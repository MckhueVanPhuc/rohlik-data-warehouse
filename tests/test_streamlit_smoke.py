from pathlib import Path
import sqlite3

import duckdb
import pytest

import app_smoke


def test_python_runtime_matches_active_interpreter():
    assert app_smoke.python_runtime()
    assert app_smoke.python_runtime().count(".") >= 1


def test_streamlit_version_is_detected():
    assert app_smoke.streamlit_runtime() == app_smoke.st.__version__


def test_sqlite_database_exists_and_connects_read_only(tmp_path):
    database = tmp_path / "test.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE marker (value INTEGER)")
    before = database.stat().st_size
    result = app_smoke.check_sqlite(database)
    assert result == app_smoke.CheckResult("PASS", True, 42, "Read-only connection succeeded.")
    assert database.stat().st_size == before


def test_sqlite_missing_is_not_created(tmp_path):
    database = tmp_path / "missing.db"
    result = app_smoke.check_sqlite(database)
    assert result.status == "NOT_AVAILABLE"
    assert result.exists is False
    assert not database.exists()


def test_sqlite_connection_error_is_reported(tmp_path, monkeypatch):
    database = tmp_path / "invalid.db"
    database.write_bytes(b"not sqlite")
    result = app_smoke.check_sqlite(database)
    assert result.status == "FAIL"
    assert "failed" in result.detail.lower()


def test_duckdb_database_exists_and_connects_read_only(tmp_path):
    database = tmp_path / "test.duckdb"
    duckdb.connect(str(database)).close()
    before = database.stat().st_size
    result = app_smoke.check_duckdb(database)
    assert result.status == "PASS"
    assert result.value == 42
    assert database.stat().st_size == before


def test_duckdb_missing_is_not_created(tmp_path):
    database = tmp_path / "missing.duckdb"
    result = app_smoke.check_duckdb(database)
    assert result.status == "NOT_AVAILABLE"
    assert not database.exists()


def test_duckdb_unavailable_or_locked_is_reported(tmp_path, monkeypatch):
    database = tmp_path / "test.duckdb"
    database.touch()

    def locked(*args, **kwargs):
        raise duckdb.IOException("Could not set lock on file")

    monkeypatch.setattr(app_smoke.duckdb, "connect", locked)
    result = app_smoke.check_duckdb(database)
    assert result.status == "BLOCKED"
    assert "lock" in result.detail.lower()


def test_connection_failure_is_not_reported_as_pass(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    database.touch()

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(app_smoke.sqlite3, "connect", fail)
    assert app_smoke.check_sqlite(database).status == "FAIL"


def test_invalid_summary_status_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        app_smoke.CheckResult("SUCCESS", True)


def test_app_executes_with_streamlit_apptest():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(app_smoke.__file__))).run(timeout=10)
    assert not app.exception
    assert app.title[0].value == "Rohlik Decision Hub – Infrastructure Smoke Test"
    assert len(app.header) == 4
