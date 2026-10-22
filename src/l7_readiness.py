"""Read-only readiness gate for Rohlik Local L7 (no warehouse mutation)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import yaml

from src.config.source_registry import EXPECTED_TABLES, PROJECT_ROOT
from src.db.duckdb import connection, resolve_database

REQUIRED_DECISIONS = ("D01", "D02", "D03", "D04", "D05")
REQUIRED_MARTS = (
    "mart.sales_orders_day",
    "mart.ops_warehouse_day",
    "mart.category_sku_day",
    "mart.marketing_promo_day",
    "mart.exec_kpi_month",
)
REQUIRED_CORE = (
    "core.fct_warehouse_day",
    "core.fct_sku_day",
    "core.params_cost",
    "core.params_workforce",
)


def _decisions(path: Path) -> dict[str, str]:
    """Only explicit APPROVED values can open the gate."""
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("decisions"), dict):
        raise ValueError("Invalid decision register")
    decisions = obj["decisions"]
    result: dict[str, str] = {}
    for code in REQUIRED_DECISIONS:
        item = decisions.get(code)
        if not isinstance(item, dict):
            raise ValueError(f"Missing decision: {code}")
        state = item.get("status")
        if state not in {"PENDING", "APPROVED", "REJECTED"}:
            raise ValueError(f"Invalid decision status for {code}")
        result[code] = state
    return result


def assess(
    database: str | Path,
    *,
    decisions_path: str | Path = PROJECT_ROOT / "config" / "l7_decisions.yaml",
) -> dict[str, Any]:
    """Read decision statuses and catalog; never create/write database."""
    approvals = _decisions(Path(decisions_path))
    db = resolve_database(database)
    report: dict[str, Any] = {
        "database": str(db),
        "database_exists": db.is_file(),
        "decisions": approvals,
        "approved": all(v == "APPROVED" for v in approvals.values()),
        "landing_tables": 0,
        "completed_source_batches": 0,
        "core_tables": 0,
        "mart_views": 0,
        "warnings": [],
        "status": "BLOCKED",
    }
    if not db.is_file():
        report["warnings"].append("WAREHOUSE_NOT_READY: database is absent")
        return report
    try:
        with connection(db) as conn:
            items = {
                f"{r[0]}.{r[1]}": r[2]
                for r in conn.execute(
                    "SELECT table_schema, table_name, table_type FROM information_schema.tables"
                ).fetchall()
            }
            report["landing_tables"] = len(EXPECTED_TABLES.intersection(items))
            report["core_tables"] = len(set(REQUIRED_CORE).intersection(items))
            report["mart_views"] = sum(items.get(m) == "VIEW" for m in REQUIRED_MARTS)
            if "meta.source_batches" in items:
                batch_rows = conn.execute(
                    "SELECT source_id, status FROM meta.source_batches"
                ).fetchall()
                complete = [row[0] for row in batch_rows if row[1] == "COMPLETED"]
                report["completed_source_batches"] = len(set(complete))
                if len(batch_rows) != 7 or len(complete) != 7 or len(set(complete)) != 7:
                    report["warnings"].append("BATCH_STATUS_NOT_VERIFIED: expected 7 unique completed source batches")
            else:
                report["warnings"].append("SOURCE_BATCHES_NOT_AVAILABLE")
    except (duckdb.Error, OSError) as exc:
        report["warnings"].append(f"READ_ONLY_INSPECTION_FAILED: {type(exc).__name__}")
        return report
    if report["landing_tables"] != 14:
        report["warnings"].append("LANDING_NOT_READY: expected 14 tables")
    if report["core_tables"] != 4:
        report["warnings"].append("CORE_NOT_READY: expected 4 tables")
    if report["mart_views"] != 5:
        report["warnings"].append("MART_NOT_READY: expected 5 views")
    if not report["approved"]:
        report["warnings"].append("APPROVAL_REQUIRED: D01-D05 must be explicitly approved")
    # Catalog counts are advisory. DQ, NO_OP reconciliation and end-to-end tests
    # are mandatory independent gates: never label PRE_MODEL_READY from this CLI.
    report["status"] = "STRUCTURE_OBSERVED_NOT_ACCEPTED" if (
        report["approved"] and report["landing_tables"] == 14
        and report["completed_source_batches"] == 7
        and report["core_tables"] == 4 and report["mart_views"] == 5
        and not report["warnings"]
    ) else "BLOCKED"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/warehouse/rohlik_landing_dev.duckdb")
    parser.add_argument("--decisions", default=str(PROJECT_ROOT / "config" / "l7_decisions.yaml"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = assess(args.database, decisions_path=args.decisions)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2 if args.json else None, ensure_ascii=False))
    return 0 if result["status"] == "STRUCTURE_OBSERVED_NOT_ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
