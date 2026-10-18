"""Local DuckDB connections, with explicit opt-in for writes.

Use one DE writer process and sequential connection lifetimes. This module does
not coordinate concurrent processes or publish snapshots for Streamlit.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "warehouse" / "rohlik.duckdb"


def resolve_database(path: str | Path = DEFAULT_DATABASE) -> Path:
    """Resolve local database paths relative to the project, never the cwd."""
    candidate = Path(path).expanduser()
    return (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()


@contextmanager
def connection(
    path: str | Path = DEFAULT_DATABASE, *, read_only: bool = True,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open an existing file and always close; reads are the safe default.

    Initialize separately. A write connection uses autocommit unless an explicit
    transaction is started. Do not share a writer across Streamlit sessions.
    """
    database = resolve_database(path)
    if not database.is_file():
        raise FileNotFoundError(f"DuckDB database not found: {database}; run initialization first")
    conn = duckdb.connect(str(database), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(path: str | Path = DEFAULT_DATABASE) -> Iterator[duckdb.DuckDBPyConnection]:
    """Commit on success, roll back on exceptions and close the owned writer.

    Do not manually commit/rollback or nest transaction control inside this scope.
    """
    with connection(path, read_only=False) as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def initialize_database(path: str | Path = DEFAULT_DATABASE) -> dict[str, str | bool]:
    """Create an empty file if missing; verify existing databases read-only.

    Never creates application schemas/tables or replaces an existing file. Run
    initialization before application connections start, not during writer work.
    """
    database = resolve_database(path)
    existed = database.exists()
    if not existed:
        database.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(database))
        conn.close()
    with connection(database) as conn:
        version = conn.execute("SELECT version()").fetchone()[0]
        if conn.execute("SELECT 42").fetchone() != (42,):
            raise RuntimeError("DuckDB verification failed: unexpected query result")
    return {"database_path": str(database), "duckdb_version": version, "created": not existed}
