"""Versioned, non-destructive metadata foundation for future V4 ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from src.db.duckdb import DEFAULT_DATABASE, DEFAULT_LOCK_TIMEOUT, connection, transaction

METADATA_COMPONENT = "v4_duckdb_safety_foundation"
METADATA_SCHEMA_VERSION = 1

_TABLE_DDL = {
    "schema_versions": """
        CREATE TABLE IF NOT EXISTS meta.schema_versions (
            component VARCHAR PRIMARY KEY,
            version INTEGER NOT NULL,
            applied_at VARCHAR NOT NULL,
            description VARCHAR NOT NULL
        )
    """,
    "source_batches": """
        CREATE TABLE IF NOT EXISTS meta.source_batches (
            batch_id VARCHAR PRIMARY KEY,
            source_id VARCHAR NOT NULL,
            source_path VARCHAR NOT NULL,
            source_fingerprint VARCHAR NOT NULL,
            contract_version INTEGER NOT NULL,
            status VARCHAR NOT NULL,
            started_at VARCHAR NOT NULL,
            completed_at VARCHAR,
            source_row_count BIGINT,
            error_message VARCHAR
        )
    """,
    "table_loads": """
        CREATE TABLE IF NOT EXISTS meta.table_loads (
            batch_id VARCHAR NOT NULL,
            table_name VARCHAR NOT NULL,
            source_row_count BIGINT NOT NULL,
            loaded_row_count BIGINT NOT NULL,
            rejected_row_count BIGINT NOT NULL,
            status VARCHAR NOT NULL,
            recorded_at VARCHAR NOT NULL,
            PRIMARY KEY (batch_id, table_name)
        )
    """,
    "batch_status_events": """
        CREATE TABLE IF NOT EXISTS meta.batch_status_events (
            event_id VARCHAR PRIMARY KEY,
            batch_id VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            occurred_at VARCHAR NOT NULL,
            actor VARCHAR NOT NULL,
            reason VARCHAR
        )
    """,
    "entry_audit_events": """
        CREATE TABLE IF NOT EXISTS meta.entry_audit_events (
            event_id VARCHAR PRIMARY KEY,
            batch_id VARCHAR,
            actor VARCHAR NOT NULL,
            action VARCHAR NOT NULL,
            target_table VARCHAR NOT NULL,
            occurred_at VARCHAR NOT NULL,
            details_json VARCHAR
        )
    """,
}

_EXPECTED_COLUMNS = {
    "schema_versions": ["component", "version", "applied_at", "description"],
    "source_batches": [
        "batch_id", "source_id", "source_path", "source_fingerprint", "contract_version",
        "status", "started_at", "completed_at", "source_row_count", "error_message",
    ],
    "table_loads": [
        "batch_id", "table_name", "source_row_count", "loaded_row_count",
        "rejected_row_count", "status", "recorded_at",
    ],
    "batch_status_events": ["event_id", "batch_id", "status", "occurred_at", "actor", "reason"],
    "entry_audit_events": [
        "event_id", "batch_id", "actor", "action", "target_table", "occurred_at", "details_json",
    ],
}


class MetadataVersionError(RuntimeError):
    """The on-disk metadata version/shape is incompatible with this code."""


def _validate_shapes(conn: duckdb.DuckDBPyConnection) -> None:
    for table, expected in _EXPECTED_COLUMNS.items():
        actual = [row[1] for row in conn.execute(f"PRAGMA table_info('meta.{table}')").fetchall()]
        if actual != expected:
            raise MetadataVersionError(
                f"meta.{table} has incompatible columns; expected={expected}, actual={actual}"
            )


def initialize_metadata(
    path: str | Path = DEFAULT_DATABASE,
    *,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> dict[str, Any]:
    """Create metadata v1 idempotently; reject unknown versions without migration."""
    created = False
    with transaction(path, lock_timeout=lock_timeout, owner_id="metadata-initializer") as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS meta")
        for ddl in _TABLE_DDL.values():
            conn.execute(ddl)
        _validate_shapes(conn)
        row = conn.execute(
            "SELECT version FROM meta.schema_versions WHERE component = ?", [METADATA_COMPONENT]
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO meta.schema_versions VALUES (?, ?, ?, ?)",
                [
                    METADATA_COMPONENT,
                    METADATA_SCHEMA_VERSION,
                    datetime.now(timezone.utc).isoformat(),
                    "V4-02 safety metadata only; business update/conflict policies remain pending",
                ],
            )
            created = True
        elif row[0] != METADATA_SCHEMA_VERSION:
            raise MetadataVersionError(
                f"Unsupported {METADATA_COMPONENT} version {row[0]}; expected {METADATA_SCHEMA_VERSION}; "
                "explicit reviewed migration required"
            )
    return {
        "component": METADATA_COMPONENT,
        "version": METADATA_SCHEMA_VERSION,
        "created": created,
        "tables": [f"meta.{name}" for name in _TABLE_DDL],
    }


def metadata_status(path: str | Path = DEFAULT_DATABASE) -> dict[str, Any]:
    """Read metadata version without creating a database or schema."""
    with connection(path) as conn:
        exists = conn.execute(
            """SELECT count(*) FROM information_schema.tables
               WHERE table_schema = 'meta' AND table_name = 'schema_versions'"""
        ).fetchone()[0]
        if not exists:
            return {"initialized": False, "component": METADATA_COMPONENT}
        row = conn.execute(
            "SELECT version, applied_at, description FROM meta.schema_versions WHERE component = ?",
            [METADATA_COMPONENT],
        ).fetchone()
    if row is None:
        return {"initialized": False, "component": METADATA_COMPONENT}
    return {
        "initialized": True,
        "component": METADATA_COMPONENT,
        "version": row[0],
        "applied_at": row[1],
        "description": row[2],
    }
