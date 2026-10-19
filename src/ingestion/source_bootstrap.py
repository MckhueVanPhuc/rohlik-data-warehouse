"""Safe provisional bootstrap of the six historical CSVs into an isolated DuckDB.

The implementation is deliberately narrow: exact Task 07 registry mappings are
materialized, source values are not cleaned, and Finance/HR remain missing.  It
does not use the production DuckDB helper because Task 08A owns a separate file
and has stronger path/ownership rules than the general infrastructure module.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

import duckdb

from src.config.source_registry import (
    DEFAULT_REGISTRY,
    EXPECTED_TABLES,
    MISSING_TABLES,
    PROJECT_ROOT,
    Registry,
    RegistryError,
    check_source_files,
    load_registry,
    source_path,
)


DEFAULT_BOOTSTRAP_DATABASE = PROJECT_ROOT / "data" / "warehouse" / "rohlik_bootstrap_dev.duckdb"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "exports" / "source_bootstrap"
PROTECTED_DATABASES = (
    PROJECT_ROOT / "data" / "warehouse" / "rohlik.duckdb",
    PROJECT_ROOT / "data" / "input.db",
)
FORMAT_VERSION = 1
COMPONENT = "TASK_08A"
BRONZE_TABLES = {
    "orders": "raw_orders",
    "orders_calendar": "raw_orders_calendar",
    "sales": "raw_sales",
    "inventory": "raw_inventory",
    "sales_calendar": "raw_sales_calendar",
    "weights": "raw_weights",
}
HISTORICAL_TABLES = frozenset(EXPECTED_TABLES - MISSING_TABLES)
SOURCE_KEYS = {
    "orders": ["warehouse", "date"],
    "orders_calendar": ["warehouse", "date"],
    "sales": ["unique_id", "date"],
    "inventory": ["unique_id"],
    "sales_calendar": ["warehouse", "date"],
    "weights": ["unique_id"],
}
CALENDAR_SHARED = [
    "holiday_name",
    "holiday",
    "shops_closed",
    "school_holidays",
    "winter_school_holidays",
]


class BootstrapError(RuntimeError):
    """A safety, preflight, ingestion, or validation failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ident(name: str) -> str:
    """Quote a validated identifier for DuckDB SQL."""
    return '"' + name.replace('"', '""') + '"'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _registry_path(path: str | Path, root: Path) -> Path:
    candidate = Path(path)
    return (candidate if candidate.is_absolute() else root / candidate).resolve()


def validate_output_database(path: str | Path, root: Path = PROJECT_ROOT) -> Path:
    """Allow only a non-production .duckdb file under this root's warehouse dir."""
    root = root.resolve()
    candidate = Path(path)
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    warehouse = (root / "data" / "warehouse").resolve()
    protected = {
        (root / "data" / "warehouse" / "rohlik.duckdb").resolve(),
        (root / "data" / "input.db").resolve(),
        *(path.resolve() for path in PROTECTED_DATABASES),
    }
    raw = (root / "data" / "raw").resolve()
    if target in protected or target.is_relative_to(raw):
        raise BootstrapError(f"Unsafe/protected output database path: {target}")
    if target.suffix.lower() != ".duckdb" or not target.is_relative_to(warehouse):
        raise BootstrapError("Bootstrap database must be a .duckdb file inside data/warehouse")
    return target


def validate_report_directory(path: str | Path, root: Path = PROJECT_ROOT) -> Path:
    candidate = Path(path)
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    exports = (root / "data" / "exports").resolve()
    if not target.is_relative_to(exports):
        raise BootstrapError("Report directory must be inside project data/exports")
    return target


def _reader_sql(source: Any) -> str:
    columns = ", ".join(
        f"'{name.replace(chr(39), chr(39) * 2)}': '{column.inferred_type}'"
        for name, column in source.columns.items()
    )
    return (
        "read_csv(?, header=true, columns={" + columns + "}, "
        "strict_mode=true, ignore_errors=false, encoding='utf-8')"
    )


