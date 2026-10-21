"""Legacy Task07/08A registry validator retained for regression compatibility."""

import argparse
import json
import sys

from src.config.source_registry_task08a import (
    DEFAULT_REGISTRY,
    RegistryError,
    check_source_files,
    load_registry,
    registry_report,
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_REGISTRY)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        registry = load_registry(args.config)
        report = registry_report(registry)
        report["source_file_errors"] = [] if args.metadata_only else check_source_files(registry)
        report["file_check"] = (
            "NOT_CHECKED" if args.metadata_only else "FAILED" if report["source_file_errors"] else "VERIFIED"
        )
    except RegistryError as exc:
        print(f"FAILED_CONFIGURATION: {exc}")
        return 1
    if report["source_file_errors"]:
        report["task08"] = "NOT_READY"
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(
            f"{'FAILED_SOURCE_FILES' if report['source_file_errors'] else 'SUCCESS'}: "
            f"configuration VALID; files={report['file_check']}"
        )
        for error in report["source_file_errors"]:
            print(error)
    return 2 if report["source_file_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
