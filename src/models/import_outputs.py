"""Nạp nhanh kết quả 8 bài toán đã chạy sẵn (thư mục "Final Code") vào pred / pred_eval.

Dùng khi muốn dashboard có kết quả ngay mà không chạy lại mô hình (vd. trình bày):
    python -m pipeline.run import-outputs --from "/Users/namnut/Downloads/Final Code"
Tìm file theo đúng tên trong thư mục và mọi thư mục con (như hàm tim_file của notebook).
Bảng được đánh dấu model_status = IMPORTED (khác FINAL của lần chạy trong pipeline).
"""

from __future__ import annotations

from pathlib import Path

from src.config.settings import Settings
from src.db.duckdb import transaction
from src.db.pipeline_metadata import ensure_pipeline_metadata, now_utc
from src.models.registry import SPECS
from src.transform.marts import build_model_marts

# tên file CSV trong Final Code → (BT, schema, bảng đích)
FILE_MAP: dict[str, tuple[str, str, str]] = {}
for _bt, _spec in SPECS.items():
    for _t in _spec.pred_tables:
        FILE_MAP[f"{_t}.csv"] = (_bt, "pred", _t)
    for _t in _spec.eval_tables:
        FILE_MAP[f"{_t}.csv"] = (_bt, "pred_eval", _t)
FILE_MAP["method_comparison.csv"] = ("BT5", "pred_eval", "bt5_method_comparison")   # tên file thực tế trong BT5_Output

# cột tối thiểu để mart kết quả mô hình hiển thị được
MIN_COLUMNS = {
    "fc_orders": ["warehouse", "date", "series", "p50", "p90", "model"],
    "staff_plan": ["warehouse", "date", "shift", "staff", "policy", "cost_eur"],
    "driver_plan": ["warehouse", "date", "orders_p50", "orders_p90", "drivers_needed"],
    "lost_sales": ["unique_id", "date", "warehouse", "L1", "sales", "est_demand", "lost_units", "lost_revenue"],
    "fc_sku": ["unique_id", "date", "warehouse", "L1", "final_price", "p50", "p90", "model"],
    "promo_effect": ["L1", "discount", "theta", "lift_%", "ci_low_%", "ci_high_%"],
    "replenishment": ["unique_id", "date", "warehouse", "L1", "final_price", "order_qty", "policy"],
    "markdown_plan": ["unique_id", "date", "warehouse", "L1", "discount", "stock", "expiring_today", "expected_waste"],
    "growth_curves": ["warehouse", "month", "t", "orders"],
    "growth_projection": ["warehouse", "t", "fitted", "model"],
}


def find_files(root: Path) -> dict[str, Path]:
    """Tên file (thường) → đường dẫn nông nhất; bỏ thư mục Input của từng bài (là input, không phải kết quả)."""
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*.csv"), key=lambda p: (len(p.parts), str(p))):
        if any(part.lower().endswith("_input") for part in path.parts):
            continue
        name = path.name.lower()
        if name in FILE_MAP and name not in found:
            found[name] = path
    return found


def import_outputs(database: Path | str, settings: Settings, source: Path | str, *, run_id: str,
                   lock_timeout: float = 10.0, progress=print) -> dict[str, int]:
    root = Path(source).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"Không thấy thư mục {root}")
    files = find_files(root)
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file kết quả nào (vd. fc_orders.csv) trong {root}")
    counts: dict[str, int] = {}
    fx_case = " ".join(f"WHEN '{c}' THEN {v}" for c, v in settings.fx_eur.items())
    with transaction(database, lock_timeout=lock_timeout, owner_id=f"import-{run_id}") as conn:
        ensure_pipeline_metadata(conn)
        for name, path in files.items():
            bt, schema, table = FILE_MAP[name]
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            conn.execute(
                f'CREATE OR REPLACE TABLE {schema}."{table}" AS SELECT *, ? AS run_id, ? AS bt_id, ? AS model_version, '
                f"'IMPORTED' AS model_status FROM read_csv(?, header = true, auto_detect = true, sample_size = -1)",
                [run_id, bt, f"{bt}-final-code-import", str(path)])
            cols = [r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = ? AND table_name = ?",
                [schema, table]).fetchall()]
            miss = [c for c in MIN_COLUMNS.get(table, []) if c not in cols]
            if miss:
                raise ValueError(f"{path.name}: thiếu cột {miss} – không nạp được vào {schema}.{table}")
            if table == "lost_sales" and "lost_revenue_eur" not in cols:
                if "currency" not in cols:
                    conn.execute(f'ALTER TABLE pred."{table}" ADD COLUMN currency VARCHAR')
                    conn.execute(f'UPDATE pred."{table}" SET currency = d.currency FROM core.dim_warehouse d '
                                 f'WHERE d.warehouse = pred."{table}".warehouse')
                conn.execute(f'ALTER TABLE pred."{table}" ADD COLUMN lost_revenue_eur DOUBLE')
                conn.execute(f'UPDATE pred."{table}" SET lost_revenue_eur = lost_revenue * CASE currency {fx_case} END')
            if table == "markdown_plan" and "currency" not in cols:
                conn.execute(f'ALTER TABLE pred."{table}" ADD COLUMN currency VARCHAR')
            for c in ("date", "month"):
                if c in cols:
                    kind = conn.execute(f'SELECT typeof("{c}") FROM {schema}."{table}" LIMIT 1').fetchone()
                    if kind and kind[0] != "DATE":
                        conn.execute(f'ALTER TABLE {schema}."{table}" ALTER "{c}" TYPE DATE USING CAST("{c}" AS DATE)')
            n = int(conn.execute(f'SELECT count(*) FROM {schema}."{table}"').fetchone()[0])
            counts[f"{schema}.{table}"] = n
            conn.execute("INSERT INTO meta.model_runs VALUES (?, ?, 'import', 'SUCCESS', ?, ?, 0, ?, ?, ?, NULL) "
                         "ON CONFLICT DO NOTHING",
                         [run_id, f"{bt}:{table}", now_utc(), now_utc(), f"{bt}-final-code-import", str(path),
                          f'{{"{schema}.{table}": {n}}}'])
            progress(f"  {path.relative_to(root)} → {schema}.{table} ({n:,} dòng)")
        build_model_marts(conn)
    return counts