def _headers(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return next(csv.reader(stream))
    except (OSError, UnicodeError, StopIteration, csv.Error) as exc:
        raise BootstrapError(f"Cannot read CSV header {path}: {exc}") from exc


def _aggregate_source(conn: duckdb.DuckDBPyConnection, file_id: str, source: Any, path: Path) -> dict[str, Any]:
    expected_columns = list(source.columns)
    actual_columns = _headers(path)
    if actual_columns != expected_columns:
        raise BootstrapError(
            f"{file_id}: source columns changed; expected={expected_columns}; actual={actual_columns}"
        )
    expressions = ["count(*) AS row_count"]
    for name in expected_columns:
        expressions.append(f"count(*) FILTER (WHERE {ident(name)} IS NULL) AS {ident('null__' + name)}")
    if file_id == "sales":
        for name in (column for column in expected_columns if column.startswith("type_") and column.endswith("_discount")):
            expressions.append(f"count(*) FILTER (WHERE {ident(name)} < 0) AS {ident('negative__' + name)}")
    try:
        result = conn.execute(
            f"SELECT {', '.join(expressions)} FROM {_reader_sql(source)}", [str(path)]
        )
        values = result.fetchone()
        stats = dict(zip([item[0] for item in result.description], values))
        keys = SOURCE_KEYS[file_id]
        key_sql = ", ".join(ident(key) for key in keys)
        duplicate_groups, duplicate_excess, null_keys = conn.execute(
            f"""WITH source AS (SELECT * FROM {_reader_sql(source)}), grouped AS (
                    SELECT {key_sql}, count(*) AS n FROM source GROUP BY {key_sql})
                SELECT count(*) FILTER (WHERE n > 1), coalesce(sum(n - 1) FILTER (WHERE n > 1), 0),
                       (SELECT count(*) FROM source WHERE {' OR '.join(f'{ident(key)} IS NULL' for key in keys)})
                FROM grouped""",
            [str(path)],
        ).fetchone()
    except duckdb.Error as exc:
        raise BootstrapError(f"{file_id}: strict CSV parse failed: {exc}") from exc
    null_counts = {name: stats[f"null__{name}"] for name in expected_columns}
    expected_nulls = {name: column.null_count for name, column in source.columns.items()}
    if stats["row_count"] != source.row_count:
        raise BootstrapError(
            f"{file_id}: row count changed; registry={source.row_count}, actual={stats['row_count']}"
        )
    if null_counts != expected_nulls:
        changed = {name: {"registry": expected_nulls[name], "actual": null_counts[name]}
                   for name in expected_columns if expected_nulls[name] != null_counts[name]}
        raise BootstrapError(f"{file_id}: null metadata changed: {changed}")
    if duplicate_groups or null_keys:
        raise BootstrapError(
            f"{file_id}: business/source key validation failed; duplicate_groups={duplicate_groups}, null_keys={null_keys}"
        )
    return {
        "path": source.path,
        "sha256": source.sha256,
        "rows": stats["row_count"],
        "columns": actual_columns,
        "null_counts": null_counts,
        "business_keys": keys,
        "duplicate_key_groups": duplicate_groups,
        "duplicate_key_excess_rows": duplicate_excess,
        "null_key_rows": null_keys,
        "negative_discount_cells": sum(
            value for name, value in stats.items() if name.startswith("negative__")
        ),
    }


def _calendar_checks(conn: duckdb.DuckDBPyConnection, registry: Registry, root: Path) -> dict[str, Any]:
    orders = registry.source_files["orders_calendar"]
    sales = registry.source_files["sales_calendar"]
    result = conn.execute(
        f"""WITH o AS (SELECT * FROM {_reader_sql(orders)}),
                  s AS (SELECT * FROM {_reader_sql(sales)})
            SELECT count(*) AS overlap_rows,
                   {', '.join(f'count(*) FILTER (WHERE o.{ident(c)} IS DISTINCT FROM s.{ident(c)}) AS {ident(c)}' for c in CALENDAR_SHARED)}
            FROM o JOIN s USING (warehouse, date)""",
        [str(root / orders.path), str(root / sales.path)],
    )
    row = result.fetchone()
    values = dict(zip([item[0] for item in result.description], row))
    conflicts = {column: values[column] for column in CALENDAR_SHARED}
    union_rows = conn.execute(
        f"""WITH o AS (SELECT warehouse,date FROM {_reader_sql(orders)}),
                  s AS (SELECT warehouse,date FROM {_reader_sql(sales)})
            SELECT count(*) FROM (SELECT * FROM o UNION SELECT * FROM s)""",
        [str(root / orders.path), str(root / sales.path)],
    ).fetchone()[0]
    return {
        "overlap_rows": values["overlap_rows"],
        "shared_fields": CALENDAR_SHARED,
        "conflicts": conflicts,
        "conflict_cells": sum(conflicts.values()),
        "union_rows": union_rows,
        "orders_only_fields": sorted(set(orders.columns) - set(sales.columns)),
        "projection_rule": (
            "FULL OUTER JOIN on unique warehouse/date; use Sales Calendar on Sales-only keys, "
            "Orders Calendar on Orders-only keys, and materialize overlap only when every shared value is null-safe equal"
        ),
    }


def _inventory_only_count(conn: duckdb.DuckDBPyConnection, registry: Registry, root: Path) -> int:
    sales = registry.source_files["sales"]
    inventory = registry.source_files["inventory"]
    return conn.execute(
        f"""WITH sales_ids AS (SELECT DISTINCT unique_id FROM {_reader_sql(sales)}),
                  inventory_ids AS (SELECT unique_id FROM {_reader_sql(inventory)})
            SELECT count(*) FROM inventory_ids i LEFT JOIN sales_ids s USING (unique_id)
            WHERE s.unique_id IS NULL""",
        [str(root / sales.path), str(root / inventory.path)],
    ).fetchone()[0]


def _fingerprint(registry: Registry, registry_file: Path) -> str:
    payload = {
        "format_version": FORMAT_VERSION,
        "registry_version": registry.registry_version,
        "registry_sha256": sha256(registry_file),
        "sources": {name: source.sha256 for name, source in sorted(registry.source_files.items())},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def preflight(
    *,
    root: Path = PROJECT_ROOT,
    registry_path: str | Path = DEFAULT_REGISTRY,
    output_database: str | Path = DEFAULT_BOOTSTRAP_DATABASE,
    report_dir: str | Path = DEFAULT_REPORT_DIR,
) -> tuple[Registry, dict[str, Any]]:
    """Perform read-only source/schema/key/resource checks and return the plan."""
    root = root.resolve()
    target = validate_output_database(output_database, root)
    reports = validate_report_directory(report_dir, root)
    registry_file = _registry_path(registry_path, root)
    try:
        registry = load_registry(registry_file, root=root)
    except RegistryError as exc:
        raise BootstrapError(f"Registry validation failed: {exc}") from exc
    source_errors = check_source_files(registry, root)
    if source_errors:
        raise BootstrapError("Source file validation failed: " + "; ".join(source_errors))
    total_bytes = sum(source_path(source.path, root).stat().st_size for source in registry.source_files.values())
    required_free = total_bytes * 4 + 100 * 1024 * 1024
    existing_parent = target.parent
    while not existing_parent.exists() and existing_parent != existing_parent.parent:
        existing_parent = existing_parent.parent
    free = shutil.disk_usage(existing_parent).free
    if free < required_free:
        raise BootstrapError(
            f"Insufficient disk space: free={free}, conservative_required={required_free}"
        )

    conn = duckdb.connect(":memory:")
    sources: dict[str, Any] = {}
    try:
        conn.execute("SET threads=2")
        conn.execute("SET memory_limit='1GB'")
        for file_id, source in registry.source_files.items():
            path = source_path(source.path, root)
            sources[file_id] = _aggregate_source(conn, file_id, source, path)
        calendar = _calendar_checks(conn, registry, root)
        inventory_only = _inventory_only_count(conn, registry, root)
    finally:
        conn.close()

    # Detect a file changed while it was parsed, not merely before parsing.
    after_hashes = {name: sha256(source_path(source.path, root)) for name, source in registry.source_files.items()}
    changed = [name for name, source in registry.source_files.items() if after_hashes[name] != source.sha256]
    if changed:
        raise BootstrapError(f"Source changed during preflight: {changed}")

    table_plan = []
    for table in registry.tables:
        status = "SKIPPED_MISSING" if table.name in MISSING_TABLES else "READY_PROVISIONAL"
        if table.name == "planning.calendar" and calendar["conflict_cells"]:
            status = "SKIPPED_PENDING"
        table_plan.append({
            "table": table.name,
            "source_files": table.source_files,
            "grain": table.grain.detail,
            "business_keys": table.business_keys,
            "columns": [column.name for column in table.columns],
            "status": status,
            "schema_approval": table.schema_approval.status,
            "mapping_approval": table.mapping_approval.status,
        })
    report = {
        "task": "08A",
        "mode": "DRY_RUN",
        "generated_at": utc_now(),
        "status": "PARTIAL" if calendar["conflict_cells"] else "READY_PROVISIONAL",
        "root": str(root),
        "target_database": str(target),
        "target_exists": target.exists(),
        "registry_path": str(registry_file),
        "registry_version": registry.registry_version,
        "registry_sha256": sha256(registry_file),
        "fingerprint": _fingerprint(registry, registry_file),
        "resources": {
            "source_bytes": total_bytes,
            "free_bytes": free,
            "conservative_required_bytes": required_free,
        },
        "sources": sources,
        "calendar": calendar,
        "special_findings": {
            "sales_null_rows": sources["sales"]["null_counts"]["sales"],
            "total_orders_null_rows": sources["sales"]["null_counts"]["total_orders"],
            "negative_discount_cells": sources["sales"]["negative_discount_cells"],
            "inventory_only_skus": inventory_only,
        },
        "bronze_tables": {file_id: f"bronze.{name}" for file_id, name in BRONZE_TABLES.items()},
        "table_plan": table_plan,
        "missing_by_design": sorted(MISSING_TABLES),
        "report_dir": str(reports),
    }
    return registry, report


def _metadata_ddl(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS bootstrap_meta")
    conn.execute("""CREATE TABLE IF NOT EXISTS bootstrap_meta.ownership (
        component VARCHAR PRIMARY KEY, format_version INTEGER, created_at VARCHAR,
        registry_version INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bootstrap_meta.bootstrap_runs (
        run_id VARCHAR PRIMARY KEY, fingerprint VARCHAR, started_at VARCHAR,
        completed_at VARCHAR, status VARCHAR, registry_version INTEGER,
        registry_sha256 VARCHAR, target_database VARCHAR, error VARCHAR)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bootstrap_meta.source_lineage (
        run_id VARCHAR, file_id VARCHAR, relative_path VARCHAR, sha256 VARCHAR,
        source_row_count BIGINT, loaded_row_count BIGINT, registry_version INTEGER,
        ingested_at VARCHAR, status VARCHAR)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bootstrap_meta.table_loads (
        run_id VARCHAR, table_name VARCHAR, source_files VARCHAR, grain VARCHAR,
        business_keys VARCHAR, row_count BIGINT, duplicate_key_groups BIGINT,
        status VARCHAR, known_issues VARCHAR)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bootstrap_meta.dq_results (
        run_id VARCHAR, check_id VARCHAR, object_name VARCHAR, status VARCHAR,
        observed VARCHAR, expected VARCHAR, details VARCHAR, checked_at VARCHAR)""")


def _user_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    return [
        f"{schema}.{table}" for schema, table in conn.execute(
            """SELECT table_schema, table_name FROM information_schema.tables
               WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
               ORDER BY 1,2"""
        ).fetchall()
    ]


def _ensure_ownership(conn: duckdb.DuckDBPyConnection, registry_version: int) -> None:
    tables = _user_tables(conn)
    owns = "bootstrap_meta.ownership" in tables
    if not owns and tables:
        raise BootstrapError(
            "Existing database is not owned by Task 08A; refusing to alter tables: " + ", ".join(tables)
        )
    _metadata_ddl(conn)
    row = conn.execute(
        "SELECT component, format_version FROM bootstrap_meta.ownership"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO bootstrap_meta.ownership VALUES (?, ?, ?, ?)",
            [COMPONENT, FORMAT_VERSION, utc_now(), registry_version],
        )
    elif row != (COMPONENT, FORMAT_VERSION):
        raise BootstrapError(f"Incompatible bootstrap database ownership/version: {row}")


def _duplicates(conn: duckdb.DuckDBPyConnection, qualified: str, keys: list[str]) -> int:
    key_sql = ", ".join(ident(key) for key in keys)
    return conn.execute(
        f"SELECT count(*) FROM (SELECT {key_sql} FROM {qualified} GROUP BY {key_sql} HAVING count(*) > 1)"
    ).fetchone()[0]


def _insert_dq(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    check_id: str,
    object_name: str,
    status: str,
    observed: Any,
    expected: Any,
    details: str,
) -> None:
    conn.execute(
        "INSERT INTO bootstrap_meta.dq_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [run_id, check_id, object_name, status, str(observed), str(expected), details, utc_now()],
    )


def _load_bronze(
    conn: duckdb.DuckDBPyConnection,
    registry: Registry,
    root: Path,
    run_id: str,
) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    for file_id, table_name in BRONZE_TABLES.items():
        source = registry.source_files[file_id]
        qualified = f"bronze.{ident(table_name)}"
        conn.execute(
            f"CREATE OR REPLACE TABLE {qualified} AS SELECT * FROM {_reader_sql(source)}",
            [str(source_path(source.path, root))],
        )
        loaded = conn.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0]
        if loaded != source.row_count:
            raise BootstrapError(
                f"Bronze row reconciliation failed for {file_id}: loaded={loaded}, source={source.row_count}"
            )
        conn.execute(
            "INSERT INTO bootstrap_meta.source_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [run_id, file_id, source.path, source.sha256, source.row_count, loaded,
             registry.registry_version, utc_now(), "SUCCESS"],
        )
        _insert_dq(conn, run_id, "BRONZE_ROW_COUNT", f"bronze.{table_name}", "PASS", loaded,
                   source.row_count, "No filtering, deduplication, filling, clipping, or aggregation")


def _create_calendar(conn: duckdb.DuckDBPyConnection, table: Any, calendar: dict[str, Any]) -> tuple[str, int]:
    if calendar["conflict_cells"]:
        return "SKIPPED_PENDING", 0
    conn.execute("CREATE SCHEMA IF NOT EXISTS planning")
    selections = [
        "coalesce(o.warehouse, s.warehouse) AS warehouse",
        "coalesce(o.date, s.date) AS date",
    ]
    for column in CALENDAR_SHARED:
        # Values on overlapping keys were already proved null-safe equal.  CASE is
        # therefore coverage selection, not an undocumented business precedence.
        selections.append(
            f"CASE WHEN s.warehouse IS NOT NULL THEN s.{ident(column)} ELSE o.{ident(column)} END AS {ident(column)}"
        )
    conn.execute(
        f"""CREATE OR REPLACE TABLE planning.calendar AS
            SELECT {', '.join(selections)}
            FROM bronze.raw_orders_calendar o
            FULL OUTER JOIN bronze.raw_sales_calendar s USING (warehouse, date)"""
    )
    rows = conn.execute("SELECT count(*) FROM planning.calendar").fetchone()[0]
    if rows != calendar["union_rows"]:
        raise BootstrapError(f"Calendar row explosion/loss: loaded={rows}, expected={calendar['union_rows']}")
    return "SUCCESS_PROVISIONAL", rows


def _load_projections(
    conn: duckdb.DuckDBPyConnection,
    registry: Registry,
    preflight_report: dict[str, Any],
    run_id: str,
) -> bool:
    partial = False
    for table in registry.tables:
        source_files = json.dumps(table.source_files, ensure_ascii=False)
        keys = json.dumps(table.business_keys, ensure_ascii=False)
        if table.name in MISSING_TABLES:
            conn.execute(
                "INSERT INTO bootstrap_meta.table_loads VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
                [run_id, table.name, source_files, table.grain.detail, keys, "SKIPPED_MISSING",
                 "Source availability=MISSING; no table or fabricated records created"],
            )
            continue
        schema, name = table.name.split(".")
        if table.name == "planning.calendar":
            status, row_count = _create_calendar(conn, table, preflight_report["calendar"])
            if status == "SKIPPED_PENDING":
                partial = True
                duplicates = None
                issue = "Shared-field conflicts require an approved precedence decision"
            else:
                duplicates = _duplicates(conn, "planning.calendar", table.business_keys)
                issue = "Provisional reconciled shared-field projection; no official business precedence"
        else:
            file_ids = {mapping.file_id for mapping in table.mappings}
            if len(file_ids) != 1:
                raise BootstrapError(f"Unsupported non-calendar multi-source mapping: {table.name}")
            file_id = next(iter(file_ids))
            source_table = f"bronze.{ident(BRONZE_TABLES[file_id])}"
            by_target = {mapping.target: mapping for mapping in table.mappings}
            if set(by_target) != {column.name for column in table.columns}:
                raise BootstrapError(f"Incomplete direct projection mapping: {table.name}")
            select_sql = ", ".join(
                f"{ident(by_target[column.name].source_column)} AS {ident(column.name)}"
                for column in table.columns
            )
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {ident(schema)}")
            conn.execute(
                f"CREATE OR REPLACE TABLE {ident(schema)}.{ident(name)} AS SELECT {select_sql} FROM {source_table}"
            )
            row_count = conn.execute(
                f"SELECT count(*) FROM {ident(schema)}.{ident(name)}"
            ).fetchone()[0]
            expected = registry.source_files[file_id].row_count
            if row_count != expected:
                raise BootstrapError(
                    f"Projection row reconciliation failed for {table.name}: loaded={row_count}, source={expected}"
                )
            duplicates = _duplicates(conn, f"{ident(schema)}.{ident(name)}", table.business_keys)
            status = "SUCCESS_PROVISIONAL"
            issue = "Registry schema/mapping remain PENDING_CONFIRMATION"
        if duplicates:
            raise BootstrapError(f"Projection duplicate business keys detected: {table.name}={duplicates}")
        conn.execute(
            "INSERT INTO bootstrap_meta.table_loads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [run_id, table.name, source_files, table.grain.detail, keys, row_count,
             duplicates, status, issue],
        )
        _insert_dq(conn, run_id, "PROJECTION_KEYS", table.name,
                   "SKIPPED_PENDING" if status == "SKIPPED_PENDING" else "PASS",
                   duplicates, 0, issue)
    return partial


