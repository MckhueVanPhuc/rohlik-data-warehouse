"""Infrastructure tests: every write targets pytest's temporary directories."""

from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from src.db.backup import backup_database, integrity_check
from src.db.sqlite import connection, initialize_database, transaction


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "input.db"
    initialize_database(path)
    return path


def test_create_without_tables(tmp_path):
    path = tmp_path / "nested" / "input.db"
    initialize_database(path)
    assert path.is_file()
    with connection(path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_query_parameters_and_close(database):
    with connection(database) as conn:
        value = "'); DROP TABLE probe; --"
        assert conn.execute("SELECT ?", (value,)).fetchone() == (value,)
        assert conn.execute("SELECT 42").fetchone() == (42,)
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 42")


def test_wal_persists(database):
    conn = sqlite3.connect(database)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        conn.close()


def test_settings_on_each_new_connection(database):
    for _ in range(2):
        with connection(database) as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
            assert conn.execute("PRAGMA busy_timeout").fetchone() == (5000,)


def test_foreign_key_enforcement(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(database) as conn:
            conn.execute("INSERT INTO child VALUES (?)", (99,))


def test_commit(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value TEXT)")
        conn.execute("INSERT INTO probe VALUES (?)", ("committed",))
    with connection(database) as conn:
        assert conn.execute("SELECT value FROM probe").fetchall() == [("committed",)]


def test_rollback_including_ddl(database):
    with pytest.raises(ValueError, match="abort"):
        with transaction(database) as conn:
            conn.execute("CREATE TABLE probe (value TEXT)")
            conn.execute("INSERT INTO probe VALUES (?)", ("rollback",))
            raise ValueError("abort")
    with connection(database) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='probe'").fetchall() == []


def test_reinitialize_preserves_data(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
        conn.execute("INSERT INTO probe VALUES (?)", (42,))
    for _ in range(2):
        initialize_database(database)
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(42,)]


def test_multiple_connections_and_reader_during_write(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    with connection(database) as reader:
        with transaction(database) as writer:
            writer.execute("INSERT INTO probe VALUES (?)", (1,))
            assert reader.execute("SELECT * FROM probe").fetchall() == []
        assert reader.execute("SELECT * FROM probe").fetchall() == [(1,)]
        with transaction(database) as second_writer:
            second_writer.execute("INSERT INTO probe VALUES (?)", (2,))
        assert reader.execute("SELECT * FROM probe ORDER BY value").fetchall() == [(1,), (2,)]


def test_backup_wal_integrity_restore_and_unique_names(database, tmp_path):
    # Keep a connection open so committed data remains in the active WAL.
    with connection(database) as live:
        live.execute("PRAGMA wal_autocheckpoint=0")
        live.execute("CREATE TABLE probe (value TEXT)")
        live.execute("INSERT INTO probe VALUES (?)", ("snapshot",))
        assert Path(str(database) + "-wal").stat().st_size > 0
        first = backup_database(database, tmp_path / "backups")
        original = first.read_bytes()
        second = backup_database(database, tmp_path / "backups")
        assert first != second
        assert first.read_bytes() == original
        integrity_check(first)
        restored = tmp_path / "restored.db"
        source = sqlite3.connect(first)
        target = sqlite3.connect(restored)
        try:
            source.backup(target)
            assert target.execute("SELECT * FROM probe").fetchall() == [("snapshot",)]
        finally:
            source.close()
            target.close()
        integrity_check(restored)


def test_missing_source_not_created(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        with connection(path):
            pass
    with pytest.raises(sqlite3.OperationalError):
        backup_database(path, tmp_path / "backups")
    assert not path.exists()
    assert list((tmp_path / "backups").iterdir()) == []


def test_corrupt_existing_file_not_replaced(tmp_path):
    path = tmp_path / "invalid.db"
    original = b"not a SQLite database"
    path.write_bytes(original)
    with pytest.raises(sqlite3.DatabaseError):
        initialize_database(path)
    assert path.read_bytes() == original
    with pytest.raises(sqlite3.DatabaseError):
        integrity_check(path)


def test_paths_independent_of_cwd(database, monkeypatch, tmp_path):
    import src.db.sqlite as module
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert module.resolve_database("input.db") == database
    with connection("input.db") as conn:
        assert conn.execute("SELECT 42").fetchone() == (42,)


def test_cli_success_and_failure(tmp_path):
    path = tmp_path / "cli.db"
    result = subprocess.run([sys.executable, "-m", "src.init_sqlite", "--database", str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SUCCESS" in result.stdout
    invalid = tmp_path / "invalid.db"
    invalid.write_bytes(b"invalid")
    result = subprocess.run([sys.executable, "-m", "src.init_sqlite", "--database", str(invalid)],
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "FAILED" in result.stdout
