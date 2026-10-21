"""V4-03 landing ingestion tests; all writes use pytest temporary paths."""

from __future__ import annotations

import csv
from datetime import date, timedelta
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from src.config.source_registry import (
    DEFAULT_CONTRACT,
    DEFAULT_REGISTRY,
    EXPECTED_SCHEMAS,
    EXPECTED_TABLES,
    load_contract,
    load_registry,
)
from src.db.duckdb import (
    DEFAULT_DATABASE,
    UnsafeWriteError,
    WriterLockTimeout,
    connection,
    initialize_database,
    transaction,
)
from src.db.duckdb_metadata import initialize_metadata
from src.ingestion import landing
from src.ingestion.landing import (
    ChangedSourceError,
    IncompleteBatchError,
    ingest_landing,
    plan_landing_ingestion,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _row_value(source_id: str, column: str, kind: str, row_number: int) -> object:
    if column == "date":
        return (date(2026, 1, 1) + timedelta(days=row_number)).isoformat()
    if column == "unique_id":
        return row_number + 1
    if column == "product_unique_id":
        return row_number + 101
    if column == "warehouse":
        return f"warehouse_{row_number}"
    if column == "L1_category_name_en":
        return f"category_{row_number}"
    if column == "id":
        return f"id_{row_number}"
    if source_id == "sales" and column == "type_0_discount":
        return -0.25 if row_number == 0 else 0.25
    if kind in {"BIGINT", "DOUBLE"}:
        return 1
    return f"{column}_{row_number}"


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, Path]:
    registry_data = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    contract_text = DEFAULT_CONTRACT.read_text(encoding="utf-8")
    config = tmp_path / "config"
    config.mkdir()
    (config / "contract.yaml").write_text(contract_text, encoding="utf-8")

    desired_rows = {source_id: 2 for source_id in registry_data["active_sources"]}
    desired_rows["cost_params"] = 3
    desired_rows["workforce_params"] = 7
    for source_id, source in registry_data["active_sources"].items():
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(source["header"])
            for row_number in range(desired_rows[source_id]):
                writer.writerow([
                    _row_value(source_id, column, source["column_types"][column], row_number)
                    for column in source["header"]
                ])
        source["row_count"] = desired_rows[source_id]
        source["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    (config / "sources.yaml").write_text(
        yaml.safe_dump(registry_data, sort_keys=False), encoding="utf-8"
    )
    database = tmp_path / "warehouse" / "landing.duckdb"
    initialize_database(database)
    return tmp_path, database


def _execute(project: tuple[Path, Path], **kwargs):
    root, database = project
    return ingest_landing(database, execute=True, root=root, **kwargs)


def test_dry_run_is_default_and_has_exact_v4_scope(project):
    root, database = project
    before = database.read_bytes()
    report = ingest_landing(database, root=root)
    assert report["mode"] == "DRY_RUN"
    assert (report["source_count"], report["table_count"], report["schema_count"]) == (7, 14, 9)
    assert len(report["pending_update_policies"]) == 14
    assert report["historical_sources_loaded"] == 0
    assert database.read_bytes() == before
    assert plan_landing_ingestion(root=root)["table_count"] == 14


def test_first_ingest_creates_exact_contract_tables_and_types(project):
    root, database = project
    report = _execute(project)
    assert report["status"] == "COMPLETED"
    assert set(report["table_row_counts"]) == EXPECTED_TABLES
    registry = load_registry("config/sources.yaml", root=root)
    catalog = load_contract("config/contract.yaml", registry=registry, root=root)
    with connection(database) as conn:
        physical = conn.execute(
            """SELECT table_schema || '.' || table_name FROM information_schema.tables
               WHERE table_schema LIKE 'src\\_%' ESCAPE '\\' ORDER BY 1"""
        ).fetchall()
        schemas = conn.execute(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_schema LIKE 'src\\_%' ESCAPE '\\'"
        ).fetchall()
        assert {row[0] for row in physical} == EXPECTED_TABLES
        assert {row[0] for row in schemas} == EXPECTED_SCHEMAS
        for qualified, table in catalog.tables.items():
            actual = conn.execute(
                """SELECT column_name, data_type, is_nullable
                   FROM information_schema.columns
                   WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position""",
                [table.schema_name, table.table],
            ).fetchall()
            expected = [
                (name, column.type, "YES" if column.nullable else "NO")
                for name, column in table.columns.items()
            ] + [
                ("_batch_id", "VARCHAR", "NO"),
                ("_source", "VARCHAR", "NO"),
                ("_loaded_at", "TIMESTAMP", "NO"),
                ("_entered_by", "VARCHAR", "NO"),
            ]
            assert actual == expected, qualified


