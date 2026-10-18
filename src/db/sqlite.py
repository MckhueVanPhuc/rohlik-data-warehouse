"""Short-lived SQLite connections and explicit transactions.

Initialize once before starting the application. Pass values to execute() using
placeholders, e.g. connection.execute("SELECT ?", (value,)).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "input.db"
BUSY_TIMEOUT_MS = 5000


def resolve_database(path: str | Path = DEFAULT_DATABASE) -> Path:
    """Resolve relative paths against the project root, never the current cwd."""
    candidate = Path(path).expanduser()
    return (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()


@contextmanager
def connection(path: str | Path = DEFAULT_DATABASE) -> Iterator[sqlite3.Connection]:
    """Open an existing database; configure each connection and always close it.

    Autocommit keeps reads short. Use transaction() for atomic writes. Opening
    does not create a missing database or change its persistent journal mode.
    """
    database = resolve_database(path)
    conn = sqlite3.connect(database.as_uri() + "?mode=rw", isolation_level=None,
                           timeout=BUSY_TIMEOUT_MS / 1000, uri=True)
    try:
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(path: str | Path = DEFAULT_DATABASE) -> Iterator[sqlite3.Connection]:
    """Commit an explicit transaction on success, rollback on any exception.

    Do not manually commit/rollback or use executescript inside this scope.
    Each invocation owns a separate connection; keep the scope short.
    """
    with connection(path) as conn:
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def verify_connection(conn: sqlite3.Connection) -> dict[str, str | int]:
    """Read and validate required settings on the supplied connection."""
    settings = {
        "sqlite_version": sqlite3.sqlite_version,
        "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        "busy_timeout": conn.execute("PRAGMA busy_timeout").fetchone()[0],
        "foreign_keys": conn.execute("PRAGMA foreign_keys").fetchone()[0],
    }
    if (settings["journal_mode"] != "wal"
            or settings["busy_timeout"] != BUSY_TIMEOUT_MS
            or settings["foreign_keys"] != 1):
        raise RuntimeError(f"Unexpected SQLite settings: {settings}")
    return settings


def initialize_database(path: str | Path = DEFAULT_DATABASE) -> dict[str, str | int]:
    """Create if absent and enable WAL during maintenance, without creating tables.

    Stop application connections before initial WAL configuration. Existing
    databases are opened in place and never replaced or truncated.
    """
    database = resolve_database(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting an existing file, including races.
    try:
        with database.open("xb"):
            pass
    except FileExistsError:
        pass
    with connection(database) as conn:
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            conn.execute("PRAGMA journal_mode=WAL")
        settings = verify_connection(conn)
        conn.execute("SELECT 42").fetchone()
    return {"database_path": str(database), **settings}
