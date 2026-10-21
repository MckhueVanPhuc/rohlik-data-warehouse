"""Task 08A tests. Every database and CSV write is confined to tmp_path."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import duckdb
import pytest
import yaml

from src.config.source_registry_task08a import DEFAULT_REGISTRY, load_registry
from src.ingestion import source_bootstrap as bootstrap


def _value(column: str, row: int) -> str:
    if column == "date":
        return f"2024-01-0{row + 1}"
    if column == "warehouse":
        return f"Warehouse_{row + 1}"
    if column == "unique_id":
        return str(row + 1)
    if column == "product_unique_id":
        return str(100 + row)
    if column == "id":
        return f"Warehouse_{row + 1}_2024-01-0{row + 1}"
    if column == "name":
        return f"Product_{row + 1}"
    if column.startswith("L") and column.endswith("_category_name_en"):
        return f"Category_{column[1]}"
    if column == "holiday_name":
        return "" if row == 0 else "Fixture Holiday"
    if column in {"sales", "total_orders"} and row == 0:
        return ""
    if column == "type_0_discount" and row == 1:
        return "-0.1"
    if column == "weight":
        return str(0.5 + row)
    if column in {"orders", "user_activity_1", "user_activity_2"}:
        return str(10 + row)
    return "0"


def _rewrite_metadata(data: dict, root: Path, file_id: str, rows: list[dict[str, str]]) -> None:
    source = data["source_files"][file_id]
    path = root / source["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(source["columns"])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    source["row_count"] = len(rows)
    source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in columns:
        source["columns"][name]["null_count"] = sum(row[name] == "" for row in rows)


def _write_config(root: Path, data: dict) -> Path:
    path = root / "config" / "sources.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def tiny_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    data = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    for file_id, source in data["source_files"].items():
        columns = list(source["columns"])
        rows = [{name: _value(name, row) for name in columns} for row in range(2)]
        # Inventory row 2 is intentionally inventory-only while source keys remain unique.
        if file_id == "inventory":
            rows[1]["unique_id"] = "3"
        _rewrite_metadata(data, tmp_path, file_id, rows)
    config = _write_config(tmp_path, data)
    database = tmp_path / "data" / "warehouse" / "bootstrap.duckdb"
    return tmp_path, config, database


@pytest.fixture
def executed(tiny_project):
    root, config, database = tiny_project
    report = bootstrap.execute_provisional(
        root=root, registry_path=config, output_database=database,
        report_dir=root / "data" / "exports" / "source_bootstrap",
    )
    return root, config, database, report


def test_valid_registry_and_preflight(tiny_project):
    root, config, database = tiny_project
    registry, report = bootstrap.preflight(
        root=root, registry_path=config, output_database=database,
        report_dir=root / "data" / "exports" / "source_bootstrap",
    )
    assert len(registry.tables) == 14
    assert report["status"] == "READY_PROVISIONAL"
    assert report["calendar"]["conflict_cells"] == 0


def test_missing_source_is_blocked(tiny_project):
    root, config, database = tiny_project
    (root / "data/raw/orders/train.csv").unlink()
    with pytest.raises(bootstrap.BootstrapError, match="absence|unreadable"):
        bootstrap.preflight(root=root, registry_path=config, output_database=database,
                            report_dir=root / "data/exports/source_bootstrap")


def test_sha_mismatch_is_blocked(tiny_project):
    root, config, database = tiny_project
    with (root / "data/raw/orders/train.csv").open("a", encoding="utf-8") as stream:
        stream.write("changed\n")
    with pytest.raises(bootstrap.BootstrapError, match="hash changed"):
        bootstrap.preflight(root=root, registry_path=config, output_database=database,
                            report_dir=root / "data/exports/source_bootstrap")


def test_missing_source_column_is_blocked_after_hash_check(tiny_project):
    root, config, database = tiny_project
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    source = data["source_files"]["orders"]
    path = root / source["path"]
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("orders", "orders_missing", 1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_config(root, data)
    with pytest.raises(bootstrap.BootstrapError, match="source columns changed"):
        bootstrap.preflight(root=root, registry_path=config, output_database=database,
                            report_dir=root / "data/exports/source_bootstrap")


@pytest.mark.parametrize("relative", ["data/input.db", "data/warehouse/rohlik.duckdb", "outside.duckdb"])
def test_unsafe_database_paths_rejected(tmp_path, relative):
    with pytest.raises(bootstrap.BootstrapError, match="Unsafe|inside data/warehouse"):
        bootstrap.validate_output_database(tmp_path / relative, tmp_path)


def test_dry_run_does_not_create_database_or_modify_sources(tiny_project):
    root, config, database = tiny_project
    before = {path: path.read_bytes() for path in (root / "data/raw").rglob("*.csv")}
    bootstrap.preflight(root=root, registry_path=config, output_database=database,
                        report_dir=root / "data/exports/source_bootstrap")
    assert not database.exists()
    assert all(path.read_bytes() == content for path, content in before.items())


def test_bronze_preserves_null_negative_and_all_columns(executed):
    _, _, database, _ = executed
    conn = duckdb.connect(str(database), read_only=True)
    try:
        assert conn.execute("SELECT count(*) FROM bronze.raw_sales WHERE sales IS NULL").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM bronze.raw_sales WHERE type_0_discount < 0").fetchone()[0] == 1
        assert len(conn.execute("DESCRIBE bronze.raw_orders").fetchall()) == 18
    finally:
        conn.close()


def test_projection_uses_registry_columns(executed):
    _, config, database, _ = executed
    registry = load_registry(config, root=config.parents[1])
    conn = duckdb.connect(str(database), read_only=True)
    try:
        for table in registry.tables:
            if table.name in bootstrap.MISSING_TABLES:
                continue
            actual = [row[0] for row in conn.execute(f"DESCRIBE {table.name}").fetchall()]
            assert actual == [column.name for column in table.columns]
        assert conn.execute(
            "SELECT unique_id,date,warehouse,sales,total_orders FROM sales_ecommerce.sku_sales_daily ORDER BY unique_id"
        ).fetchall() == conn.execute(
            "SELECT unique_id,date,warehouse,sales,total_orders FROM bronze.raw_sales ORDER BY unique_id"
        ).fetchall()
    finally:
        conn.close()


def test_duplicate_business_key_is_blocked(tiny_project):
    root, config, database = tiny_project
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    source = data["source_files"]["sales"]
    path = root / source["path"]
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[1]["unique_id"] = rows[0]["unique_id"]
    rows[1]["date"] = rows[0]["date"]
    _rewrite_metadata(data, root, "sales", rows)
    _write_config(root, data)
    with pytest.raises(bootstrap.BootstrapError, match="duplicate_groups=1"):
        bootstrap.preflight(root=root, registry_path=config, output_database=database,
                            report_dir=root / "data/exports/source_bootstrap")


def test_row_count_reconciliation_and_lineage(executed):
    _, _, _, report = executed
    assert set(report["bronze_row_counts"]) == {
        "bronze.raw_orders", "bronze.raw_orders_calendar", "bronze.raw_sales",
        "bronze.raw_inventory", "bronze.raw_sales_calendar", "bronze.raw_weights",
    }
    assert all(item["source_row_count"] == item["loaded_row_count"] == 2
               for item in report["source_lineage"])
    assert all(len(item["sha256"]) == 64 for item in report["source_lineage"])


def test_finance_hr_missing_create_no_tables(executed):
    _, _, database, report = executed
    conn = duckdb.connect(str(database), read_only=True)
    try:
        names = {row[0] for row in conn.execute("SHOW ALL TABLES").fetchall()}
        # SHOW ALL TABLES layout varies; information_schema is stable for the assertion.
        logical = {f"{s}.{t}" for s, t in conn.execute(
            "SELECT table_schema,table_name FROM information_schema.tables"
        ).fetchall()}
    finally:
        conn.close()
    assert "finance.cost_params" not in logical
    assert "hr.workforce_params" not in logical
    missing = {x["table_name"]: x["status"] for x in report["table_loads"]}
    assert missing["finance.cost_params"] == missing["hr.workforce_params"] == "SKIPPED_MISSING"


def test_calendar_shared_fields_have_no_row_multiplication(executed):
    _, _, database, report = executed
    conn = duckdb.connect(str(database), read_only=True)
    try:
        assert conn.execute("SELECT count(*) FROM planning.calendar").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM planning.calendar GROUP BY warehouse,date HAVING count(*)>1").fetchall() == []
    finally:
        conn.close()
    assert report["calendar"]["overlap_rows"] == 2


def test_calendar_conflict_is_detected_and_marked_pending(tiny_project):
    root, config, database = tiny_project
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    source = data["source_files"]["orders_calendar"]
    path = root / source["path"]
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[1]["holiday"] = "1"
    _rewrite_metadata(data, root, "orders_calendar", rows)
    _write_config(root, data)
    _, report = bootstrap.preflight(root=root, registry_path=config, output_database=database,
                                    report_dir=root / "data/exports/source_bootstrap")
    assert report["status"] == "PARTIAL"
    assert report["calendar"]["conflicts"]["holiday"] == 1
    assert next(x for x in report["table_plan"] if x["table"] == "planning.calendar")["status"] == "SKIPPED_PENDING"


def test_idempotent_rerun_is_noop(executed):
    root, config, database, first = executed
    second = bootstrap.execute_provisional(
        root=root, registry_path=config, output_database=database,
        report_dir=root / "data/exports/source_bootstrap",
    )
    assert first["run"]["run_id"] == second["run"]["run_id"]
    assert second["idempotent_noop"] is True
    conn = duckdb.connect(str(database), read_only=True)
    try:
        assert conn.execute("SELECT count(*) FROM bootstrap_meta.bootstrap_runs").fetchone()[0] == 1
    finally:
        conn.close()


def test_midrun_failure_is_recorded_not_success(tiny_project, monkeypatch):
    root, config, database = tiny_project
    monkeypatch.setattr(bootstrap, "_load_projections", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fixture abort")))
    with pytest.raises(bootstrap.BootstrapError, match="fixture abort"):
        bootstrap.execute_provisional(
            root=root, registry_path=config, output_database=database,
            report_dir=root / "data/exports/source_bootstrap",
        )
    conn = duckdb.connect(str(database), read_only=True)
    try:
        assert conn.execute("SELECT status FROM bootstrap_meta.bootstrap_runs").fetchone()[0] == "FAILED"
        assert conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='bronze'").fetchone()[0] == 0
    finally:
        conn.close()
    report = bootstrap.validate_existing(root=root, output_database=database)
    assert report["status"] == "FAILED"
    assert report["bronze_row_counts"] == {}


def test_existing_unowned_database_is_rejected(tiny_project):
    root, config, database = tiny_project
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(database))
    conn.execute("CREATE TABLE unrelated(value INTEGER)")
    conn.close()
    with pytest.raises(bootstrap.BootstrapError, match="not owned"):
        bootstrap.execute_provisional(root=root, registry_path=config, output_database=database,
                                      report_dir=root / "data/exports/source_bootstrap")


def test_validate_report_reflects_database_status(executed):
    root, _, database, _ = executed
    report = bootstrap.validate_existing(root=root, output_database=database)
    assert report["status"] == "SUCCESS"
    assert report["ownership"]["component"] == "TASK_08A"
    assert len(report["table_loads"]) == 14
    assert any(item["status"] == "WARN" for item in report["dq_results"])


def test_report_written_only_under_exports(executed):
    root, _, _, report = executed
    path = bootstrap.write_report(report, root / "data/exports/source_bootstrap", root)
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["run"]["status"] == "SUCCESS"
    with pytest.raises(bootstrap.BootstrapError, match="inside project data/exports"):
        bootstrap.write_report(report, root / "reports", root)


def test_source_and_protected_database_bytes_unchanged(tiny_project):
    root, config, database = tiny_project
    sqlite = root / "data/input.db"
    primary = root / "data/warehouse/rohlik.duckdb"
    sqlite.parent.mkdir(parents=True, exist_ok=True)
    primary.parent.mkdir(parents=True, exist_ok=True)
    sqlite.write_bytes(b"sqlite-protected-fixture")
    primary.write_bytes(b"duckdb-protected-fixture")
    sources = {path: path.read_bytes() for path in (root / "data/raw").rglob("*.csv")}
    bootstrap.execute_provisional(root=root, registry_path=config, output_database=database,
                                  report_dir=root / "data/exports/source_bootstrap")
    assert sqlite.read_bytes() == b"sqlite-protected-fixture"
    assert primary.read_bytes() == b"duckdb-protected-fixture"
    assert all(path.read_bytes() == value for path, value in sources.items())
