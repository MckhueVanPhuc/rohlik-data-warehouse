"""Validate the V4 registry/contract and optionally run a read-only CSV preflight."""

import argparse
import json
import sys

from src.config.source_registry import (
    DEFAULT_REGISTRY,
    RegistryError,
    load_contract,
    load_registry,
    preflight_sources,
    registry_report,
)


def main() -> int:
    """Exit 0 for valid config/sources, 1 for config failure, 2 for source failure."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_REGISTRY)
    parser.add_argument("--metadata-only", action="store_true", help="Skip CSV existence/hash checks (e.g. source-free checkout)")
    parser.add_argument("--json", action="store_true", help="Print structured validation report")
    args = parser.parse_args()
    try:
        registry = load_registry(args.config)
        contract = load_contract(registry=registry)
        report = registry_report(registry, contract)
    except RegistryError as exc:
        print(f"FAILED_CONFIGURATION: {exc}")
        return 1
    if args.metadata_only:
        report["file_check"] = "NOT_CHECKED"
    else:
        try:
            report["preflight"] = preflight_sources(registry)
            report["file_check"] = report["preflight"]["status"]
        except RegistryError as exc:
            report["file_check"] = "FAILED"
            report["source_file_errors"] = [str(exc)]
            if args.json:
                print(json.dumps(report, ensure_ascii=True, indent=2))
            else:
                print(f"FAILED_SOURCE_FILES: {exc}")
            return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(f"SUCCESS: V4 configuration VALID; files={report['file_check']}")
        print(
            f"Active sources: {report['active_source_count']}; contracts: {report['contract_count']}; "
            f"schemas: {len(report['schemas'])}"
        )
        print("ASSUMED sources: " + ", ".join(report["assumed_sources"]))
        print(report["execution"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
