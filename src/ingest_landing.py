"""Dry-run V4 landing preflight, or explicitly load an isolated DuckDB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from src.config.source_registry import PROJECT_ROOT, RegistryError
from src.ingestion.landing import LandingIngestionError, ingest_landing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="explicitly enable writes")
    parser.add_argument("--database", help="existing isolated .duckdb target (required with --execute)")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--entered-by", default="system:v4-03-initial-bootstrap")
    parser.add_argument("--lock-timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.execute and not args.database:
        parser.error("--database is required with --execute")
    database = args.database or args.project_root / "data" / "warehouse" / "rohlik.duckdb"
    try:
        report = ingest_landing(
            database,
            execute=args.execute,
            root=args.project_root,
            entered_by=args.entered_by,
            lock_timeout=args.lock_timeout,
        )
    except (OSError, ValueError, RuntimeError, duckdb.Error, RegistryError, LandingIngestionError) as exc:
        print(f"FAILED: {exc}")
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
