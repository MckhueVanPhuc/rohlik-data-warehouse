"""DuckDB infrastructure tests; all writes use temporary databases."""

from pathlib import Path
import shutil
import subprocess
import sys

import duckdb
import pytest

from src.db.duckdb import connection, initialize_database, transaction


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse" / "test.duckdb"
    initialize_database(path)
    return path


def test_create_at_requested_path_without_tables(tmp_path):
    path = tmp_path / "nested" / "empty.duckdb"
    result = initialize_database(path)
    assert result["database_path"] == str(path.resolve())
    assert result["created"] is True
    assert path.is_file()
    with connection(path) as conn:
        assert conn.execute("SHOW TABLES").fetchall() == []
        assert conn.execute("SELECT schema_name FROM information_schema.schemata").fetchall()


def test_query_parameters_and_connection_closed(database):
    with connection(database) as conn:
        assert conn.execute("SELECT 42").fetchone() == (42,)
        value = "'); DROP TABLE probe; --"
        assert conn.execute("SELECT ?", (value,)).fetchone() == (value,)
    with pytest.raises(duckdb.ConnectionException):
        conn.execute("SELECT 42")


def test_read_only_after_writer_closes(database):
    with connection(database, read_only=False) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    with connection(database, read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM probe").fetchone() == (0,)
        with pytest.raises(duckdb.InvalidInputException):
            conn.execute("INSERT INTO probe VALUES (1)")


def test_commit(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
        conn.execute("INSERT INTO probe VALUES (?)", (42,))
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(42,)]


def test_rollback(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    with pytest.raises(ValueError, match="abort"):
        with transaction(database) as conn:
            conn.execute("INSERT INTO probe VALUES (?)", (42,))
            raise ValueError("abort")
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == []


def test_sql_error_rolls_back_and_releases_connection(database):
    with pytest.raises(duckdb.CatalogException):
        with transaction(database) as conn:
            conn.execute("CREATE TABLE probe (value INTEGER)")
            conn.execute("INSERT INTO missing_table VALUES (1)")
    with connection(database) as conn:
        assert conn.execute("SHOW TABLES").fetchall() == []


def test_reinitialize_preserves_bytes_and_data(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
        conn.execute("INSERT INTO probe VALUES (?)", (42,))
    original = database.read_bytes()
    for _ in range(2):
        assert initialize_database(database)["created"] is False
    assert database.read_bytes() == original
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(42,)]


def test_sequential_writer_reader_operations(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    for value in range(3):
        with transaction(database) as conn:
            conn.execute("INSERT INTO probe VALUES (?)", (value,))
        with connection(database) as conn:
            assert conn.execute("SELECT COUNT(*) FROM probe").fetchone() == (value + 1,)


@pytest.mark.parametrize("read_only", [True, False])
def test_connection_does_not_create_missing_file(tmp_path, read_only):
    path = tmp_path / "missing.duckdb"
    with pytest.raises(FileNotFoundError):
        with connection(path, read_only=read_only):
            pass
    assert not path.exists()


def test_invalid_existing_file_is_not_replaced(tmp_path):
    path = tmp_path / "invalid.duckdb"
    original = b"not a DuckDB database"
    path.write_bytes(original)
    with pytest.raises(duckdb.Error):
        initialize_database(path)
    assert path.read_bytes() == original


def test_relative_paths_ignore_cwd(tmp_path, monkeypatch):
    import src.db.duckdb as module
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = initialize_database("warehouse/test.duckdb")
    assert result["database_path"] == str(tmp_path / "warehouse" / "test.duckdb")
    with connection("warehouse/test.duckdb") as conn:
        assert conn.execute("SELECT 42").fetchone() == (42,)


def test_offline_backup_to_new_file(database, tmp_path):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
        conn.execute("INSERT INTO probe VALUES (?)", (42,))
    # Offline copy only: every connection has closed and no writer can start.
    assert not Path(str(database) + ".wal").exists()
    backup = tmp_path / "snapshot.duckdb"
    with database.open("rb") as source, backup.open("xb") as destination:
        shutil.copyfileobj(source, destination)
    with connection(backup) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(42,)]


def test_cli_success_repeat_and_failure(tmp_path):
    path = tmp_path / "cli.duckdb"
    command = [sys.executable, "-m", "src.init_duckdb", "--database", str(path)]
    for _ in range(2):
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "SUCCESS" in result.stdout
    path.write_bytes(b"invalid file")
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert path.read_bytes() == b"invalid file"
