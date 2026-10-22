"""Chạy 8 mô hình theo DAG, đọc input từ kho, ghi kết quả vào pred / pred_eval (M3, D06).

* mode="models"   : bản tinh gọn – mô hình/chính sách tốt nhất, tham số chốt (src/models/params.py).
* mode="evaluate" : backtest + so sánh như notebook; lưu tham số mới vào data/models/params/.
Mỗi BT: đọc input (kết nối read-only, đóng ngay) → tính (ngoài khoá ghi) → ghi kết quả trong 1 transaction ngắn.
BT lỗi → ghi FAILED, các BT phụ thuộc bị SKIPPED; BT khác vẫn chạy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import json
from pathlib import Path
import time
import traceback
from typing import Any, Callable

from src.config.settings import Settings
from src.db.duckdb import connection, transaction
from src.db.pipeline_metadata import ensure_pipeline_metadata, now_utc, table_exists
from src.models.io import MissingInputError, read_inputs, save_run_log, write_tables
from src.models.params import load_params, save_params
from src.models.registry import DAG, SPECS, UPSTREAM_TABLES
from src.transform.marts import build_model_marts


@dataclass
class ModelResult:
    bt_id: str
    status: str                     # SUCCESS / FAILED / SKIPPED
    runtime_sec: float = 0.0
    outputs: dict[str, int] = field(default_factory=dict)
    message: str = ""
    params_file: str | None = None


def _needs(mod, mode: str) -> list[str]:
    names = list(mod.REQUIRED_INPUTS if mode == "evaluate" else getattr(mod, "FAST_INPUTS", mod.REQUIRED_INPUTS))
    return names + [n for n in getattr(mod, "OPTIONAL_INPUTS", []) if n not in names]


def last_refresh_ok(database: Path | str) -> tuple[bool, str]:
    with connection(database) as conn:
        if not table_exists(conn, "meta", "pipeline_runs"):
            return False, "chưa có lần refresh nào"
        row = conn.execute(
            """SELECT status, finished_at FROM meta.pipeline_runs
               WHERE command IN ('refresh', 'init', 'all', 'ui-refresh') AND status <> 'RUNNING'
               ORDER BY started_at DESC LIMIT 1""").fetchone()
    if row is None:
        return False, "chưa có lần refresh nào"
    return row[0] == "SUCCESS", f"refresh gần nhất: {row[0]} lúc {row[1]}"


def run_models(
    database: Path | str,
    settings: Settings,
    *,
    mode: str = "models",
    bts: list[str] | None = None,
    run_id: str,
    lock_timeout: float = 10.0,
    progress: Callable[[str], None] = print,
) -> list[ModelResult]:
    if mode not in ("models", "evaluate"):
        raise ValueError("mode phải là 'models' hoặc 'evaluate'")
    wanted = [b.upper() for b in (bts or DAG)]
    unknown = sorted(set(wanted) - set(DAG))
    if unknown:
        raise ValueError(f"Không có mô hình {unknown}; chọn trong {list(DAG)}")
    order = [b for b in DAG if b in wanted]
    failed: set[str] = set()
    results: list[ModelResult] = []
    for bt in order:
        spec = SPECS[bt]
        mod = importlib.import_module(spec.module)
        names = _needs(mod, mode)
        blocked = sorted({UPSTREAM_TABLES[n][0] for n in names if n in UPSTREAM_TABLES} & failed)
        started = now_utc()
        t0 = time.time()
        if blocked:
            res = ModelResult(bt, "SKIPPED", message=f"bỏ qua vì {blocked} lỗi trong lần chạy này")
            _record(database, run_id, mode, res, spec.model_version, None, started, lock_timeout)
            results.append(res); failed.add(bt)
            progress(f"[{bt}] SKIPPED – {res.message}")
            continue
        progress(f"[{bt}] {spec.title} – đọc input {names}")
        frozen = None
        try:
            if mode == "models":
                frozen = load_params(settings, bt)
                if frozen is None:
                    raise RuntimeError(f"Chưa có tham số chốt cho {bt} (config/model_params/{bt}.json) – chạy evaluate trước")
            with connection(database) as conn:
                inputs = read_inputs(conn, names, settings)
            cfg: dict[str, Any] = {**settings.model_config(), "mode": mode, "frozen": frozen,
                                   "n_jobs": spec.n_jobs if spec.n_jobs is not None else settings.n_jobs,
                                   **spec.extra_config}
            progress(f"[{bt}] chạy mô hình ({mode}) …")
            out = mod.run_model(inputs=inputs, config=cfg, artifact_dir=settings.runs_dir / run_id / bt)
            new_params = out.pop("_params", None)
            run_log = out.pop("run_log", None)
            pred = {k: v for k, v in out.items() if k in spec.pred_tables}
            evals = {k: v for k, v in out.items() if k in spec.eval_tables}
            status = "FINAL"
            with transaction(database, lock_timeout=lock_timeout, owner_id=f"models-{run_id}-{bt}") as conn:
                ensure_pipeline_metadata(conn)
                counts = write_tables(conn, "pred", pred, run_id=run_id, bt_id=bt,
                                      model_version=spec.model_version, model_status=status)
                if evals:
                    counts.update(write_tables(conn, "pred_eval", evals, run_id=run_id, bt_id=bt,
                                               model_version=spec.model_version, model_status=status))
            pfile = None
            if mode == "evaluate" and new_params:
                pfile = str(save_params(settings, bt, new_params, run_id=run_id, model_version=spec.model_version))
            save_run_log(settings.runs_dir, run_id, bt, run_log)
            res = ModelResult(bt, "SUCCESS", time.time() - t0, counts,
                              f"tham số: {frozen.get('_source') if frozen else 'tính mới (evaluate)'}", pfile)
        except Exception as exc:  # noqa: BLE001 – 1 BT lỗi không làm dừng các BT độc lập khác
            res = ModelResult(bt, "FAILED", time.time() - t0, message=f"{type(exc).__name__}: {exc}")
            failed.add(bt)
            tb = traceback.format_exc(limit=3)
            progress(tb)
        _record(database, run_id, mode, res, spec.model_version, frozen, started, lock_timeout)
        results.append(res)
        progress(f"[{bt}] {res.status} sau {res.runtime_sec:.1f}s – {res.message}")
    with transaction(database, lock_timeout=lock_timeout, owner_id=f"model-marts-{run_id}") as conn:
        built = build_model_marts(conn)
    progress("Mart kết quả mô hình: " + ", ".join(f"{k}={'OK' if v else 'chưa có'}" for k, v in built.items()))
    return results


def _record(database, run_id, mode, res: ModelResult, model_version, frozen, started, lock_timeout) -> None:
    with transaction(database, lock_timeout=lock_timeout, owner_id=f"model-run-log-{run_id}") as conn:
        ensure_pipeline_metadata(conn)
        conn.execute("DELETE FROM meta.model_runs WHERE run_id = ? AND bt_id = ?", [run_id, res.bt_id])
        conn.execute(
            "INSERT INTO meta.model_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [run_id, res.bt_id, mode, res.status, started, now_utc(), round(res.runtime_sec, 2), model_version,
             (frozen or {}).get("_source") if frozen else ("evaluate" if mode == "evaluate" else None),
             json.dumps(res.outputs, ensure_ascii=False), None if res.status == "SUCCESS" else res.message],
        )
