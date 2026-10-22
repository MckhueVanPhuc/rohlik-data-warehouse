"""Safe local DuckDB connections, cross-process writer coordination and backups."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import threading
import time
from typing import BinaryIO
from uuid import uuid4

import duckdb
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_BACKUP_DIRECTORY = PROJECT_ROOT / "data" / "backups" / "duckdb"
DEFAULT_LOCK_TIMEOUT = 10.0


class DuckDBSafetyError(RuntimeError):
    """Base error for rejected unsafe DuckDB operations."""


class WriterLockTimeout(DuckDBSafetyError):
    """The shared writer lock was not acquired within its bounded wait."""


class UnsafeWriteError(DuckDBSafetyError):
    """A caller attempted to bypass the shared writer service."""


class NestedTransactionError(DuckDBSafetyError):
    """Nested writer transactions are intentionally unsupported."""


class BackupError(DuckDBSafetyError):
    """A database could not be backed up and verified safely."""


def _configured_database(settings_path: Path = DEFAULT_SETTINGS) -> Path:
    """Read the V4 warehouse path and constrain it to data/warehouse under root."""
    try:
        settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DuckDBSafetyError(f"Cannot read DuckDB settings {settings_path}: {exc}") from exc
    warehouse = settings.get("warehouse") if isinstance(settings, dict) else None
    if not isinstance(warehouse, str) or not warehouse:
        raise DuckDBSafetyError("config/settings.yaml must define a non-empty warehouse path")
    relative = PurePosixPath(warehouse)
    if ("\\" in warehouse or relative.is_absolute() or PureWindowsPath(warehouse).drive
            or ".." in relative.parts):
        raise DuckDBSafetyError(f"Unsafe configured warehouse path: {warehouse}")
    resolved = (PROJECT_ROOT / warehouse).resolve()
    warehouse_root = (PROJECT_ROOT / "data" / "warehouse").resolve()
    if resolved.suffix.lower() != ".duckdb" or not resolved.is_relative_to(warehouse_root):
        raise DuckDBSafetyError("Configured warehouse must be a .duckdb file under data/warehouse")
    return resolved


DEFAULT_DATABASE = _configured_database()


def resolve_database(path: str | Path = DEFAULT_DATABASE) -> Path:
    """Resolve a database without allowing relative traversal or raw-data targets."""
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        posix = PurePosixPath(str(path).replace("\\", "/"))
        if PureWindowsPath(str(path)).drive or ".." in posix.parts:
            raise DuckDBSafetyError(f"Unsafe relative DuckDB path: {path}")
        resolved = (PROJECT_ROOT / candidate).resolve()
        if not resolved.is_relative_to(PROJECT_ROOT.resolve()):
            raise DuckDBSafetyError(f"DuckDB path escapes project root: {path}")
    if resolved.suffix.lower() != ".duckdb":
        raise DuckDBSafetyError(f"DuckDB path must use the .duckdb suffix: {resolved}")
    raw_root = (PROJECT_ROOT / "data" / "raw").resolve()
    if resolved.is_relative_to(raw_root):
        raise DuckDBSafetyError(f"DuckDB path cannot be inside raw data: {resolved}")
    return resolved


def _ensure_writable_target(database: Path) -> None:
    protected = {
        (PROJECT_ROOT / "data" / "warehouse" / "rohlik_bootstrap_dev.duckdb").resolve(),
    }
    if database in protected:
        raise UnsafeWriteError(f"V4 writer service refuses the protected legacy bootstrap database: {database}")


def _lock_path(database: Path) -> Path:
    return database.with_name(database.name + ".writer.lock")


_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[Path, threading.Lock] = {}
_ACTIVE_TRANSACTION: ContextVar[bool] = ContextVar("duckdb_active_transaction", default=False)


def _local_lock(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(path, threading.Lock())


def _try_os_lock(stream: BinaryIO) -> bool:
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        return False
    return True


def _unlock_os(stream: BinaryIO) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _owner_hint(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return "owner metadata unavailable"
    return value or "owner metadata unavailable"


@contextmanager
def writer_lock(
    path: str | Path = DEFAULT_DATABASE,
    *,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
    owner_id: str | None = None,
) -> Iterator[Path]:
    """Acquire the one-writer lock shared by CLI and future Streamlit services.

    The OS releases the byte-range lock when the handle/process terminates. A stale
    lock file is diagnostic metadata and is never force-unlocked or deleted.
    """
    if timeout < 0:
        raise ValueError("Writer lock timeout cannot be negative")
    database = resolve_database(path)
    lock_path = _lock_path(database)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    local = _local_lock(lock_path)
    if not local.acquire(timeout=max(0.0, timeout)):
        raise WriterLockTimeout(
            f"Timed out after {timeout:.3f}s waiting for DuckDB writer lock {lock_path}"
        )
    stream: BinaryIO | None = None
    acquired = False
    try:
        stream = lock_path.open("a+b")
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        while not _try_os_lock(stream):
            if time.monotonic() >= deadline:
                raise WriterLockTimeout(
                    f"Timed out after {timeout:.3f}s waiting for DuckDB writer lock {lock_path}; "
                    f"last owner metadata: {_owner_hint(lock_path)}"
                )
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        acquired = True
        owner = {
            "owner_id": owner_id or f"pid-{os.getpid()}-{uuid4().hex}",
            "pid": os.getpid(),
            "database": str(database),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps(owner, sort_keys=True).encode("utf-8"))
        stream.flush()
        yield database
    finally:
        if stream is not None:
            if acquired:
                _unlock_os(stream)
            stream.close()
        local.release()


@contextmanager
def _connection(path: Path, *, read_only: bool) -> Iterator[duckdb.DuckDBPyConnection]:
    conn = duckdb.connect(str(path), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def connection(
    path: str | Path = DEFAULT_DATABASE, *, read_only: bool = True,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open an existing database read-only and always close it.

    ``read_only=False`` remains in the signature for a clear migration error, but
    writable callers must use :func:`transaction` so the process lock cannot be bypassed.
    """
    if not read_only:
        raise UnsafeWriteError("Direct writable connections are blocked; use transaction()")
    database = resolve_database(path)
    if not database.is_file():
        raise FileNotFoundError(f"DuckDB database not found: {database}; run explicit initialization first")
    with _connection(database, read_only=True) as conn:
        yield conn


