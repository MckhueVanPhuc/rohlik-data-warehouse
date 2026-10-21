"""Safe V4 initial CSV bootstrap into the fourteen contract landing tables."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from src.config.source_registry import (
    EXPECTED_SCHEMAS,
    EXPECTED_TABLES,
    PROJECT_ROOT,
    ActiveSource,
    BusinessContract,
    ContractCatalog,
    Registry,
    load_contract,
    load_registry,
    preflight_sources,
    source_path,
)
from src.db.duckdb import (
    DEFAULT_DATABASE,
    DEFAULT_LOCK_TIMEOUT,
    UnsafeWriteError,
    resolve_database,
    transaction,
)
from src.db.duckdb_metadata import (
    complete_source_batch,
    initialize_metadata,
    record_batch_status,
    record_entry_audit,
    record_table_load,
    source_batch_history,
    start_source_batch,
)

LANDING_METADATA_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("_batch_id", "VARCHAR", False),
    ("_source", "VARCHAR", False),
    ("_loaded_at", "TIMESTAMP", False),
    ("_entered_by", "VARCHAR", False),
)
COMPLETED_STATUS = "COMPLETED"
DEFAULT_ENTERED_BY = "system:v4-03-initial-bootstrap"


class LandingIngestionError(RuntimeError):
    """A V4 landing load was rejected without replacing existing data."""


class ChangedSourceError(LandingIngestionError):
    """A completed source or its contract has a different fingerprint."""


class IncompleteBatchError(LandingIngestionError):
    """Prior metadata is not a complete, consistent seven-source bootstrap."""


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _qualified(table: BusinessContract) -> str:
    return f"{_quote(table.schema_name)}.{_quote(table.table)}"


def _load_configuration(
    root: Path,
    registry_path: str | Path,
    contract_path: str | Path,
) -> tuple[Registry, ContractCatalog, dict[str, Any]]:
    registry = load_registry(registry_path, root=root)
    contract = load_contract(contract_path, registry=registry, root=root)
    preflight = preflight_sources(registry, root=root)
    if len(registry.active_sources) != 7 or set(contract.tables) != EXPECTED_TABLES:
        raise LandingIngestionError("V4 bootstrap requires exactly 7 sources and 14 contracts")
    if {item.schema_name for item in contract.tables.values()} != EXPECTED_SCHEMAS:
        raise LandingIngestionError("V4 bootstrap requires exactly the 9 approved landing schemas")
    return registry, contract, preflight


def _tables_by_source(
    registry: Registry, contract: ContractCatalog,
) -> dict[str, list[tuple[str, BusinessContract]]]:
    source_ids = {source.path: source_id for source_id, source in registry.active_sources.items()}
    grouped: dict[str, list[tuple[str, BusinessContract]]] = defaultdict(list)
    for name, table in contract.tables.items():
        grouped[source_ids[table.raw_source]].append((name, table))
    return {source_id: grouped[source_id] for source_id in registry.active_sources}


def _source_fingerprint(
    source_id: str,
    source: ActiveSource,
    registry: Registry,
    contract: ContractCatalog,
    tables: list[tuple[str, BusinessContract]],
) -> str:
    payload = {
        "source_id": source_id,
        "source_sha256": source.sha256,
        "registry_version": registry.registry_version,
        "contract_version": contract.contract_version,
        "tables": {
            name: table.model_dump(by_alias=True, mode="json")
            for name, table in sorted(tables)
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _warnings(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"source_id": source_id, "column": column, "count": count, "action": "PRESERVED"}
        for source_id, source_report in preflight["sources"].items()
        for column, count in source_report["constraint_violations"].items()
    ]


def plan_landing_ingestion(
    *,
    root: str | Path = PROJECT_ROOT,
    registry_path: str | Path = "config/sources.yaml",
    contract_path: str | Path = "config/contract.yaml",
) -> dict[str, Any]:
    """Preflight all active sources without opening or creating a warehouse."""
    project_root = Path(root).resolve()
    registry, contract, preflight = _load_configuration(
        project_root, registry_path, contract_path
    )
    return {
        "mode": "DRY_RUN",
        "status": preflight["status"],
        "source_count": len(registry.active_sources),
        "table_count": len(contract.tables),
        "schema_count": len({table.schema_name for table in contract.tables.values()}),
        "historical_sources_loaded": 0,
        "pending_update_policies": sorted(contract.tables),
        "warnings": _warnings(preflight),
    }


def _expected_columns(table: BusinessContract) -> list[tuple[str, str, bool]]:
    columns = [
        (name, definition.type, definition.nullable)
        for name, definition in table.columns.items()
    ]
    return [*columns, *LANDING_METADATA_COLUMNS]


def _table_exists(conn: duckdb.DuckDBPyConnection, table: BusinessContract) -> bool:
    return bool(conn.execute(
        """SELECT count(*) FROM information_schema.tables
           WHERE table_schema = ? AND table_name = ?""",
        [table.schema_name, table.table],
    ).fetchone()[0])


def _validate_existing_table(
    conn: duckdb.DuckDBPyConnection, name: str, table: BusinessContract,
) -> None:
    rows = conn.execute(
        """SELECT column_name, data_type, is_nullable
           FROM information_schema.columns
           WHERE table_schema = ? AND table_name = ?
           ORDER BY ordinal_position""",
        [table.schema_name, table.table],
    ).fetchall()
    actual = [(column, kind.upper(), nullable == "YES") for column, kind, nullable in rows]
    expected = _expected_columns(table)
    if actual != expected:
        raise LandingIngestionError(
            f"{name} has an incompatible physical schema; expected={expected}, actual={actual}"
        )


def _create_table(conn: duckdb.DuckDBPyConnection, table: BusinessContract) -> None:
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote(table.schema_name)}")
    definitions = [
        f"{_quote(name)} {kind}{'' if nullable else ' NOT NULL'}"
        for name, kind, nullable in _expected_columns(table)
    ]
    conn.execute(f"CREATE TABLE IF NOT EXISTS {_qualified(table)} ({', '.join(definitions)})")


def _reader_sql(source: ActiveSource) -> str:
    fields = ", ".join(
        f"'{name}': '{kind}'" for name, kind in source.column_types.items()
    )
    return (
        "read_csv(?, header=true, columns={" + fields
        + "}, strict_mode=true, ignore_errors=false, encoding='utf-8')"
    )


def _insert_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table: BusinessContract,
    source: ActiveSource,
    csv_path: Path,
    batch_id: str,
    loaded_at: datetime,
    entered_by: str,
) -> int:
    raw_for_canonical = {canonical: raw for raw, canonical in table.mapping.items()}
    canonical_names = list(table.columns)
    projections = [
        f"CAST({_quote(raw_for_canonical[name])} AS {table.columns[name].type})"
        for name in canonical_names
    ]
    target_names = [*canonical_names, *(name for name, _, _ in LANDING_METADATA_COLUMNS)]
    sql = (
        f"INSERT INTO {_qualified(table)} "
        f"({', '.join(_quote(name) for name in target_names)}) "
        f"SELECT {', '.join(projections)}, ?, ?, ?, ? FROM {_reader_sql(source)}"
    )
    conn.execute(
        sql,
        [batch_id, source.path, loaded_at, entered_by, str(csv_path)],
    )
    return conn.execute(
        f"SELECT count(*) FROM {_qualified(table)} WHERE _batch_id = ?", [batch_id]
    ).fetchone()[0]


def _validate_key_coverage(
    conn: duckdb.DuckDBPyConnection,
    table: BusinessContract,
    batch_id: str,
    expected_rows: int,
) -> None:
    keys = ", ".join(_quote(key) for key in table.business_keys)
    distinct = conn.execute(
        f"SELECT count(*) FROM (SELECT DISTINCT {keys} FROM {_qualified(table)} "
        "WHERE _batch_id = ?)",
        [batch_id],
    ).fetchone()[0]
    if distinct != expected_rows:
        raise LandingIngestionError(
            f"{table.schema_name}.{table.table}: key coverage {distinct} != {expected_rows}"
        )


def _batch_state(
    conn: duckdb.DuckDBPyConnection, source_id: str, fingerprint: str,
) -> str:
    rows = source_batch_history(conn, source_id)
    completed = [stored for stored, status in rows if status == COMPLETED_STATUS]
    if any(stored != fingerprint for stored in completed):
        raise ChangedSourceError(
            f"{source_id}: completed fingerprint changed; explicit versioned migration, backup, "
            "and approval are required"
        )
    if fingerprint in completed:
        return "COMPLETE"
    if rows:
        statuses = sorted({status for _, status in rows})
        raise IncompleteBatchError(
            f"{source_id}: prior batch status is not complete ({statuses}); refusing NO_OP"
        )
    return "NEW"


def _validate_idempotency(
    conn: duckdb.DuckDBPyConnection,
    fingerprints: dict[str, str],
) -> str:
    states = {source_id: _batch_state(conn, source_id, value)
              for source_id, value in fingerprints.items()}
    unique = set(states.values())
    if unique == {"COMPLETE"}:
        return "NO_OP"
    if unique != {"NEW"}:
        raise IncompleteBatchError(
            f"Inconsistent seven-source bootstrap state {states}; explicit recovery is required"
        )
    return "LOAD"


def ingest_landing(
    database: str | Path,
    *,
    execute: bool = False,
    root: str | Path = PROJECT_ROOT,
    registry_path: str | Path = "config/sources.yaml",
    contract_path: str | Path = "config/contract.yaml",
    entered_by: str = DEFAULT_ENTERED_BY,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> dict[str, Any]:
    """Plan by default; explicitly bootstrap only a non-production existing DuckDB."""
    project_root = Path(root).resolve()
    registry, contract, preflight = _load_configuration(
        project_root, registry_path, contract_path
    )
    if not execute:
        return {
            "mode": "DRY_RUN",
            "status": preflight["status"],
            "source_count": len(registry.active_sources),
            "table_count": len(contract.tables),
            "schema_count": len({table.schema_name for table in contract.tables.values()}),
            "historical_sources_loaded": 0,
            "pending_update_policies": sorted(contract.tables),
            "warnings": _warnings(preflight),
            "database_path": str(resolve_database(database)),
        }
    target = resolve_database(database)
    if target == DEFAULT_DATABASE:
        raise UnsafeWriteError(
            "V4-03 refuses production ingestion while update policies are PENDING_CONFIRMATION"
        )
    if not target.is_file():
        raise FileNotFoundError(
            f"DuckDB database not found: {target}; initialize an isolated database explicitly"
        )
    if not entered_by.strip():
        raise ValueError("entered_by must be non-empty")

    initialize_metadata(target, lock_timeout=lock_timeout)
    grouped = _tables_by_source(registry, contract)
    fingerprints = {
        source_id: _source_fingerprint(
            source_id, source, registry, contract, grouped[source_id]
        )
        for source_id, source in registry.active_sources.items()
    }
    warnings = _warnings(preflight)
    table_counts: dict[str, int] = {}
    batch_ids: dict[str, str] = {}
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()

    with transaction(
        target, lock_timeout=lock_timeout, owner_id="v4-03-initial-bootstrap"
    ) as conn:
        action = _validate_idempotency(conn, fingerprints)
        if action == "NO_OP":
            for name, table in contract.tables.items():
                if not _table_exists(conn, table):
                    raise IncompleteBatchError(
                        f"{name}: completed metadata exists but landing table is missing"
                    )
                _validate_existing_table(conn, name, table)
            return {
                "mode": "EXECUTE",
                "status": "NO_OP",
                "source_count": 7,
                "table_count": 14,
                "schema_count": 9,
                "table_row_counts": {},
                "warnings": warnings,
            }

        for name, table in contract.tables.items():
            if _table_exists(conn, table):
                _validate_existing_table(conn, name, table)
                count = conn.execute(f"SELECT count(*) FROM {_qualified(table)}").fetchone()[0]
                if count:
                    raise IncompleteBatchError(
                        f"{name}: populated landing table has no completed V4 fingerprint"
                    )
            else:
                _create_table(conn, table)

        for source_id, source in registry.active_sources.items():
            batch_id = f"v4-03-{source_id}-{uuid4().hex}"
            batch_ids[source_id] = batch_id
            lineage = json.dumps(
                {"mode": "INITIAL_HISTORICAL_BOOTSTRAP", "source_type": source.source_type},
                sort_keys=True,
            )
            start_source_batch(
                conn,
                batch_id=batch_id,
                source_id=source_id,
                source_path=source.path,
                source_fingerprint=fingerprints[source_id],
                contract_version=contract.contract_version,
                started_at=timestamp,
                source_row_count=source.row_count,
            )
            record_batch_status(
                conn,
                batch_id=batch_id,
                status="RUNNING",
                occurred_at=timestamp,
                actor=entered_by,
                reason=lineage,
            )
            for name, table in grouped[source_id]:
                loaded = _insert_table(
                    conn,
                    table=table,
                    source=source,
                    csv_path=source_path(source.path, project_root),
                    batch_id=batch_id,
                    loaded_at=now,
                    entered_by=entered_by,
                )
                if loaded != source.row_count:
                    raise LandingIngestionError(
                        f"{name}: loaded row count {loaded} != source row count {source.row_count}"
                    )
                _validate_key_coverage(conn, table, batch_id, source.row_count)
                table_counts[name] = loaded
                record_table_load(
                    conn,
                    batch_id=batch_id,
                    table_name=name,
                    source_row_count=source.row_count,
                    loaded_row_count=loaded,
                    recorded_at=timestamp,
                )
                record_entry_audit(
                    conn,
                    batch_id=batch_id,
                    actor=entered_by,
                    action="INITIAL_BOOTSTRAP",
                    target_table=name,
                    occurred_at=timestamp,
                    details_json=json.dumps(
                        {"source_type": source.source_type, "rows": loaded}, sort_keys=True
                    ),
                )
            complete_source_batch(conn, batch_id=batch_id, completed_at=timestamp)
            record_batch_status(
                conn,
                batch_id=batch_id,
                status=COMPLETED_STATUS,
                occurred_at=timestamp,
                actor=entered_by,
                reason=lineage,
            )

    return {
        "mode": "EXECUTE",
        "status": COMPLETED_STATUS,
        "source_count": len(registry.active_sources),
        "table_count": len(contract.tables),
        "schema_count": len({table.schema_name for table in contract.tables.values()}),
        "batch_ids": batch_ids,
        "table_row_counts": table_counts,
        "warnings": warnings,
    }
