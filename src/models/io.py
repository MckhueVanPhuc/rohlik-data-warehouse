"""Đọc input cho mô hình từ kho DuckDB (STG + pred) và ghi kết quả vào pred / pred_eval.

* Input "nguồn" đọc từ stg.* (bản đang có hiệu lực, đã bỏ lô UNDONE) với đúng tên cột Kaggle/Landing,
  cắt theo settings: train_from ≤ date ≤ as_of (lịch tới forecast_end), chỉ 7 kho trong settings.
* Input "kết quả BT trước" đọc từ pred.* / pred_eval.* (lần chạy gần nhất).
* Ghi: mỗi bảng pred.<tên> được ghi lại toàn bộ (CREATE OR REPLACE) + 4 cột metadata
  run_id, bt_id, model_version, model_status (M2 mục 10.1).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.config.settings import Settings
from src.db.pipeline_metadata import table_exists
from src.models.registry import UPSTREAM_TABLES

# stg canonical → tên cột mà code mô hình (notebook) dùng
WORKFORCE_RENAME = {
    "morning_shift_ratio": "morning_share",
    "overtime_cap_ratio": "overtime_cap",
    "shortage_penalty_multiplier": "shortage_penalty",
    "legacy_rule_buffer_ratio": "rule_buffer",
}
META_COLS = ("run_id", "bt_id", "model_version", "model_status")


class MissingInputError(RuntimeError):
    """Thiếu bảng input (chưa refresh / BT trước chưa chạy)."""


def _source_sql(name: str) -> tuple[str, str] | None:
    """(câu SQL, loại cửa sổ) cho input nguồn; None nếu không phải input nguồn."""
    actual = "WHERE date BETWEEN $train_from AND $as_of"
    sql = {
        "orders_daily": f"SELECT warehouse, date, orders FROM stg.orders_daily {actual} AND list_contains($whs, warehouse)",
        "calendar": "SELECT warehouse, date, holiday_name, holiday, shops_closed, winter_school_holidays, school_holidays "
                    "FROM stg.calendar WHERE date BETWEEN $train_from AND $forecast_end AND list_contains($whs, warehouse)",
        "sku_sales_daily": f"SELECT unique_id, date, warehouse, sales, total_orders FROM stg.sku_sales_daily {actual} "
                           "AND list_contains($whs, warehouse)",
        "prices": f"SELECT unique_id, date, sell_price_main FROM stg.prices {actual}",
        "promotions": "SELECT unique_id, date, " + ", ".join(f"type_{i}_discount" for i in range(7))
                      + f" FROM stg.promotions {actual}",
        "availability": f"SELECT unique_id, date, availability FROM stg.availability {actual}",
        "product_master": "SELECT unique_id, product_unique_id, name, L1_category_name_en, L2_category_name_en, "
                          "L3_category_name_en, L4_category_name_en, warehouse FROM stg.product_master",
        "sku_weights": "SELECT unique_id, weight FROM stg.sku_weights",
        "cost_params": "SELECT L1_category_name_en, cost_ratio, shelf_life_days, waste_handling_cost_ratio FROM stg.cost_params",
        "workforce_params": "SELECT * EXCLUDE (_batch_id, _source, _loaded_at, _entered_by) FROM stg.workforce_params",
    }
    return sql.get(name)


def _fix_dates(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("date", "cutoff", "data_until", "month"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


def read_inputs(conn: duckdb.DuckDBPyConnection, names: list[str], settings: Settings) -> dict[str, pd.DataFrame]:
    """Đọc các input mô hình cần; báo lỗi rõ nếu bảng chưa có."""
    params = {**settings.sql_params(), "whs": list(settings.warehouses)}
    out: dict[str, pd.DataFrame] = {}
    for name in names:
        sql = _source_sql(name)
        if sql is not None:
            if not table_exists(conn, "stg", name):
                raise MissingInputError(f"Chưa có stg.{name} – chạy `python -m pipeline.run refresh` trước")
            used = {k: v for k, v in params.items() if f"${k}" in sql}
            df = conn.execute(sql, used).df()
            if name == "workforce_params":
                df = df.rename(columns=WORKFORCE_RENAME)
            out[name] = _fix_dates(df)
            continue
        if name in UPSTREAM_TABLES:
            bt, schema, table = UPSTREAM_TABLES[name]
            if not table_exists(conn, schema, table):
                hint = "evaluate" if schema == "pred_eval" else "models"
                raise MissingInputError(f"Chưa có {schema}.{table} của {bt} – chạy `python -m pipeline.run {hint} --bt {bt}` trước")
            df = conn.execute(f'SELECT * EXCLUDE ({", ".join(META_COLS)}) FROM {schema}."{table}"').df()
            out[name] = _fix_dates(df)
            continue
        raise MissingInputError(f"Không biết đọc input '{name}' từ đâu")
    return out


def write_tables(conn: duckdb.DuckDBPyConnection, schema: str, frames: dict[str, pd.DataFrame], *,
                 run_id: str, bt_id: str, model_version: str, model_status: str) -> dict[str, int]:
    """Ghi lại toàn bộ các bảng kết quả trong transaction của người gọi."""
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    counts = {}
    for name, df in frames.items():
        d = df.copy()
        for c in d.columns:
            if d[c].dtype == object:
                sample = d[c].dropna()
                if len(sample) and isinstance(sample.iloc[0], pd.Timestamp):
                    d[c] = pd.to_datetime(d[c])
        for c in ("date", "month", "cutoff", "data_until"):
            if c in d.columns:
                d[c] = pd.to_datetime(d[c]).dt.date
        d["run_id"], d["bt_id"], d["model_version"], d["model_status"] = run_id, bt_id, model_version, model_status
        view = f"_w_{name}"
        conn.register(view, d)
        conn.execute(f'CREATE OR REPLACE TABLE {schema}."{name}" AS SELECT * FROM {view}')
        conn.unregister(view)
        counts[f"{schema}.{name}"] = len(d)
    return counts


def save_run_log(runs_dir: Path, run_id: str, bt_id: str, run_log: pd.DataFrame | None) -> Path | None:
    if run_log is None:
        return None
    folder = Path(runs_dir) / run_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{bt_id}_run_log.csv"
    run_log.to_csv(path, index=False, encoding="utf-8")
    return path
