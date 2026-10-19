"""Read-only Streamlit infrastructure smoke test for Rohlik Decision Hub."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys

import duckdb
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SQLITE_DATABASE = PROJECT_ROOT / "data" / "input.db"
DUCKDB_DATABASE = PROJECT_ROOT / "data" / "warehouse" / "rohlik.duckdb"
STREAMLIT_CONFIG = PROJECT_ROOT / ".streamlit" / "config.toml"
VALID_STATUSES = frozenset({"PASS", "FAIL", "NOT_AVAILABLE", "BLOCKED"})


@dataclass(frozen=True)
class CheckResult:
    """A normalized infrastructure check result suitable for tests and UI."""

    status: str
    exists: bool
    value: int | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Unsupported check status: {self.status}")


def python_runtime() -> str:
    """Return the active Python version without shelling out."""
    return sys.version.split()[0]


def streamlit_runtime() -> str:
    """Return the imported Streamlit version."""
    return st.__version__


def _blocked_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(term in message for term in ("lock", "busy", "used by another process"))


def check_sqlite(path: str | Path = SQLITE_DATABASE) -> CheckResult:
    """Run SELECT 42 through a read-only SQLite URI; never create a missing file."""
    database = Path(path).resolve()
    if not database.is_file():
        return CheckResult("NOT_AVAILABLE", False, detail=f"Database missing: {database}")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{database.as_uri()}?mode=ro", uri=True, timeout=1.0, isolation_level=None
        )
        row = connection.execute("SELECT 42").fetchone()
        if row != (42,):
            return CheckResult("FAIL", True, detail=f"Unexpected SELECT 42 result: {row!r}")
        return CheckResult("PASS", True, value=42, detail="Read-only connection succeeded.")
    except (sqlite3.Error, OSError) as exc:
        status = "BLOCKED" if _blocked_error(exc) else "FAIL"
        return CheckResult(status, True, detail=f"Read-only connection failed: {exc}")
    finally:
        if connection is not None:
            connection.close()


def check_duckdb(path: str | Path = DUCKDB_DATABASE) -> CheckResult:
    """Run SELECT 42 using an explicitly read-only DuckDB connection."""
    database = Path(path).resolve()
    if not database.is_file():
        return CheckResult("NOT_AVAILABLE", False, detail=f"Database missing: {database}")
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = duckdb.connect(str(database), read_only=True)
        row = connection.execute("SELECT 42").fetchone()
        if row != (42,):
            return CheckResult("FAIL", True, detail=f"Unexpected SELECT 42 result: {row!r}")
        return CheckResult("PASS", True, value=42, detail="Read-only connection succeeded.")
    except (duckdb.Error, OSError) as exc:
        status = "BLOCKED" if _blocked_error(exc) else "FAIL"
        return CheckResult(status, True, detail=f"Read-only connection failed: {exc}")
    finally:
        if connection is not None:
            connection.close()


def _show_database_result(label: str, result: CheckResult) -> None:
    st.write(f"**Database:** {'EXISTS' if result.exists else 'MISSING'}")
    st.write(f"**Connection:** {result.status}")
    if result.status == "PASS":
        st.success(f"{label} SELECT 42 returned {result.value}.")
    elif result.status == "BLOCKED":
        st.warning(result.detail)
    elif result.status == "NOT_AVAILABLE":
        st.info(result.detail)
    else:
        st.error(result.detail)


def main() -> None:
    """Render the smoke test; all database operations remain read-only."""
    st.set_page_config(page_title="Rohlik Infrastructure Smoke Test", layout="centered")
    st.title("Rohlik Decision Hub – Infrastructure Smoke Test")

    st.header("1 – Runtime Environment")
    config_ok = STREAMLIT_CONFIG.is_file()
    st.write(f"**Python Version:** {python_runtime()}")
    st.write(f"**Streamlit Version:** {streamlit_runtime()}")
    st.write("**Application Mode:** Infrastructure Test")
    st.write("**Database operation mode:** Read-only")
    st.write(f"**Project Configuration:** {'PASS' if config_ok else 'FAIL'}")

    sqlite_result = check_sqlite()
    st.header("2 – SQLite Connectivity")
    _show_database_result("SQLite", sqlite_result)

    duckdb_result = check_duckdb()
    st.header("3 – DuckDB Connectivity")
    _show_database_result("DuckDB", duckdb_result)

    st.header("4 – Infrastructure Summary")
    st.table(
        {
            "Component": ["Python Environment", "Streamlit Runtime", "SQLite Connection", "DuckDB Connection"],
            "Status": ["PASS", "PASS", sqlite_result.status, duckdb_result.status],
        }
    )


if __name__ == "__main__":
    main()
