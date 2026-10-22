"""Hợp đồng 8 mô hình bản tinh gọn (D06): đăng ký DAG/bảng, tham số chốt, chế độ models/evaluate.

Phần chạy thật trên kho (đánh dấu integration) tự bỏ qua khi máy chưa có data/warehouse/rohlik.duckdb đã refresh.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from src.config.settings import load_settings
from src.models.params import DEFAULT_PARAMS_DIR, load_params
from src.models.registry import DAG, SPECS, UPSTREAM_TABLES

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("bt", DAG)
def test_registry_tables_match_model_outputs(bt):
    spec = SPECS[bt]
    mod = importlib.import_module(spec.module)
    assert set(spec.pred_tables) <= set(mod.FAST_OUTPUTS), "chế độ models phải ra đủ bảng pred"
    assert set(spec.eval_tables) <= set(mod.OUTPUTS)
    assert set(mod.FAST_OUTPUTS) <= set(mod.OUTPUTS)
    assert set(mod.FAST_INPUTS) <= set(mod.REQUIRED_INPUTS) | set(getattr(mod, "OPTIONAL_INPUTS", []))
    for name in mod.FAST_INPUTS:
        if name in UPSTREAM_TABLES:
            src_bt, schema, _ = UPSTREAM_TABLES[name]
            assert schema == "pred", f"{bt} chế độ models không được phụ thuộc bảng evaluate {name}"
            assert DAG.index(src_bt) < DAG.index(bt)


@pytest.mark.parametrize("bt", DAG)
def test_default_frozen_params_exist_and_load(bt):
    path = DEFAULT_PARAMS_DIR / f"{bt}.json"
    assert path.is_file(), f"thiếu {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["bt_id"] == bt and data["params"]
    params = load_params(load_settings(), bt)
    assert params is not None and "_source" in params


@pytest.mark.parametrize("bt", ["BT1", "BT2", "BT3", "BT4", "BT6", "BT8"])
def test_models_mode_refuses_missing_frozen_params(bt):
    mod = importlib.import_module(SPECS[bt].module)
    with pytest.raises((ValueError, KeyError)):
        mod.run_model(inputs={}, config={"mode": "models", "frozen": {}})


def test_bt5_final_method_is_e2_and_bt3_final_is_m4():
    assert importlib.import_module("src.models.bt5").FINAL_METHOD.startswith("E2")
    assert importlib.import_module("src.models.bt3").FINAL_MODEL == "M4_LightGBM_Tweedie"


@pytest.mark.integration
@pytest.mark.parametrize("bt", ["BT1", "BT8"])
def test_fast_models_on_local_warehouse(bt):
    from src.db.duckdb import DEFAULT_DATABASE, connection
    from src.db.pipeline_metadata import table_exists
    from src.models.io import read_inputs
    if not DEFAULT_DATABASE.is_file():
        pytest.skip("chưa có data/warehouse/rohlik.duckdb trên máy này")
    settings = load_settings()
    mod = importlib.import_module(SPECS[bt].module)
    with connection(DEFAULT_DATABASE) as conn:
        if not table_exists(conn, "stg", "sku_sales_daily"):
            pytest.skip("kho chưa refresh")
        inputs = read_inputs(conn, list(mod.FAST_INPUTS), settings)
    out = mod.run_model(inputs=inputs, config={**settings.model_config(), "mode": "models",
                                               "frozen": load_params(settings, bt)})
    assert set(SPECS[bt].pred_tables) <= set(out)