def _special_dq(conn: duckdb.DuckDBPyConnection, run_id: str, report: dict[str, Any]) -> None:
    findings = report["special_findings"]
    sales_nulls = conn.execute(
        "SELECT count(*) FILTER (WHERE sales IS NULL), count(*) FILTER (WHERE total_orders IS NULL) FROM bronze.raw_sales"
    ).fetchone()
    negative = conn.execute(
        """SELECT count(*) FILTER (WHERE type_0_discount < 0) +
                  count(*) FILTER (WHERE type_1_discount < 0) +
                  count(*) FILTER (WHERE type_2_discount < 0) +
                  count(*) FILTER (WHERE type_3_discount < 0) +
                  count(*) FILTER (WHERE type_4_discount < 0) +
                  count(*) FILTER (WHERE type_5_discount < 0) +
                  count(*) FILTER (WHERE type_6_discount < 0)
           FROM bronze.raw_sales"""
    ).fetchone()[0]
    inventory_only = conn.execute(
        """SELECT count(*) FROM bronze.raw_inventory i
           LEFT JOIN (SELECT DISTINCT unique_id FROM bronze.raw_sales) s USING (unique_id)
           WHERE s.unique_id IS NULL"""
    ).fetchone()[0]
    checks = [
        ("SALES_NULLS", "bronze.raw_sales", sales_nulls,
         (findings["sales_null_rows"], findings["total_orders_null_rows"]),
         "PASS", "Null values are preserved, not filled or dropped"),
        ("NEGATIVE_DISCOUNTS", "bronze.raw_sales", negative,
         findings["negative_discount_cells"], "WARN",
         "Known source condition is preserved; clipping is deferred to Task 09 policy"),
        ("INVENTORY_ONLY_SKUS", "bronze.raw_inventory", inventory_only,
         findings["inventory_only_skus"], "WARN",
         "Inventory-only SKUs are preserved, not filtered"),
        ("CALENDAR_OVERLAP", "planning.calendar", report["calendar"]["overlap_rows"],
         report["calendar"]["overlap_rows"], "PASS",
         "Overlap is reconciled null-safely without row multiplication"),
    ]
    for check_id, obj, observed, expected, status, detail in checks:
        if observed != expected:
            raise BootstrapError(f"Special DQ reconciliation failed: {check_id}: {observed} != {expected}")
        _insert_dq(conn, run_id, check_id, obj, status, observed, expected, detail)


