"""Validate configuration and optionally verify source file hashes, without ingestion."""

import argparse
import json
import sys

from src.config.source_registry import (DEFAULT_REGISTRY, RegistryError, check_source_files,
                                        load_registry, registry_report)


def main() -> int:
    """Exit 0 for valid pending config, 1 for invalid config, 2 for unexpected source issues."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_REGISTRY)
    parser.add_argument("--metadata-only", action="store_true", help="Skip CSV existence/hash checks (e.g. source-free checkout)")
    parser.add_argument("--json", action="store_true", help="Print structured validation report")
    args = parser.parse_args()
    try:
        registry = load_registry(args.config)
        report = registry_report(registry)
        report["source_file_errors"] = [] if args.metadata_only else check_source_files(registry)
        report["file_check"] = "NOT_CHECKED" if args.metadata_only else "FAILED" if report["source_file_errors"] else "VERIFIED"
    except RegistryError as exc:
        print(f"FAILED_CONFIGURATION: {exc}")
        return 1
    if report["source_file_errors"]:
        report["task08"] = "NOT_READY"
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(f"{'FAILED_SOURCE_FILES' if report['source_file_errors'] else 'SUCCESS'}: configuration VALID; files={report['file_check']}")
        print(f"Tables: {report['source_count']}; catalog files: {report['verified_source_files']}; source paths/keys/schema references: VALID")
        for name, status in report["table_status"].items():
            print(f"{name}: source={status['source']}; schema={status['schema']}; mapping={status['mapping']}; upload={status['upload']}")
        print("MISSING by design: " + ", ".join(report["missing_by_design"]))
        for name, decisions in report["pending_decisions"].items():
            print(f"PENDING {name}: " + "; ".join(decisions))
        for name, detail in report["global_pending"].items():
            print(f"PENDING global.{name}: {detail}")
        for error in report["source_file_errors"]:
            print(error)
        print(f"Task 08: {report['task08']}; configuration only, no ingestion")
    return 2 if report["source_file_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
