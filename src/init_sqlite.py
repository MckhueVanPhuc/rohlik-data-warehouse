"""Initialize SQLite: python -m src.init_sqlite [--database PATH]."""

import argparse
import sqlite3

from src.db.sqlite import DEFAULT_DATABASE, initialize_database


def main() -> int:
    """Report verified settings and return a nonzero exit code on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    args = parser.parse_args()
    try:
        settings = initialize_database(args.database)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"FAILED: {exc}")
        return 1
    print("SUCCESS: SQLite initialized and verified")
    for name, value in settings.items():
        print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
