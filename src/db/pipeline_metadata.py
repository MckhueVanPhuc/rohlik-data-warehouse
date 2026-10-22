"""Bảng meta bổ sung cho pipeline V4 (STG → Core → Mart → DQ, nhập liệu, mô hình).

Không sửa 5 bảng meta v1 của src/db/duckdb_metadata.py (V4-02). Thành phần mới được ghi
riêng trong meta.schema_versions với component = "v4_pipeline".
"""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb

PIPELINE_COMPONENT = "v4_pipeline"
PIPELINE_SCHEMA_VERSION = 1

PIPELINE_DDL = {
    "pipeline_runs": """
        CREATE TABLE IF NOT EXISTS meta.pipeline_runs (
            run_id VARCHAR PRIMARY KEY,
            command VARCHAR NOT NULL,
            status VARCHAR NOT NULL,            -- RUNNING / SUCCESS / FAILED
            started_at VARCHAR NOT NULL,
            finished_at VARCHAR,
            as_of VARCHAR,
            details_json VARCHAR,
            error_message VARCHAR
        )""",
    "quality_report": """
        CREATE TABLE IF NOT EXISTS meta.quality_report (
            run_id VARCHAR NOT NULL,
            check_id VARCHAR NOT NULL,
            table_name VARCHAR NOT NULL,
            severity VARCHAR NOT NULL,          -- ERROR / WARN
            observed DOUBLE,
            threshold VARCHAR,
            status VARCHAR NOT NULL,            -- PASS / WARN / FAIL
            description VARCHAR,
            checked_at VARCHAR NOT NULL,
            PRIMARY KEY (run_id, check_id)
        )""",
    "stg_rejects": """
        CREATE TABLE IF NOT EXISTS meta.stg_rejects (
            run_id VARCHAR NOT NULL,
            table_name VARCHAR NOT NULL,
            _batch_id VARCHAR,
            _loaded_at TIMESTAMP,
            _entered_by VARCHAR,
            reason VARCHAR NOT NULL,            -- KEY_NULL / NULL_REQUIRED / DUP_IN_BATCH
            business_key VARCHAR,
            row_json VARCHAR,
            rejected_at VARCHAR NOT NULL
        )""",
    "entry_log": """
        CREATE TABLE IF NOT EXISTS meta.entry_log (
            entry_id VARCHAR PRIMARY KEY,
            batch_id VARCHAR NOT NULL,
            action VARCHAR NOT NULL,            -- UPLOAD / UNDO
            table_name VARCHAR NOT NULL,
            file_name VARCHAR,
            file_sha256 VARCHAR,
            n_rows BIGINT,
            n_keys_replaced BIGINT,
            entered_by VARCHAR NOT NULL,        -- user:admin_local (D14)
            operator_name VARCHAR NOT NULL,     -- ô "Người nhập" (bắt buộc)
            reason VARCHAR NOT NULL,            -- ô "Lý do" (bắt buộc)
            entered_at VARCHAR NOT NULL
        )""",
    "model_runs": """
        CREATE TABLE IF NOT EXISTS meta.model_runs (
            run_id VARCHAR NOT NULL,
            bt_id VARCHAR NOT NULL,
            mode VARCHAR NOT NULL,              -- models / evaluate / import
            status VARCHAR NOT NULL,            -- SUCCESS / FAILED / SKIPPED
            started_at VARCHAR NOT NULL,
            finished_at VARCHAR,
            runtime_sec DOUBLE,
            model_version VARCHAR,
            params_source VARCHAR,
            outputs_json VARCHAR,
            error_message VARCHAR,
            PRIMARY KEY (run_id, bt_id)
        )""",
}

V_BATCH_CURRENT = """
CREATE OR REPLACE VIEW meta.v_batch_current AS
WITH ev AS (
    SELECT batch_id, status, occurred_at,
           row_number() OVER (PARTITION BY batch_id ORDER BY occurred_at DESC, event_id DESC) AS rn
    FROM meta.batch_status_events
)
SELECT b.batch_id, b.source_id, COALESCE(ev.status, b.status) AS status,
       COALESCE(ev.occurred_at, b.completed_at, b.started_at) AS status_at,
       CASE WHEN b.source_id LIKE 'upload:%' THEN 'UPLOAD' ELSE 'SOURCE' END AS batch_type
FROM meta.source_batches b
LEFT JOIN ev ON ev.batch_id = b.batch_id AND ev.rn = 1
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_pipeline_metadata(conn: duckdb.DuckDBPyConnection) -> None:
    """Tạo bảng meta bổ sung + view trạng thái lô trong transaction của người gọi (idempotent)."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS meta")
    for ddl in PIPELINE_DDL.values():
        conn.execute(ddl)
    conn.execute(V_BATCH_CURRENT)
    row = conn.execute(
        "SELECT version FROM meta.schema_versions WHERE component = ?", [PIPELINE_COMPONENT]
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta.schema_versions VALUES (?, ?, ?, ?)",
            [PIPELINE_COMPONENT, PIPELINE_SCHEMA_VERSION, now_utc(),
             "V4-05 pipeline: STG/Core/Mart/DQ, entry log, model runs"],
        )
    elif row[0] != PIPELINE_SCHEMA_VERSION:
        raise RuntimeError(
            f"meta.schema_versions {PIPELINE_COMPONENT}={row[0]} khác {PIPELINE_SCHEMA_VERSION}; cần migration"
        )


def table_exists(conn: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    return bool(conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [schema, table],
    ).fetchone()[0])
