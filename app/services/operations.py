"""Adapter giữa giao diện Streamlit và backend DE cho nhập liệu, undo, refresh, trạng thái (D01, D02, M9).

Nguyên tắc:
  * Mọi hàm gọi require_admin (1 tài khoản chung admin_local – D14).
  * Đọc: mở kết nối DuckDB read-only rồi đóng ngay (không giữ kết nối khi người dùng thao tác).
  * Ghi (upload, undo, refresh): dùng writer lock + transaction của src/db/duckdb.py; kho bận → WriterLockTimeout
    để giao diện báo "Hệ thống đang bận – chưa ghi gì".
  * Không chạy mô hình từ giao diện (mô hình chạy bằng lệnh `python -m pipeline.run models`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

from src.config.settings import Settings, load_settings
from src.config.source_registry import BusinessContract, ContractCatalog, load_contract
from src.db.duckdb import DEFAULT_DATABASE, WriterLockTimeout, connection
from src.db.pipeline_metadata import table_exists
from src.entry.validate import UploadReport, column_guide, table_by_name, template_csv, validate_upload
from src.entry.write import EntryError, batch_history, undo_batch, write_upload
from src.transform.refresh import RefreshReport, run_refresh_logged

__all__ = ["EntryError", "WriterLockTimeout", "OperationsService"]


def _require_admin() -> object:
    from app.auth import require_admin

    return require_admin()


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def _contract() -> ContractCatalog:
    return load_contract()


class OperationsService:
    def __init__(self, database: str | Path = DEFAULT_DATABASE) -> None:
        self.database = Path(database)
        self.settings = _settings()
        self.contract = _contract()

    # ---------------------------------------------------------------- danh mục bảng
    def tables(self) -> list[tuple[str, str]]:
        """[(tên ngắn, nhãn hiển thị)] cho ô chọn bảng – 14/14 bảng (D13)."""
        out = []
        for qualified, table in sorted(self.contract.tables.items()):
            tag = " · kịch bản giả định" if table.source_type == "ASSUMED" else ""
            out.append((table.table, f"{qualified}{tag}"))
        return out

    def table(self, name: str) -> BusinessContract:
        return table_by_name(self.contract, name)

    def guide(self, name: str) -> pd.DataFrame:
        _require_admin()
        return column_guide(self.table(name))

    def template(self, name: str, example_rows: int = 0) -> bytes:
        _require_admin()
        if example_rows and self.database.is_file():
            try:
                with connection(self.database) as conn:
                    return template_csv(self.table(name), conn, example_rows)
            except duckdb.Error:
                pass
        return template_csv(self.table(name))

    # ---------------------------------------------------------------- nhập liệu
    def validate(self, name: str, raw: bytes, file_name: str) -> UploadReport:
        _require_admin()
        table = self.table(name)
        if not self.database.is_file():
            return validate_upload(raw, file_name, table, self.settings, None)
        with connection(self.database) as conn:
            return validate_upload(raw, file_name, table, self.settings, conn)

    def write(self, name: str, report: UploadReport, operator: str, reason: str) -> dict:
        _require_admin()
        return write_upload(self.database, self.contract, self.table(name), report, operator=operator, reason=reason,
                            lock_timeout=self.settings.lock_timeout_seconds)

    def undo(self, batch_id: str, operator: str, reason: str) -> dict:
        _require_admin()
        return undo_batch(self.database, batch_id, operator=operator, reason=reason,
                          lock_timeout=self.settings.lock_timeout_seconds)

    def refresh(self) -> RefreshReport:
        _require_admin()
        return run_refresh_logged(self.database, self.settings, self.contract, command="ui-refresh",
                                  lock_timeout=self.settings.lock_timeout_seconds)

    # ---------------------------------------------------------------- đọc trạng thái
    def _read(self, sql: str, params: list | None = None, needs: tuple[str, str] = ("meta", "pipeline_runs")) -> pd.DataFrame:
        if not self.database.is_file():
            return pd.DataFrame()
        with connection(self.database) as conn:
            if not table_exists(conn, *needs):
                return pd.DataFrame()
            return conn.execute(sql, params or []).df()

    def batches(self) -> pd.DataFrame:
        _require_admin()
        if not self.database.is_file():
            return pd.DataFrame()
        with connection(self.database) as conn:
            if not table_exists(conn, "meta", "entry_log") or not table_exists(conn, "meta", "pipeline_runs"):
                return pd.DataFrame()
            return batch_history(conn)

    def batch_rows(self, batch_id: str, limit: int = 500) -> pd.DataFrame:
        _require_admin()
        row = self._read("SELECT table_name FROM meta.table_loads WHERE batch_id = ?", [batch_id], ("meta", "table_loads"))
        if row.empty:
            return pd.DataFrame()
        schema, table = str(row.iloc[0, 0]).split(".", 1)
        if f"{schema}.{table}" not in self.contract.tables:
            return pd.DataFrame()
        return self._read(f'SELECT * FROM "{schema}"."{table}" WHERE _batch_id = ? LIMIT {int(limit)}', [batch_id],
                          (schema, table))

    def pending_refresh(self) -> int:
        df = self._read("""SELECT count(*) AS n FROM meta.v_batch_current WHERE batch_type = 'UPLOAD'
                           AND status_at > COALESCE((SELECT max(finished_at) FROM meta.pipeline_runs
                           WHERE command IN ('refresh','init','all','ui-refresh') AND status = 'SUCCESS'), '')""")
        return int(df.iloc[0, 0]) if not df.empty else 0

    def pipeline_runs(self, limit: int = 15) -> pd.DataFrame:
        return self._read(f"""SELECT started_at, command, status, finished_at, error_message
                              FROM meta.pipeline_runs ORDER BY started_at DESC LIMIT {int(limit)}""")

    def quality_report(self) -> pd.DataFrame:
        return self._read("""SELECT check_id, table_name, severity, observed, status, description FROM meta.quality_report
                             WHERE run_id = (SELECT run_id FROM meta.pipeline_runs
                                             WHERE command IN ('refresh','init','all','ui-refresh')
                                             ORDER BY started_at DESC LIMIT 1)
                             ORDER BY CASE status WHEN 'FAIL' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END, check_id""",
                          needs=("meta", "quality_report"))

    def model_runs(self) -> pd.DataFrame:
        return self._read("""SELECT bt_id, mode, status, runtime_sec, finished_at, model_version, params_source, error_message
                             FROM (SELECT *, row_number() OVER (PARTITION BY bt_id ORDER BY started_at DESC) AS rn
                                   FROM meta.model_runs WHERE bt_id NOT LIKE '%:%') WHERE rn = 1 ORDER BY bt_id""",
                          needs=("meta", "model_runs"))
