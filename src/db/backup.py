"""SQLite Backup API utility: python -m src.db.backup [--database PATH]."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

from src.db.sqlite import DEFAULT_DATABASE, PROJECT_ROOT, resolve_database

DEFAULT_BACKUPS = PROJECT_ROOT / "data" / "backups"


def integrity_check(path: str | Path) -> None:
    """Check an existing database read-only; raise if any corruption is reported."""
    conn = sqlite3.connect(resolve_database(path).as_uri() + "?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            raise RuntimeError(f"SQLite integrity check failed: {result}")
    finally:
        conn.close()


def backup_database(
    path: str | Path = DEFAULT_DATABASE,
    backup_dir: str | Path = DEFAULT_BACKUPS,
) -> Path:
    """Create a unique, verified snapshot, including committed WAL contents.

    Never restores data. Failed snapshots are removed, and exceptions propagate.
    """
    source_path = resolve_database(path)
    directory = resolve_database(backup_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"{source_path.stem}_{timestamp}_{uuid4().hex}.db"
    # Reserve this name exclusively; never reuse or overwrite an old backup.
    with target.open("xb"):
        pass
    try:
        source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True,
                                 timeout=5)
        try:
            destination = sqlite3.connect(target)
            try:
                source.backup(destination, pages=256)
            finally:
                destination.close()
        finally:
            source.close()
        integrity_check(target)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def main() -> int:
    """Create a backup or verify an existing one without restoring it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUPS)
    parser.add_argument("--check", metavar="PATH", help="Only check this existing file")
    args = parser.parse_args()
    try:
        if args.check:
            integrity_check(args.check)
            print(f"SUCCESS: integrity_check=ok: {args.check}")
        else:
            result = backup_database(args.database, args.backup_dir)
            print(f"SUCCESS: backup={result}; integrity_check=ok")
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