def test_hr_finance_mapping_counts_assumed_lineage_and_anomaly_preservation(project):
    report = _execute(project)
    assert report["table_row_counts"]["src_finance.cost_params"] == 3
    assert report["table_row_counts"]["src_hr.workforce_params"] == 7
    assert {warning["column"]: warning["count"] for warning in report["warnings"]} == {
        "type_0_discount": 1
    }
    with connection(project[1]) as conn:
        hr_columns = [row[1] for row in conn.execute(
            "PRAGMA table_info('src_hr.workforce_params')"
        ).fetchall()]
        for canonical in (
            "hourly_wage_eur", "morning_shift_ratio", "overtime_cap_ratio",
            "shortage_penalty_multiplier", "legacy_rule_buffer_ratio",
        ):
            assert canonical in hr_columns
        for raw in (
            "wage_eur_per_hour", "morning_share", "overtime_cap",
            "shortage_penalty", "rule_buffer",
        ):
            assert raw not in hr_columns
        assert conn.execute(
            "SELECT waste_handling_cost_ratio FROM src_finance.cost_params ORDER BY 1 LIMIT 1"
        ).fetchone() == (1.0,)
        assert conn.execute(
            "SELECT type_0_discount FROM src_marketing.promotions ORDER BY unique_id"
        ).fetchall() == [(-0.25,), (0.25,)]
        assumed_events = conn.execute(
            "SELECT count(*) FROM meta.batch_status_events WHERE reason LIKE '%ASSUMED%'"
        ).fetchone()[0]
        assert assumed_events == 4


def test_completed_fingerprint_is_noop_and_manual_rows_survive(project):
    _execute(project)
    with transaction(project[1]) as conn:
        conn.execute(
            """INSERT INTO src_sales.orders_daily
               SELECT warehouse, date, orders, 'manual-batch', _source, _loaded_at, 'tester'
               FROM src_sales.orders_daily LIMIT 1"""
        )
        before = conn.execute("SELECT count(*) FROM src_sales.orders_daily").fetchone()[0]
    report = _execute(project)
    assert report["status"] == "NO_OP"
    with connection(project[1]) as conn:
        assert conn.execute("SELECT count(*) FROM src_sales.orders_daily").fetchone() == (before,)


def test_changed_completed_fingerprint_is_blocked(project):
    root, _ = project
    _execute(project)
    registry_path = root / "config" / "sources.yaml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    source = data["active_sources"]["sales"]
    sales = root / source["path"]
    changed = sales.read_text(encoding="utf-8").replace("-0.25", "-0.20", 1)
    sales.write_text(changed, encoding="utf-8")
    source["sha256"] = hashlib.sha256(sales.read_bytes()).hexdigest()
    registry_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ChangedSourceError, match="explicit versioned migration"):
        _execute(project)


def test_failure_mid_ingest_rolls_back_landing_and_batch_metadata(project, monkeypatch):
    original = landing._insert_table
    calls = 0

    def fail_after_two(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("injected load failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(landing, "_insert_table", fail_after_two)
    with pytest.raises(RuntimeError, match="injected load failure"):
        _execute(project)
    with connection(project[1]) as conn:
        assert conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema LIKE 'src%'"
        ).fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM meta.source_batches").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM meta.table_loads").fetchone() == (0,)


@pytest.mark.parametrize("status", ["FAILED", "PARTIAL", "RUNNING", "UNKNOWN"])
def test_non_complete_prior_batch_never_claims_noop(project, status):
    root, database = project
    initialize_metadata(database)
    with transaction(database) as conn:
        conn.execute(
            """INSERT INTO meta.source_batches
               (batch_id, source_id, source_path, source_fingerprint, contract_version,
                status, started_at, source_row_count)
               VALUES ('old', 'orders', 'data/raw/orders/train.csv', 'old', 4, ?, 'now', 2)""",
            [status],
        )
    with pytest.raises(IncompleteBatchError, match="refusing NO_OP"):
        ingest_landing(database, execute=True, root=root)


def test_metadata_counts_reconcile_with_landing(project):
    _execute(project)
    with connection(project[1]) as conn:
        loads = conn.execute(
            "SELECT batch_id, table_name, loaded_row_count FROM meta.table_loads"
        ).fetchall()
        assert len(loads) == 14
        for batch_id, qualified, expected in loads:
            schema, table = qualified.split(".")
            actual = conn.execute(
                f'SELECT count(*) FROM "{schema}"."{table}" WHERE _batch_id = ?', [batch_id]
            ).fetchone()[0]
            assert actual == expected
        assert conn.execute(
            "SELECT count(*) FROM meta.source_batches WHERE status = 'COMPLETED'"
        ).fetchone() == (7,)


def test_writer_lock_conflict_then_safe_recovery(project):
    root, database = project
    holder_code = """
import sys
from src.db.duckdb import transaction
with transaction(sys.argv[1], lock_timeout=5, owner_id='landing-test-holder'):
    print('LOCKED', flush=True)
    sys.stdin.readline()
"""
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(database)],
        cwd=PROJECT_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "LOCKED"
    try:
        with pytest.raises(WriterLockTimeout):
            ingest_landing(database, execute=True, root=root, lock_timeout=0.2)
    finally:
        assert holder.stdin is not None
        holder.stdin.write("release\n")
        holder.stdin.flush()
        stdout, stderr = holder.communicate(timeout=10)
        assert holder.returncode == 0, stdout + stderr
    assert ingest_landing(database, execute=True, root=root)["status"] == "COMPLETED"


def test_production_database_execution_is_blocked_before_open(project):
    root, _ = project
    with pytest.raises(UnsafeWriteError, match="PENDING_CONFIRMATION"):
        ingest_landing(DEFAULT_DATABASE, execute=True, root=root)
