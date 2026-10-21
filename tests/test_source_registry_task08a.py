"""Active regression tests for the versioned Task08A registry adapter."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from src.config.source_registry_task08a import (DEFAULT_REGISTRY, EXPECTED_TABLES, RegistryError,
                                                check_source_files, load_registry, registry_report,
                                                source_path, validate_registry)

ORDERS = "sales_ecommerce.orders_daily"


@pytest.fixture
def small():
    """Use one complete table definition, never require CSVs to exist for loading."""
    data = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    data["tables"] = [data["tables"][0]]
    data["source_files"] = {"orders": data["source_files"]["orders"]}
    return data


def validate(data, tmp_path):
    return validate_registry(data, root=tmp_path, expected_tables=frozenset({ORDERS}))


def write_config(path, data):
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_load_valid_yaml_without_source_files(small, tmp_path):
    path = tmp_path / "sources.yaml"
    write_config(path, small)
    registry = load_registry(path, root=tmp_path, expected_tables=frozenset({ORDERS}))
    assert registry.list_tables() == [ORDERS]
    assert not (tmp_path / "data").exists()


def test_yaml_syntax_error(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("tables: [\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="Cannot load registry"):
        load_registry(path, root=tmp_path)


def test_yaml_duplicate_keys_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("registry_version: 1\nregistry_version: 2\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="Duplicate YAML key"):
        load_registry(path, root=tmp_path)


def test_unsafe_yaml_tags_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("!!python/object/apply:os.system ['echo should-not-run']", encoding="utf-8")
    with pytest.raises(RegistryError, match="Cannot load registry"):
        load_registry(path, root=tmp_path)


@pytest.mark.parametrize("field", ["department", "grain", "columns", "upload", "schema_approval"])
def test_required_metadata_missing(small, tmp_path, field):
    del small["tables"][0][field]
    with pytest.raises(RegistryError, match="Invalid registry metadata"):
        validate(small, tmp_path)


def test_duplicate_table_name(small, tmp_path):
    small["tables"].append(deepcopy(small["tables"][0]))
    with pytest.raises(RegistryError, match="Duplicate source table"):
        validate(small, tmp_path)


def test_production_requires_all_fourteen(small, tmp_path):
    with pytest.raises(RegistryError, match="Expected source tables mismatch"):
        validate_registry(small, root=tmp_path)


@pytest.mark.parametrize("keys", [[], ["not_in_schema"], ["warehouse", "warehouse"]])
def test_invalid_business_keys(small, tmp_path, keys):
    small["tables"][0]["business_keys"] = keys
    with pytest.raises(RegistryError):
        validate(small, tmp_path)


@pytest.mark.parametrize("path", ["../outside.csv", "C:/private/file.csv", "/tmp/file.csv",
                                  "data/raw/orders/../train.csv", "data/raw/orders/test.csv",
                                  "https://example.com/file.csv", "data\\raw\\orders\\train.csv"])
def test_invalid_source_path(small, tmp_path, path):
    small["source_files"]["orders"]["path"] = path
    with pytest.raises(RegistryError, match="Source path outside"):
        validate(small, tmp_path)


def test_resolved_source_escape_blocked(tmp_path, monkeypatch):
    # Simulate symlink resolution without requiring Windows administrator privileges.
    target = tmp_path / "data/raw/orders/train.csv"
    external = tmp_path / "outside.csv"
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        return original(external) if path == target else original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(RegistryError, match="escapes"):
        source_path("data/raw/orders/train.csv", tmp_path)


def test_mapping_source_column_must_exist(small, tmp_path):
    small["tables"][0]["mappings"][0]["source_column"] = "unknown_column"
    with pytest.raises(RegistryError, match="source column not in verified metadata"):
        validate(small, tmp_path)


def test_mapping_unknown_file_or_target(small, tmp_path):
    small["tables"][0]["mappings"][0]["target"] = "unknown_target"
    with pytest.raises(RegistryError, match="undeclared file or target"):
        validate(small, tmp_path)


def test_target_cannot_be_unmapped(small, tmp_path):
    small["tables"][0]["mappings"].pop()
    with pytest.raises(RegistryError, match="require explicit direct mappings"):
        validate(small, tmp_path)


def test_unexpected_source_absence(small, tmp_path):
    registry = validate(small, tmp_path)
    errors = check_source_files(registry, tmp_path)
    assert len(errors) == 1 and "unexpected source absence" in errors[0]
    assert not (tmp_path / "data").exists()


def test_source_hash_check_detects_changes(small, tmp_path):
    path = tmp_path / "data/raw/orders/train.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture-only\n")
    small["source_files"]["orders"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    registry = validate(small, tmp_path)
    assert check_source_files(registry, tmp_path) == []
    path.write_bytes(b"changed-fixture\n")
    assert "source hash changed" in check_source_files(registry, tmp_path)[0]


def test_expected_finance_hr_missing_is_valid(tmp_path):
    data = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    registry = validate_registry(data, root=tmp_path)
    report = registry_report(registry)
    assert report["configuration"] == "VALID"
    assert report["missing_by_design"] == ["finance.cost_params", "hr.workforce_params"]
    assert report["task08"] == "NOT_READY"
    assert len(report["pending_decisions"]) == 14


def test_finance_hr_cannot_claim_real_data(tmp_path):
    data = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    data["tables"][-1]["source_availability"] = "VERIFIED"
    with pytest.raises(RegistryError, match="must remain MISSING"):
        validate_registry(data, root=tmp_path)


def test_pending_retained_and_get_api_returns_copy(small, tmp_path):
    registry = validate(small, tmp_path)
    table = registry.get_table(ORDERS)
    assert table.schema_approval.status == "PENDING_CONFIRMATION"
    assert table.upload.access == "BLOCKED_PENDING_APPROVAL"
    table.pending_decisions.clear()
    assert registry.get_table(ORDERS).pending_decisions
    assert registry.list_tables("sales_ecommerce") == [ORDERS]
    assert registry.list_tables("hr") == []
    with pytest.raises(KeyError):
        registry.get_table("unknown.table")


def test_cannot_approve_without_evidence(small, tmp_path):
    small["tables"][0]["schema_approval"]["status"] = "VERIFIED"
    with pytest.raises(RegistryError, match="approved_by and approved_at"):
        validate(small, tmp_path)


def test_approval_cannot_contradict_pending_columns(small, tmp_path):
    approval = small["tables"][0]["schema_approval"]
    approval.update(status="VERIFIED", approved_by="fixture-reviewer", approved_at="2026-10-18")
    with pytest.raises(RegistryError, match="verified keys and columns"):
        validate(small, tmp_path)


def test_upload_disabled_and_policy_pending(small, tmp_path):
    small["tables"][0]["upload"]["enabled"] = True
    with pytest.raises(RegistryError):
        validate(small, tmp_path)


def test_upload_columns_partition_checked(small, tmp_path):
    small["tables"][0]["upload"]["optional_columns"].append("warehouse")
    with pytest.raises(RegistryError, match="partition"):
        validate(small, tmp_path)


def test_no_database_connections_or_writes(small, tmp_path, monkeypatch):
    import duckdb
    import sqlite3
    def forbidden(*args, **kwargs):
        raise AssertionError("Registry must not connect to any database")
    monkeypatch.setattr(duckdb, "connect", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    path = tmp_path / "registry.yaml"
    write_config(path, small)
    before = path.read_bytes()
    load_registry(path, root=tmp_path, expected_tables=frozenset({ORDERS}))
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_production_metadata_preserves_task06_evidence():
    # No CSV existence needed; verified snapshot metadata is part of configuration.
    registry = load_registry()
    assert len(registry.tables) == len(EXPECTED_TABLES) == 14
    assert sum(len(source.columns) for source in registry.source_files.values()) == 64
    assert registry.get_table("sales_ecommerce.sku_sales_daily").columns[3].nullable is True
    assert "order_index" not in {c.name for t in registry.tables for c in t.columns}
    calendar = registry.get_table("planning.calendar")
    assert len(calendar.deferred_mappings) == 8
    assert "warehouse_limited" in {m.source_column for m in calendar.deferred_mappings}
    assert all(t.schema_approval.status == "PENDING_CONFIRMATION" for t in registry.tables)


def test_cli_metadata_only_json_with_temporary_config(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_bytes(DEFAULT_REGISTRY.read_bytes())
    result = subprocess.run([sys.executable, "-m", "src.validate_source_registry_task08a", "--config", str(path), "--metadata-only", "--json"],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["source_count"] == 14
    assert report["file_check"] == "NOT_CHECKED"
    assert report["task08"] == "NOT_READY"


def test_cli_bad_config_has_nonzero_exit(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("registry_version: [", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "src.validate_source_registry_task08a", "--config", str(path)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert "FAILED_CONFIGURATION" in result.stdout


def test_cli_missing_source_is_distinct_from_pending(small, tmp_path, monkeypatch, capsys):
    import src.validate_source_registry_task08a as cli
    registry = validate(small, tmp_path)
    monkeypatch.setattr(cli, "load_registry", lambda *a, **k: registry)
    monkeypatch.setattr(cli, "check_source_files", lambda *a, **k: check_source_files(registry, tmp_path))
    monkeypatch.setattr(sys, "argv", ["validate_source_registry"])
    assert cli.main() == 2
    assert "FAILED_SOURCE_FILES" in capsys.readouterr().out
