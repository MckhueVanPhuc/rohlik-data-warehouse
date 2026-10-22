"""Ghi lô upload vào Landing và soft undo (M9 mục 5–6, D02/D13/D14).

* Mọi thao tác chạy trong 1 transaction có writer lock (src.db.duckdb.transaction); lỗi → rollback.
* Không lấy được khoá trong `lock_timeout` giây → WriterLockTimeout → giao diện báo "Hệ thống đang bận".
* Dùng lại bảng meta v1 của repo: source_batches (source_id = 'upload:<bảng>', fingerprint = SHA-256 file),
  batch_status_events, table_loads, entry_audit_events + bảng mới meta.entry_log (người nhập, lý do).
* Undo = sự kiện UNDONE (+ source_batches.status = 'UNDONE'); KHÔNG xoá dòng Landing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
from uuid import uuid4

import pandas as pd

from src.config.source_registry import BusinessContract, ContractCatalog
from src.db.duckdb import transaction
from src.db.duckdb_metadata import (
    complete_source_batch,
    record_batch_status,
    record_entry_audit,
    record_table_load,
    start_source_batch,
)
from src.db.pipeline_metadata import ensure_pipeline_metadata
from src.entry.validate import UploadReport, validate_person_fields

ENTERED_BY = "user:admin_local"   # D14 – một tài khoản chung; người thật nằm ở operator_name


class EntryError(RuntimeError):
    """Thao tác nhập liệu/undo bị từ chối (dữ liệu chưa hợp lệ, lô không được undo…)."""


def new_batch_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"b_upload_{now.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)}"


def write_upload(
    database: Path | str,
    contract: ContractCatalog,
    table: BusinessContract,
    report: UploadReport,
    *,
    operator: str,
    reason: str,
    lock_timeout: float = 10.0,
) -> dict:
    """Ghi cả file (đã qua U-01…U-07) thành 1 lô COMPLETED. Trả thông tin lô."""
    errors = validate_person_fields(operator, reason)
    if errors:
        raise EntryError("; ".join(errors))
    if not report.ok:
        raise EntryError("File còn lỗi – chưa ghi gì (nguyên tắc cả file hoặc không ghi)")
    operator, reason = operator.strip(), reason.strip()
    qualified = f"{table.schema_name}.{table.table}"
    now = datetime.now(timezone.utc)
    started = now.isoformat()
    batch_id = new_batch_id(now)
    data = report.clean.copy()
    cols = list(table.columns)
    lineage = json.dumps({"mode": "UPLOAD", "operator": operator, "reason": reason,
                          "file_name": report.file_name}, ensure_ascii=False, sort_keys=True)
    with transaction(database, lock_timeout=lock_timeout, owner_id=f"upload-{batch_id}") as conn:
        ensure_pipeline_metadata(conn)
        dup = conn.execute(
            """SELECT b.batch_id FROM meta.source_batches b JOIN meta.v_batch_current c USING (batch_id)
               WHERE b.source_id LIKE 'upload:%' AND b.source_fingerprint = ? AND c.status = 'COMPLETED'""",
            [report.sha256]).fetchone()
        if dup:
            raise EntryError(f"U-08: file này đã được nhập ở lô {dup[0]}")
        start_source_batch(conn, batch_id=batch_id, source_id=f"upload:{table.table}",
                           source_path=f"upload:{report.file_name}", source_fingerprint=report.sha256,
                           contract_version=contract.contract_version, started_at=started,
                           source_row_count=len(data))
        record_batch_status(conn, batch_id=batch_id, status="RUNNING", occurred_at=started,
                            actor=ENTERED_BY, reason=lineage)
        conn.register("_upload_rows", data[cols].astype(object))
        proj = ", ".join(f'CAST("{c}" AS {table.columns[c].type})' for c in cols)
        target = ", ".join(f'"{c}"' for c in cols)
        conn.execute(
            f'INSERT INTO "{table.schema_name}"."{table.table}" ({target}, _batch_id, _source, _loaded_at, _entered_by) '
            f"SELECT {proj}, ?, ?, ?, ? FROM _upload_rows",
            [batch_id, f"upload:{report.file_name}", now.replace(tzinfo=None), ENTERED_BY])
        conn.unregister("_upload_rows")
        loaded = int(conn.execute(f'SELECT count(*) FROM "{table.schema_name}"."{table.table}" WHERE _batch_id = ?',
                                  [batch_id]).fetchone()[0])
        if loaded != len(data):
            raise EntryError(f"Ghi {loaded} dòng ≠ {len(data)} dòng hợp lệ – đã rollback")
        record_table_load(conn, batch_id=batch_id, table_name=qualified, source_row_count=len(data),
                          loaded_row_count=loaded, recorded_at=started)
        record_entry_audit(conn, batch_id=batch_id, actor=ENTERED_BY, action="UPLOAD", target_table=qualified,
                           occurred_at=started, details_json=json.dumps(
                               {"operator": operator, "reason": reason, "file_name": report.file_name,
                                "sha256": report.sha256, "rows": loaded}, ensure_ascii=False, sort_keys=True))
        done = datetime.now(timezone.utc)
        if done <= now:
            done = now + timedelta(microseconds=1)
        complete_source_batch(conn, batch_id=batch_id, completed_at=done.isoformat())
        record_batch_status(conn, batch_id=batch_id, status="COMPLETED", occurred_at=done.isoformat(),
                            actor=ENTERED_BY, reason=lineage)
        conn.execute("INSERT INTO meta.entry_log VALUES (?, ?, 'UPLOAD', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     [uuid4().hex, batch_id, qualified, report.file_name, report.sha256, loaded,
                      report.n_keys_replaced, ENTERED_BY, operator, reason, started])
    return {"batch_id": batch_id, "table": qualified, "rows": loaded, "operator": operator}


def undo_batch(database: Path | str, batch_id: str, *, operator: str, reason: str,
               lock_timeout: float = 10.0) -> dict:
    """Soft undo 1 lô UPLOAD đang COMPLETED (lô nạp nguồn không được undo)."""
    errors = validate_person_fields(operator, reason)
    if errors:
        raise EntryError("; ".join(errors))
    operator, reason = operator.strip(), reason.strip()
    at = datetime.now(timezone.utc).isoformat()
    with transaction(database, lock_timeout=lock_timeout, owner_id=f"undo-{batch_id}") as conn:
        ensure_pipeline_metadata(conn)
        row = conn.execute("SELECT status, batch_type, source_id FROM meta.v_batch_current WHERE batch_id = ?",
                           [batch_id]).fetchone()
        if row is None:
            raise EntryError(f"Không có lô {batch_id}")
        status, batch_type, source_id = row
        if batch_type != "UPLOAD":
            raise EntryError("Chỉ undo được lô UPLOAD; lô nạp nguồn (SOURCE) không undo trên giao diện")
        if status != "COMPLETED":
            raise EntryError(f"Lô {batch_id} đang ở trạng thái {status} – không undo được")
        table_name = conn.execute("SELECT table_name FROM meta.table_loads WHERE batch_id = ?", [batch_id]).fetchone()
        table_name = table_name[0] if table_name else source_id
        payload = json.dumps({"mode": "UNDO", "operator": operator, "reason": reason}, ensure_ascii=False, sort_keys=True)
        record_batch_status(conn, batch_id=batch_id, status="UNDONE", occurred_at=at, actor=ENTERED_BY, reason=payload)
        conn.execute("UPDATE meta.source_batches SET status = 'UNDONE' WHERE batch_id = ?", [batch_id])
        record_entry_audit(conn, batch_id=batch_id, actor=ENTERED_BY, action="UNDO", target_table=table_name,
                           occurred_at=at, details_json=payload)
        conn.execute("INSERT INTO meta.entry_log VALUES (?, ?, 'UNDO', ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?)",
                     [uuid4().hex, batch_id, table_name, ENTERED_BY, operator, reason, at])
    return {"batch_id": batch_id, "status": "UNDONE"}


def batch_history(conn) -> pd.DataFrame:
    """Danh sách lô (nguồn + upload) kèm người nhập/lý do và cờ 'chờ refresh'."""
    return conn.execute("""
        WITH up AS (
            SELECT batch_id, any_value(operator_name) FILTER (WHERE action = 'UPLOAD') AS operator_name,
                   any_value(reason) FILTER (WHERE action = 'UPLOAD') AS reason,
                   any_value(operator_name) FILTER (WHERE action = 'UNDO') AS undo_by,
                   any_value(reason) FILTER (WHERE action = 'UNDO') AS undo_reason
            FROM meta.entry_log GROUP BY batch_id),
        last_ok AS (SELECT max(finished_at) AS t FROM meta.pipeline_runs
                    WHERE command IN ('refresh', 'init', 'all', 'ui-refresh') AND status = 'SUCCESS')
        SELECT b.batch_id, COALESCE(t.table_name, b.source_id) AS table_name, c.batch_type, c.status,
               b.source_row_count AS n_rows, b.source_path AS file_or_source,
               up.operator_name, up.reason, up.undo_by, up.undo_reason,
               b.started_at, c.status_at,
               CASE WHEN (SELECT t FROM last_ok) IS NULL OR c.status_at > (SELECT t FROM last_ok)
                    THEN 'Chưa refresh' ELSE 'Đã vào báo cáo' END AS bao_cao
        FROM meta.source_batches b
        JOIN meta.v_batch_current c USING (batch_id)
        LEFT JOIN (SELECT batch_id, any_value(table_name) AS table_name FROM meta.table_loads GROUP BY batch_id) t
               USING (batch_id)
        LEFT JOIN up USING (batch_id)
        ORDER BY b.started_at DESC
    """).df()
