"""Refresh = STG → Core → Mart → DQ trong MỘT transaction có writer lock.

Có kiểm tra ERROR thất bại → ROLLBACK (STG/Core/Mart cũ giữ nguyên), ghi lại báo cáo DQ + bản lỗi
trong một transaction ngắn riêng để người dùng xem nguyên nhân, trả trạng thái FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config.settings import Settings
from src.config.source_registry import ContractCatalog
from src.db.duckdb import transaction
from src.db.pipeline_metadata import ensure_pipeline_metadata, now_utc
from src.transform.core import build_core
from src.transform.marts import build_base_marts, build_model_marts
from src.transform.quality import CheckResult, build_checks, run_checks, stg_row_checks, write_report
from src.transform.stg import build_stg, stg_key_map


class RefreshFailed(RuntimeError):
    def __init__(self, message: str, results: list[CheckResult]):
        super().__init__(message)
        self.results = results


@dataclass
class RefreshReport:
    run_id: str
    status: str
    stg_rows: dict[str, int] = field(default_factory=dict)
    stg_rejects: dict[str, int] = field(default_factory=dict)
    core_rows: dict[str, int] = field(default_factory=dict)
    mart_rows: dict[str, int] = field(default_factory=dict)
    model_marts: dict[str, bool] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if c["status"] == "FAIL"]

    @property
    def warned(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if c["status"] == "WARN"]


def new_run_id(prefix: str) -> str:
    from datetime import datetime, timezone
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:6]}"


def record_run(database: Path | str, run_id: str, command: str, status: str, settings: Settings,
               details: dict | None = None, error: str | None = None, *, lock_timeout: float = 10.0) -> None:
    """Ghi/ cập nhật 1 dòng meta.pipeline_runs (transaction ngắn riêng)."""
    with transaction(database, lock_timeout=lock_timeout, owner_id=f"pipeline-run-log-{run_id}") as conn:
        ensure_pipeline_metadata(conn)
        exists = conn.execute("SELECT count(*) FROM meta.pipeline_runs WHERE run_id = ?", [run_id]).fetchone()[0]
        payload = json.dumps(details or {}, ensure_ascii=False, default=str)
        if exists:
            conn.execute(
                "UPDATE meta.pipeline_runs SET status = ?, finished_at = ?, details_json = ?, error_message = ? "
                "WHERE run_id = ?", [status, now_utc(), payload, error, run_id])
        else:
            conn.execute("INSERT INTO meta.pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         [run_id, command, status, now_utc(), None if status == "RUNNING" else now_utc(),
                          settings.as_of.isoformat(), payload, error])


def _as_dict(r: CheckResult) -> dict[str, Any]:
    return {"check_id": r.check.check_id, "table": r.check.table, "severity": r.check.severity,
            "observed": r.observed, "status": r.status, "description": r.check.description}


def refresh(database: Path | str, settings: Settings, contract: ContractCatalog, *,
            run_id: str | None = None, lock_timeout: float = 10.0) -> RefreshReport:
    run_id = run_id or new_run_id("refresh")
    report = RefreshReport(run_id=run_id, status="RUNNING")
    saved_rejects: list[tuple] = []
    try:
        with transaction(database, lock_timeout=lock_timeout, owner_id=f"pipeline-refresh-{run_id}") as conn:
            conn.execute("SET preserve_insertion_order = false")
            ensure_pipeline_metadata(conn)
            stg_results = build_stg(conn, contract, run_id)
            report.stg_rows = {r.table: r.stg_rows for r in stg_results}
            report.stg_rejects = {r.table: r.rejected_rows for r in stg_results if r.rejected_rows}
            report.core_rows = build_core(conn, settings)
            report.mart_rows = build_base_marts(conn)
            report.model_marts = build_model_marts(conn)
            results = stg_row_checks(stg_results) + run_checks(conn, build_checks(settings, stg_key_map(contract), run_id))
            report.checks = [_as_dict(r) for r in results]
            write_report(conn, run_id, results)
            if report.failed:
                saved_rejects = conn.execute("SELECT * FROM meta.stg_rejects WHERE run_id = ?", [run_id]).fetchall()
                ids = ", ".join(c["check_id"] for c in report.failed)
                raise RefreshFailed(f"Kiểm tra ERROR thất bại: {ids} – dữ liệu cũ được giữ nguyên", results)
    except RefreshFailed as exc:
        report.status = "FAILED"
        with transaction(database, lock_timeout=lock_timeout, owner_id=f"pipeline-dq-log-{run_id}") as conn:
            ensure_pipeline_metadata(conn)
            write_report(conn, run_id, exc.results)
            if saved_rejects:
                conn.executemany("INSERT INTO meta.stg_rejects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", saved_rejects)
        return report
    report.status = "SUCCESS"
    return report


def run_refresh_logged(database: Path | str, settings: Settings, contract: ContractCatalog, *,
                       command: str = "refresh", lock_timeout: float = 10.0) -> RefreshReport:
    """Refresh + ghi meta.pipeline_runs (RUNNING → SUCCESS/FAILED). Dùng chung cho CLI và nút trên dashboard."""
    run_id = new_run_id(command)
    record_run(database, run_id, command, "RUNNING", settings, lock_timeout=lock_timeout)
    try:
        report = refresh(database, settings, contract, run_id=run_id, lock_timeout=lock_timeout)
    except Exception as exc:  # noqa: BLE001
        record_run(database, run_id, command, "FAILED", settings, error=f"{type(exc).__name__}: {exc}",
                   lock_timeout=lock_timeout)
        raise
    details = {"stg_rows": report.stg_rows, "core_rows": report.core_rows, "mart_rows": report.mart_rows,
               "fail": [c["check_id"] for c in report.failed], "warn": [c["check_id"] for c in report.warned]}
    record_run(database, run_id, command, report.status, settings, details=details,
               error=None if report.status == "SUCCESS" else "DQ ERROR: " + ", ".join(details["fail"]),
               lock_timeout=lock_timeout)
    return report
