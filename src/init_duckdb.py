"""Initialize and verify DuckDB: python -m src.init_duckdb [--database PATH]."""

import argparse

import duckdb

from src.db.duckdb import DEFAULT_DATABASE, initialize_database


def main() -> int:
    """Print SUCCESS and verified settings, or FAILED with exit code 1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    args = parser.parse_args()
    try:
        result = initialize_database(args.database)
    except (OSError, duckdb.Error, RuntimeError) as exc:
        print(f"FAILED: {exc}")
        return 1
    print("SUCCESS: DuckDB initialized and verified; no application schema created")
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