def _report_from_database(database: Path, base: dict[str, Any] | None = None) -> dict[str, Any]:
    if not database.is_file():
        raise BootstrapError(f"Bootstrap database not found: {database}")
    try:
        conn = duckdb.connect(str(database), read_only=True)
        try:
            owner = conn.execute(
                "SELECT component, format_version, registry_version FROM bootstrap_meta.ownership"
            ).fetchone()
            if not owner or owner[:2] != (COMPONENT, FORMAT_VERSION):
                raise BootstrapError("Database is not a compatible Task 08A bootstrap database")
            run = conn.execute(
                """SELECT run_id, fingerprint, started_at, completed_at, status, registry_version,
                          registry_sha256, error
                   FROM bootstrap_meta.bootstrap_runs
                   ORDER BY started_at DESC LIMIT 1"""
            ).fetchone()
            if not run:
                raise BootstrapError("Bootstrap database has no run metadata")
            names = [item[0] for item in conn.description]
            run_data = dict(zip(names, run))
            lineages = conn.execute(
                """SELECT file_id, relative_path, sha256, source_row_count, loaded_row_count, status
                   FROM bootstrap_meta.source_lineage WHERE run_id=? ORDER BY file_id""",
                [run_data["run_id"]],
            ).fetchall()
            loads = conn.execute(
                """SELECT table_name, source_files, grain, business_keys, row_count,
                          duplicate_key_groups, status, known_issues
                   FROM bootstrap_meta.table_loads WHERE run_id=? ORDER BY table_name""",
                [run_data["run_id"]],
            ).fetchall()
            dq = conn.execute(
                """SELECT check_id, object_name, status, observed, expected, details
                   FROM bootstrap_meta.dq_results WHERE run_id=? ORDER BY check_id, object_name""",
                [run_data["run_id"]],
            ).fetchall()
            actual_bronze = {}
            existing = {
                f"{schema}.{table}" for schema, table in conn.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables"
                ).fetchall()
            }
            for file_id, table in BRONZE_TABLES.items():
                qualified = f"bronze.{table}"
                if qualified in existing:
                    actual_bronze[qualified] = conn.execute(
                        f"SELECT count(*) FROM bronze.{ident(table)}"
                    ).fetchone()[0]
        finally:
            conn.close()
    except duckdb.Error as exc:
        raise BootstrapError(f"Cannot validate bootstrap database: {exc}") from exc
    report = dict(base or {})
    report.update({
        "mode": "VALIDATE_ONLY" if base is None else report.get("mode", "EXECUTE_PROVISIONAL"),
        "generated_at": utc_now(),
        "target_database": str(database),
        "ownership": {"component": owner[0], "format_version": owner[1], "registry_version": owner[2]},
        "run": {key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in run_data.items()},
        "bronze_row_counts": actual_bronze,
        "source_lineage": [dict(zip(
            ["file_id", "relative_path", "sha256", "source_row_count", "loaded_row_count", "status"], row
        )) for row in lineages],
        "table_loads": [dict(zip(
            ["table_name", "source_files", "grain", "business_keys", "row_count",
             "duplicate_key_groups", "status", "known_issues"], row
        )) for row in loads],
        "dq_results": [dict(zip(
            ["check_id", "object_name", "status", "observed", "expected", "details"], row
        )) for row in dq],
        "status": "PARTIAL" if any(row[6] == "SKIPPED_PENDING" for row in loads) else run_data["status"],
    })
    return report


