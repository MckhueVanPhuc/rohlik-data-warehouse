"""Lớp STG: 14 bảng "bản đang có hiệu lực" sinh tự động từ config/contract.yaml (M2 mục 6).

Quy tắc (D02, D04):
  1. stg.<bảng> ↔ src_*.<bảng>: cùng tên bảng, cùng tên cột (giữ 4 cột kỹ thuật).
  2. Chỉ lấy dòng thuộc lô có trạng thái hiện hành COMPLETED (meta.v_batch_current) → lô UNDONE bị bỏ.
  3. Mỗi khoá nghiệp vụ giữ 1 bản: mới nhất theo _loaded_at DESC, rồi _batch_id DESC.
  4. Bản hỏng (khoá NULL, NULL ở cột bắt buộc không cho NULL, trùng khoá trong cùng lô) → meta.stg_rejects.
  5. Không sửa giá trị (không COALESCE, không kẹp giảm giá âm) – xử lý/gắn cờ ở Core.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from src.config.source_registry import BusinessContract, ContractCatalog
from src.db.pipeline_metadata import now_utc


def q(identifier: str) -> str:
    """Bọc tên cột/bảng trong dấu nháy kép an toàn."""
    return '"' + identifier.replace('"', '""') + '"'


@dataclass(frozen=True)
class StgResult:
    table: str
    landing_rows: int
    completed_rows: int
    stg_rows: int
    rejected_rows: int
    dup_in_batch: int


def _landing(table: BusinessContract) -> str:
    return f"{q(table.schema_name)}.{q(table.table)}"


def build_stg_table(
    conn: duckdb.DuckDBPyConnection, table: BusinessContract, run_id: str
) -> StgResult:
    """Ghi lại (CREATE OR REPLACE) một bảng STG trong transaction của người gọi."""
    src = _landing(table)
    keys = list(table.business_keys)
    key_cols = ", ".join(q(k) for k in keys)
    key_not_null = " AND ".join(f"l.{q(k)} IS NOT NULL" for k in keys)
    required = [
        name for name, col in table.columns.items()
        if col.required and not col.nullable and name not in keys
    ]
    req_not_null = " AND ".join(f"l.{q(c)} IS NOT NULL" for c in required) or "TRUE"
    key_text = " || '|' || ".join(f"'{k}=' || COALESCE(CAST(l.{q(k)} AS VARCHAR), 'NULL')" for k in keys)
    stg_name = f"stg.{q(table.table)}"
    rejected_at = now_utc()

    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE _stg_active AS
        SELECT l.* FROM {src} l
        JOIN meta.v_batch_current b ON b.batch_id = l._batch_id AND b.status = 'COMPLETED'
    """)
    # (a) bản lỗi khoá / NULL bắt buộc
    conn.execute(f"""
        INSERT INTO meta.stg_rejects
        SELECT ?, ?, l._batch_id, l._loaded_at, l._entered_by,
               CASE WHEN NOT ({key_not_null}) THEN 'KEY_NULL' ELSE 'NULL_REQUIRED' END,
               {key_text}, CAST(to_json(l) AS VARCHAR), ?
        FROM _stg_active l
        WHERE NOT ({key_not_null}) OR NOT ({req_not_null})
    """, [run_id, f"stg.{table.table}", rejected_at])
    # (b) trùng khoá trong cùng một lô và cùng _loaded_at → loại cả các dòng trùng (không biết bản nào đúng)
    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE _stg_dup AS
        SELECT {key_cols}, _batch_id, _loaded_at FROM _stg_active l
        WHERE {key_not_null}
        GROUP BY ALL HAVING count(*) > 1
    """)
    dup_keys = int(conn.execute("SELECT count(*) FROM _stg_dup").fetchone()[0])
    if dup_keys:
        join = " AND ".join(f"d.{q(k)} = l.{q(k)}" for k in keys)
        conn.execute(f"""
            INSERT INTO meta.stg_rejects
            SELECT ?, ?, l._batch_id, l._loaded_at, l._entered_by, 'DUP_IN_BATCH',
                   {key_text}, CAST(to_json(l) AS VARCHAR), ?
            FROM _stg_active l JOIN _stg_dup d
              ON {join} AND d._batch_id = l._batch_id AND d._loaded_at = l._loaded_at
        """, [run_id, f"stg.{table.table}", rejected_at])
        dup_filter = (
            f"AND NOT EXISTS (SELECT 1 FROM _stg_dup d WHERE {join} "
            "AND d._batch_id = l._batch_id AND d._loaded_at = l._loaded_at)"
        )
    else:
        dup_filter = ""
    # (c) chọn bản đang có hiệu lực: mới nhất theo _loaded_at rồi _batch_id
    conn.execute(f"""
        CREATE OR REPLACE TABLE {stg_name} AS
        SELECT * EXCLUDE (_rn) FROM (
            SELECT l.*, row_number() OVER (
                       PARTITION BY {", ".join(f"l.{q(k)}" for k in keys)}
                       ORDER BY l._loaded_at DESC, l._batch_id DESC) AS _rn
            FROM _stg_active l
            WHERE {key_not_null} AND {req_not_null} {dup_filter}
        ) WHERE _rn = 1
    """)
    landing_rows = int(conn.execute(f"SELECT count(*) FROM {src}").fetchone()[0])
    completed_rows = int(conn.execute("SELECT count(*) FROM _stg_active").fetchone()[0])
    stg_rows = int(conn.execute(f"SELECT count(*) FROM {stg_name}").fetchone()[0])
    rejected = int(conn.execute(
        "SELECT count(*) FROM meta.stg_rejects WHERE run_id = ? AND table_name = ?",
        [run_id, f"stg.{table.table}"],
    ).fetchone()[0])
    conn.execute("DROP TABLE IF EXISTS _stg_active")
    conn.execute("DROP TABLE IF EXISTS _stg_dup")
    return StgResult(f"stg.{table.table}", landing_rows, completed_rows, stg_rows, rejected, dup_keys)


def build_stg(
    conn: duckdb.DuckDBPyConnection, contract: ContractCatalog, run_id: str
) -> list[StgResult]:
    """Ghi lại cả 14 bảng STG (gọi trong cùng 1 transaction của refresh)."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS stg")
    return [build_stg_table(conn, table, run_id) for _, table in sorted(contract.tables.items())]


def stg_key_map(contract: ContractCatalog) -> dict[str, list[str]]:
    """{stg.<bảng>: [khoá nghiệp vụ]} – dùng cho kiểm tra B01–B14."""
    return {f"stg.{t.table}": list(t.business_keys) for t in contract.tables.values()}
