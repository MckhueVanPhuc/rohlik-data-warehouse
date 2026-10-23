"""Chạy MỘT bài toán BT trong một tiến trình Python riêng (tiến trình con) – dùng bởi src/models/runner.py.

Vì sao cần tiến trình riêng (V4-05.1, sau lỗi `OSError: access violation reading 0x0000000000000000` trên Windows):
  * Thư viện gốc (DLL/.so) của LightGBM, DuckDB, pyarrow, numba… cùng nạp vào một tiến trình có thể xung đột phiên bản
    thư viện C++ (msvcp140.dll / vcruntime140.dll / OpenMP). Mỗi BT chạy riêng → chỉ nạp đúng thư viện nó cần,
    và LightGBM được nạp TRƯỚC DuckDB/pyarrow (thứ tự an toàn).
  * Nếu thư viện gốc làm sập tiến trình (segfault / access violation), chỉ tiến trình con chết; pipeline vẫn ghi FAILED
    rõ ràng và chạy tiếp các BT không phụ thuộc.
  * Bộ nhớ (BT3 cần ~5 GB) được trả lại hệ điều hành ngay sau mỗi BT.

Giao tiếp: tiến trình con KHÔNG ghi vào kho. Nó đọc input (chỉ đọc), chạy mô hình, rồi ghi kết quả ra thư mục tạm
`<out-dir>/` dưới dạng Parquet + `result.json` (hoặc `error.json`). Tiến trình cha đọc lại và ghi vào kho trong 1 transaction.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

LGBM_MODULES = {"src.models.bt1", "src.models.bt3", "src.models.bt4"}


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:  # noqa: BLE001
        pass
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.models.worker")
    p.add_argument("--bt", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--mode", required=True, choices=["models", "evaluate"])
    p.add_argument("--database", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--settings", default=None)
    p.add_argument("--n-jobs", type=int, default=None)
    p.add_argument("--extra-config", default="{}")
    a = p.parse_args(argv)
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Nạp LightGBM TRƯỚC mọi thư viện gốc khác (DuckDB, pyarrow) – tránh xung đột runtime C++ trên Windows.
    if a.module in LGBM_MODULES:
        import lightgbm  # noqa: F401

    try:
        import importlib

        from src.config.settings import load_settings
        from src.db.duckdb import connection
        from src.models.io import read_inputs, save_run_log
        from src.models.params import load_params
        from src.models.runner import _needs

        settings = load_settings(a.settings) if a.settings else load_settings()
        mod = importlib.import_module(a.module)
        names = _needs(mod, a.mode)
        frozen = load_params(settings, a.bt) if a.mode == "models" else None
        with connection(a.database) as conn:
            inputs = read_inputs(conn, names, settings)
        cfg = {**settings.model_config(), "mode": a.mode, "frozen": frozen,
               "n_jobs": a.n_jobs if a.n_jobs is not None else settings.n_jobs, **json.loads(a.extra_config)}
        out = mod.run_model(inputs=inputs, config=cfg, artifact_dir=settings.runs_dir / a.run_id / a.bt)
        new_params = out.pop("_params", None)
        run_log = out.pop("run_log", None)
        save_run_log(settings.runs_dir, a.run_id, a.bt, run_log)
        tables = {}
        for name, df in out.items():
            if df is None:
                continue
            path = out_dir / f"{name}.parquet"
            try:
                df.to_parquet(path, index=False)
            except Exception:  # noqa: BLE001 – cột object trộn kiểu (vd số lẫn chữ) → ghi dạng chữ, giữ ô trống
                safe = df.copy()
                for c in safe.columns[safe.dtypes == object]:
                    safe[c] = safe[c].map(lambda v: v if v is None or isinstance(v, str) else str(v))
                safe.to_parquet(path, index=False)
            tables[name] = path.name
        (out_dir / "result.json").write_text(json.dumps({"tables": tables, "params": new_params}, default=_json_default,
                                                        ensure_ascii=False), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001 – báo lỗi có cấu trúc cho tiến trình cha
        (out_dir / "error.json").write_text(json.dumps({
            "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(limit=6)},
            ensure_ascii=False), encoding="utf-8")
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
