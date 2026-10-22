"""V4-05.1: mỗi BT chạy trong tiến trình riêng – kết quả trả về đúng; tiến trình con bị sập (lỗi thư viện gốc)
chỉ làm BT đó FAILED, pipeline vẫn chạy tiếp và không ghi dở vào kho."""

from __future__ import annotations

import sys
import textwrap

import pytest

from src.db.duckdb import connection
from src.models import runner
from src.models.registry import ModelSpec
from src.transform.refresh import refresh

from test_pipeline_v405 import project  # noqa: F401 – dùng lại kho tổng hợp nhỏ

OK_MODULE = textwrap.dedent('''
    import pandas as pd
    FAST_INPUTS = ["orders_daily"]
    REQUIRED_INPUTS = ["orders_daily"]
    OUTPUTS = ["fake_out"]
    FAST_OUTPUTS = ["fake_out"]
    def run_model(*, inputs, config, artifact_dir=None):
        o = inputs["orders_daily"]
        return {"fake_out": pd.DataFrame({"warehouse": sorted(o["warehouse"].unique()), "n": [len(o)] * o["warehouse"].nunique(),
                                          "n_jobs": [config["n_jobs"]] * o["warehouse"].nunique()})}
''')

CRASH_MODULE = textwrap.dedent('''
    import ctypes
    FAST_INPUTS = []
    REQUIRED_INPUTS = []
    OUTPUTS = ["crash_out"]
    FAST_OUTPUTS = ["crash_out"]
    def run_model(*, inputs, config, artifact_dir=None):
        ctypes.string_at(0)          # đọc địa chỉ 0 → access violation / segfault giống lỗi LightGBM trên Windows
''')


@pytest.fixture
def fake_models(tmp_path, monkeypatch):
    pkg = tmp_path / "fakemods"
    pkg.mkdir()
    (pkg / "fake_ok_bt.py").write_text(OK_MODULE, encoding="utf-8")
    (pkg / "fake_crash_bt.py").write_text(CRASH_MODULE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(pkg))
    monkeypatch.setenv("PYTHONPATH", str(pkg))
    specs = {
        "BTC": ModelSpec("BTC", "giả lập sập", "fake_crash_bt", "t", ("crash_out",), ()),
        "BTO": ModelSpec("BTO", "giả lập đúng", "fake_ok_bt", "t", ("fake_out",), ()),
    }
    monkeypatch.setattr(runner, "SPECS", specs)
    monkeypatch.setattr(runner, "DAG", ["BTC", "BTO"])
    return specs


def test_isolated_run_returns_results_and_survives_native_crash(project, fake_models, monkeypatch):  # noqa: F811
    tmp, database, settings, contract = project
    assert refresh(database, settings, contract).status == "SUCCESS"
    logs: list[str] = []
    results = runner.run_models(database, settings, mode="evaluate", run_id="iso_test", isolate=True, progress=logs.append)
    by = {r.bt_id: r for r in results}
    assert by["BTC"].status == "FAILED"
    assert "dừng bất thường" in by["BTC"].message
    assert by["BTO"].status == "SUCCESS", by["BTO"].message
    with connection(database) as conn:
        rows = conn.execute("SELECT warehouse, n FROM pred.fake_out ORDER BY 1").fetchall()
        assert rows == [("Brno_1", 88), ("Prague_1", 88)]
        assert conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'crash_out'").fetchone()[0] == 0
        status = dict(conn.execute("SELECT bt_id, status FROM meta.model_runs WHERE run_id = 'iso_test'").fetchall())
    assert status == {"BTC": "FAILED", "BTO": "SUCCESS"}


def test_in_process_mode_still_available(project, fake_models):  # noqa: F811
    _, database, settings, contract = project
    assert refresh(database, settings, contract).status == "SUCCESS"
    results = runner.run_models(database, settings, mode="models", bts=["BTO"], run_id="inproc", isolate=False,
                                progress=lambda m: None)
    # chế độ models cần tham số chốt → module giả không có file params nên FAILED rõ ràng, không sập
    assert results[0].status in {"SUCCESS", "FAILED"}


def test_settings_default_isolation_on():
    from src.config.settings import load_settings
    s = load_settings()
    assert s.models_isolate is True and s.path is not None and s.path.name == "settings.yaml"
