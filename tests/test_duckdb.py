"""V4 DuckDB safety tests; every write targets pytest temporary paths."""

from pathlib import Path
import subprocess
import sys
import time

import duckdb
import pytest

from src.db.duckdb import (
    DEFAULT_DATABASE,
    NestedTransactionError,
    UnsafeWriteError,
    WriterLockTimeout,
    backup_database,
    connection,
    initialize_database,
    resolve_database,
    transaction,
)
from src.db.duckdb_metadata import (
    METADATA_COMPONENT,
    MetadataVersionError,
    initialize_metadata,
    metadata_status,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOLDER_CODE = """
import sys
from src.db.duckdb import transaction
with transaction(sys.argv[1], lock_timeout=5, owner_id='pytest-holder') as conn:
    conn.execute('INSERT INTO probe VALUES (1)')
    print('LOCKED', flush=True)
    sys.stdin.readline()
"""


def start_holder(database: Path) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-c", HOLDER_CODE, str(database)],
        cwd=PROJECT_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "LOCKED"
    return process


def release_holder(process: subprocess.Popen) -> tuple[str, str]:
    assert process.stdin is not None
    process.stdin.write("release\n")
    process.stdin.flush()
    return process.communicate(timeout=10)


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


def test_default_database_comes_from_v4_settings():
    assert DEFAULT_DATABASE == (PROJECT_ROOT / "data" / "warehouse" / "rohlik.duckdb").resolve()


def test_task08a_database_is_protected_from_v4_writes(tmp_path, monkeypatch):
    import src.db.duckdb as module

    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    protected = tmp_path / "data" / "warehouse" / "rohlik_bootstrap_dev.duckdb"
    with pytest.raises(UnsafeWriteError, match="protected Task08A"):
        initialize_database(protected)
    assert not protected.exists()


def test_query_parameters_and_connection_closed(database):
    with connection(database) as conn:
        assert conn.execute("SELECT 42").fetchone() == (42,)
        value = "'); DROP TABLE probe; --"
        assert conn.execute("SELECT ?", (value,)).fetchone() == (value,)
    with pytest.raises(duckdb.ConnectionException):
        conn.execute("SELECT 42")


def test_read_only_after_writer_closes(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    with connection(database, read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM probe").fetchone() == (0,)
        with pytest.raises(duckdb.InvalidInputException):
            conn.execute("INSERT INTO probe VALUES (1)")


def test_direct_writable_connection_is_blocked(database):
    with pytest.raises(UnsafeWriteError, match="use transaction"):
        with connection(database, read_only=False):
            pass


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


def test_connection_does_not_create_missing_file(tmp_path):
    path = tmp_path / "missing.duckdb"
    with pytest.raises(FileNotFoundError):
        with connection(path):
            pass
    with pytest.raises(UnsafeWriteError):
        with connection(path, read_only=False):
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


def test_safe_backup_is_unique_verified_and_reopens(database, tmp_path):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
        conn.execute("INSERT INTO probe VALUES (?)", (42,))
    source_before = database.read_bytes()
    first = backup_database(database, backup_directory=tmp_path / "backups")
    second = backup_database(database, backup_directory=tmp_path / "backups")
    first_path = Path(first["backup_path"])
    second_path = Path(second["backup_path"])
    assert first["verified"] is second["verified"] is True
    assert first_path != second_path
    assert first_path.read_bytes() == second_path.read_bytes() == source_before
    assert database.read_bytes() == source_before
    with connection(first_path) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(42,)]


def test_nested_transaction_is_blocked_and_outer_commits(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
        with pytest.raises(NestedTransactionError):
            with transaction(database):
                pass
        conn.execute("INSERT INTO probe VALUES (42)")
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(42,)]


def test_lock_released_after_python_failure(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    with pytest.raises(RuntimeError, match="fail inside writer"):
        with transaction(database, lock_timeout=0.2) as conn:
            conn.execute("INSERT INTO probe VALUES (1)")
            raise RuntimeError("fail inside writer")
    with transaction(database, lock_timeout=0.2) as conn:
        conn.execute("INSERT INTO probe VALUES (2)")
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(2,)]


def test_cross_process_lock_timeout(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    holder = start_holder(database)
    contender_code = """
import sys
from src.db.duckdb import WriterLockTimeout, transaction
try:
    with transaction(sys.argv[1], lock_timeout=0.2):
        pass
except WriterLockTimeout as exc:
    print(type(exc).__name__)
    raise SystemExit(0)
raise SystemExit(3)
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", contender_code, str(database)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "WriterLockTimeout" in result.stdout
    finally:
        stdout, stderr = release_holder(holder)
        assert holder.returncode == 0, stdout + stderr


def test_two_competing_writer_processes_are_serialized(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    holder = start_holder(database)
    contender_code = """
import sys
from src.db.duckdb import transaction
with transaction(sys.argv[1], lock_timeout=5, owner_id='pytest-contender') as conn:
    conn.execute('INSERT INTO probe VALUES (2)')
print('DONE')
"""
    contender = subprocess.Popen(
        [sys.executable, "-c", contender_code, str(database)],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.25)
    assert contender.poll() is None
    holder_stdout, holder_stderr = release_holder(holder)
    assert holder.returncode == 0, holder_stdout + holder_stderr
    contender_stdout, contender_stderr = contender.communicate(timeout=10)
    assert contender.returncode == 0, contender_stdout + contender_stderr
    assert "DONE" in contender_stdout
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe ORDER BY value").fetchall() == [(1,), (2,)]


def test_process_termination_releases_lock_and_rolls_back(database):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    holder = start_holder(database)
    holder.kill()
    holder.communicate(timeout=10)
    with transaction(database, lock_timeout=2) as conn:
        conn.execute("INSERT INTO probe VALUES (3)")
    with connection(database) as conn:
        assert conn.execute("SELECT * FROM probe").fetchall() == [(3,)]


def test_backup_refuses_active_writer(database, tmp_path):
    with transaction(database) as conn:
        conn.execute("CREATE TABLE probe (value INTEGER)")
    holder = start_holder(database)
    try:
        with pytest.raises(WriterLockTimeout):
            backup_database(
                database,
                backup_directory=tmp_path / "backups",
                lock_timeout=0.2,
            )
        assert not (tmp_path / "backups").exists()
    finally:
        stdout, stderr = release_holder(holder)
        assert holder.returncode == 0, stdout + stderr


def test_metadata_initialization_is_idempotent_and_preserves_records(database):
    first = initialize_metadata(database)
    assert first["created"] is True
    with transaction(database) as conn:
        conn.execute("INSERT INTO meta.source_batches VALUES (?, ?, ?, ?, ?, ?, now(), NULL, ?, NULL)",
                     ["batch-1", "orders", "data/raw/orders/train.csv", "abc", 4, "PLANNED", 7])
    second = initialize_metadata(database)
    assert second["created"] is False
    status = metadata_status(database)
    assert status["initialized"] is True
    assert status["component"] == METADATA_COMPONENT
    with connection(database) as conn:
        assert conn.execute("SELECT batch_id FROM meta.source_batches").fetchall() == [("batch-1",)]
        assert conn.execute("SELECT count(*) FROM meta.schema_versions").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='meta'").fetchone() == (5,)


def test_metadata_unknown_version_is_blocked_without_replacement(database):
    initialize_metadata(database)
    with transaction(database) as conn:
        conn.execute(
            "UPDATE meta.schema_versions SET version = 99 WHERE component = ?",
            [METADATA_COMPONENT],
        )
    with pytest.raises(MetadataVersionError, match="explicit reviewed migration"):
        initialize_metadata(database)
    with connection(database) as conn:
        assert conn.execute(
            "SELECT version FROM meta.schema_versions WHERE component = ?", [METADATA_COMPONENT]
        ).fetchone() == (99,)


@pytest.mark.parametrize("unsafe", ["../escape.duckdb", "data/raw/forbidden.duckdb", "wrong.db"])
def test_unsafe_database_paths_are_rejected(unsafe):
    with pytest.raises((RuntimeError, ValueError)):
        resolve_database(unsafe)


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
