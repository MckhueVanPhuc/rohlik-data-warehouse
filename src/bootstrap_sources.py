"""Task 08A CLI: dry-run, execute provisional bootstrap, or validate an existing run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.config.source_registry_task08a import DEFAULT_REGISTRY, PROJECT_ROOT
from src.ingestion.source_bootstrap import (
    BootstrapError,
    DEFAULT_BOOTSTRAP_DATABASE,
    DEFAULT_REPORT_DIR,
    execute_provisional,
    preflight,
    validate_existing,
    write_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read-only preflight (default)")
    mode.add_argument("--execute", action="store_true", help="Write the isolated bootstrap database")
    mode.add_argument("--validate-only", action="store_true", help="Read-only validation of an existing bootstrap")
    parser.add_argument("--provisional", action="store_true", help="Required acknowledgement for --execute")
    parser.add_argument("--config", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--database", type=Path, default=DEFAULT_BOOTSTRAP_DATABASE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--json", action="store_true", help="Print the complete report")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    if args.execute and not args.provisional:
        print("FAILED: --execute requires explicit --provisional acknowledgement")
        return 1
    if args.provisional and not args.execute:
        print("FAILED: --provisional is only valid with --execute")
        return 1
    try:
        if args.execute:
            report = execute_provisional(
                root=PROJECT_ROOT, registry_path=args.config, output_database=args.database,
                report_dir=args.report_dir,
            )
        elif args.validate_only:
            report = validate_existing(root=PROJECT_ROOT, output_database=args.database)
        else:
            _, report = preflight(
                root=PROJECT_ROOT, registry_path=args.config, output_database=args.database,
                report_dir=args.report_dir,
            )
        report_path = write_report(report, args.report_dir, PROJECT_ROOT)
    except BootstrapError as exc:
        print(f"FAILED: {exc}")
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{report['status']}: mode={report['mode']}; target={report['target_database']}")
        print(f"report={report_path}")
        if report.get("idempotent_noop"):
            print("idempotency=NO_OP (same source and registry fingerprint)")
    return 2 if report["status"] == "PARTIAL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