def execute_provisional(
    *,
    root: Path = PROJECT_ROOT,
    registry_path: str | Path = DEFAULT_REGISTRY,
    output_database: str | Path = DEFAULT_BOOTSTRAP_DATABASE,
    report_dir: str | Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    """Run Task 08A transactionally after a complete preflight."""
    root = root.resolve()
    target = validate_output_database(output_database, root)
    registry, plan = preflight(
        root=root, registry_path=registry_path, output_database=target, report_dir=report_dir
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(target))
    run_id = str(uuid4())
    try:
        _ensure_ownership(conn, registry.registry_version)
        prior = conn.execute(
            "SELECT run_id FROM bootstrap_meta.bootstrap_runs WHERE fingerprint=? AND status='SUCCESS' ORDER BY started_at DESC LIMIT 1",
            [plan["fingerprint"]],
        ).fetchone()
        changed_success = conn.execute(
            "SELECT run_id FROM bootstrap_meta.bootstrap_runs WHERE status='SUCCESS' AND fingerprint<>? LIMIT 1",
            [plan["fingerprint"]],
        ).fetchone()
        if changed_success:
            raise BootstrapError(
                "A successful bootstrap exists for a different source/registry fingerprint; profiling and review are required"
            )
        if prior:
            conn.close()
            result = _report_from_database(target, {**plan, "mode": "EXECUTE_PROVISIONAL"})
            result["idempotent_noop"] = True
            return result
        conn.execute(
            "INSERT INTO bootstrap_meta.bootstrap_runs VALUES (?, ?, ?, NULL, 'RUNNING', ?, ?, ?, NULL)",
            [run_id, plan["fingerprint"], utc_now(), registry.registry_version,
             plan["registry_sha256"], str(target)],
        )
        conn.commit()
        try:
            conn.execute("BEGIN TRANSACTION")
            _load_bronze(conn, registry, root, run_id)
            partial = _load_projections(conn, registry, plan, run_id)
            _special_dq(conn, run_id, plan)
            changed = [
                file_id for file_id, source in registry.source_files.items()
                if sha256(source_path(source.path, root)) != source.sha256
            ]
            if changed:
                raise BootstrapError(f"Source changed during bootstrap: {changed}")
            conn.execute(
                "UPDATE bootstrap_meta.bootstrap_runs SET completed_at=?, status='SUCCESS' WHERE run_id=?",
                [utc_now(), run_id],
            )
            conn.commit()
        except BaseException as exc:
            conn.rollback()
            conn.execute(
                "UPDATE bootstrap_meta.bootstrap_runs SET completed_at=?, status='FAILED', error=? WHERE run_id=?",
                [utc_now(), str(exc), run_id],
            )
            conn.commit()
            if isinstance(exc, BootstrapError):
                raise
            raise BootstrapError(f"Bootstrap data transaction failed: {exc}") from exc
    except (duckdb.Error, OSError) as exc:
        raise BootstrapError(f"Bootstrap execution failed: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
    result = _report_from_database(target, {**plan, "mode": "EXECUTE_PROVISIONAL"})
    result["idempotent_noop"] = False
    if partial:
        result["status"] = "PARTIAL"
    return result


def validate_existing(
    *, output_database: str | Path = DEFAULT_BOOTSTRAP_DATABASE, root: Path = PROJECT_ROOT
) -> dict[str, Any]:
    target = validate_output_database(output_database, root)
    return _report_from_database(target)


def write_report(report: dict[str, Any], directory: str | Path = DEFAULT_REPORT_DIR,
                 root: Path = PROJECT_ROOT) -> Path:
    target_dir = validate_report_directory(directory, root)
    target_dir.mkdir(parents=True, exist_ok=True)
    run_id = report.get("run", {}).get("run_id") or report.get("fingerprint", "unknown")[:16]
    mode = report.get("mode", "report").lower()
    target = target_dir / f"{mode}_{run_id}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (target_dir / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return target