@contextmanager
def transaction(
    path: str | Path = DEFAULT_DATABASE,
    *,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    owner_id: str | None = None,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Run one short write transaction under the shared cross-process lock."""
    if _ACTIVE_TRANSACTION.get():
        raise NestedTransactionError("Nested DuckDB transactions are blocked")
    database = resolve_database(path)
    _ensure_writable_target(database)
    if not database.is_file():
        raise FileNotFoundError(f"DuckDB database not found: {database}; initialize it explicitly first")
    with writer_lock(database, timeout=lock_timeout, owner_id=owner_id):
        token = _ACTIVE_TRANSACTION.set(True)
        try:
            with _connection(database, read_only=False) as conn:
                conn.execute("BEGIN TRANSACTION")
                try:
                    yield conn
                    conn.commit()
                except BaseException:
                    try:
                        conn.rollback()
                    except duckdb.Error:
                        pass
                    raise
        finally:
            _ACTIVE_TRANSACTION.reset(token)


def initialize_database(
    path: str | Path = DEFAULT_DATABASE, *, lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> dict[str, str | bool]:
    """Explicitly create an empty DuckDB if missing; never replace an existing file."""
    database = resolve_database(path)
    _ensure_writable_target(database)
    with writer_lock(database, timeout=lock_timeout, owner_id="database-initializer"):
        existed = database.exists()
        if existed and not database.is_file():
            raise DuckDBSafetyError(f"DuckDB target exists but is not a file: {database}")
        if not existed:
            database.parent.mkdir(parents=True, exist_ok=True)
            with _connection(database, read_only=False):
                pass
        with _connection(database, read_only=True) as conn:
            version = conn.execute("SELECT version()").fetchone()[0]
            if conn.execute("SELECT 42").fetchone() != (42,):
                raise RuntimeError("DuckDB verification failed: unexpected query result")
    return {"database_path": str(database), "duckdb_version": version, "created": not existed}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_directory(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    resolved = (PROJECT_ROOT / candidate).resolve()
    allowed = (PROJECT_ROOT / "data" / "backups").resolve()
    if not resolved.is_relative_to(allowed):
        raise BackupError("Relative DuckDB backup directories must be under data/backups")
    return resolved


def backup_database(
    path: str | Path = DEFAULT_DATABASE,
    *,
    backup_directory: str | Path = DEFAULT_BACKUP_DIRECTORY,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> dict[str, str | int | bool]:
    """Copy a closed/checkpointed database under the shared lock and verify the copy."""
    database = resolve_database(path)
    if not database.is_file():
        raise FileNotFoundError(f"DuckDB database not found: {database}")
    directory = _backup_directory(backup_directory)
    with writer_lock(database, timeout=lock_timeout, owner_id="database-backup"):
        wal = Path(str(database) + ".wal")
        if wal.exists():
            raise BackupError(f"Refusing backup while DuckDB WAL exists: {wal}")
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = directory / f"{database.stem}_{stamp}_{uuid4().hex}.duckdb"
        created = False
        try:
            with _connection(database, read_only=True) as source_conn:
                source_version = source_conn.execute("SELECT version()").fetchone()[0]
                source_tables = source_conn.execute("SELECT count(*) FROM duckdb_tables()").fetchone()[0]
                source_hash_before = _sha256(database)
                with database.open("rb") as source, backup.open("xb") as destination:
                    created = True
                    shutil.copyfileobj(source, destination)
                source_hash_after = _sha256(database)
                if source_hash_before != source_hash_after:
                    raise BackupError("Source database changed during backup")
            backup_hash = _sha256(backup)
            if backup_hash != source_hash_before or backup.stat().st_size != database.stat().st_size:
                raise BackupError("Backup byte verification failed")
            with _connection(backup, read_only=True) as backup_conn:
                backup_version = backup_conn.execute("SELECT version()").fetchone()[0]
                backup_tables = backup_conn.execute("SELECT count(*) FROM duckdb_tables()").fetchone()[0]
            if backup_version != source_version or backup_tables != source_tables:
                raise BackupError("Backup reopen/catalog verification failed")
        except BaseException:
            if created and backup.exists():
                backup.unlink()
            raise
    return {
        "source_path": str(database),
        "backup_path": str(backup),
        "sha256": backup_hash,
        "size_bytes": backup.stat().st_size,
        "verified": True,
    }
