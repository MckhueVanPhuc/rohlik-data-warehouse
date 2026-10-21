"""V4 registry, contract and read-only source preflight tests."""

import csv
import hashlib
from pathlib import Path

import pytest
import yaml

from src.config.source_registry import (
    ACTIVE_SOURCE_PATHS,
    DEFAULT_CONTRACT,
    DEFAULT_REGISTRY,
    EXPECTED_SCHEMAS,
    EXPECTED_TABLES,
    RegistryError,
    load_contract,
    load_registry,
    preflight_sources,
    validate_contract,
    validate_registry,
)


def registry_data() -> dict:
    return yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))


def contract_data() -> dict:
    return yaml.safe_load(DEFAULT_CONTRACT.read_text(encoding="utf-8"))


def make_source_fixture(tmp_path: Path, data: dict) -> None:
    """Replace production evidence with one valid row per active source."""
    for source_id, source in data["active_sources"].items():
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        row = []
        for column in source["header"]:
            kind = source["column_types"][column]
            if column == "date":
                value = "2026-01-01"
            elif kind in {"BIGINT", "DOUBLE"}:
                value = "1"
            else:
                value = f"{source_id}_{column}"
            row.append(value)
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(source["header"])
            writer.writerow(row)
        source["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        source["row_count"] = 1


def test_production_registry_has_exactly_seven_active_sources_and_historical_calendar():
    registry = load_registry()
    assert len(registry.active_sources) == 7
    assert {source.path for source in registry.active_sources.values()} == ACTIVE_SOURCE_PATHS
    assert all(source.status == "ACTIVE" for source in registry.active_sources.values())
    historical = registry.historical_sources["orders_calendar"]
    assert historical.status == "HISTORICAL_ONLY"
    assert historical.path == "data/raw/orders/train_calendar.csv"
    assert historical.path not in ACTIVE_SOURCE_PATHS


def test_contract_has_exactly_fourteen_tables_and_nine_schemas():
    catalog = load_contract()
    assert set(catalog.tables) == EXPECTED_TABLES
    assert len(catalog.tables) == 14
    assert {table.schema_name for table in catalog.tables.values()} == EXPECTED_SCHEMAS


def test_cost_and_hr_headers_and_assumed_status():
    registry = load_registry()
    assert registry.active_sources["cost_params"].header == [
        "L1_category_name_en", "cost_ratio", "shelf_life_days", "waste_handling_cost_ratio"
    ]
    assert registry.active_sources["workforce_params"].header == [
        "warehouse", "wage_eur_per_hour", "items_per_order", "picks_per_hour",
        "shift_hours", "morning_share", "overtime_multiplier", "overtime_cap",
        "shortage_penalty", "rule_buffer", "orders_per_driver_shift",
    ]
    assert registry.active_sources["cost_params"].source_type == "ASSUMED"
    assert registry.active_sources["workforce_params"].source_type == "ASSUMED"
    catalog = load_contract(registry=registry)
    assert catalog.tables["src_finance.cost_params"].source_type == "ASSUMED"
    assert catalog.tables["src_hr.workforce_params"].source_type == "ASSUMED"


def test_hr_mapping_has_five_renames_and_all_eleven_canonical_columns():
    table = load_contract().tables["src_hr.workforce_params"]
    renames = {raw: canonical for raw, canonical in table.mapping.items() if raw != canonical}
    assert renames == {
        "wage_eur_per_hour": "hourly_wage_eur",
        "morning_share": "morning_shift_ratio",
        "overtime_cap": "overtime_cap_ratio",
        "shortage_penalty": "shortage_penalty_multiplier",
        "rule_buffer": "legacy_rule_buffer_ratio",
    }
    assert len(table.columns) == len(table.mapping) == 11


def test_hr_source_has_seven_unique_warehouse_keys(tmp_path):
    data = registry_data()
    make_source_fixture(tmp_path, data)
    source = data["active_sources"]["workforce_params"]
    target = tmp_path / source["path"]
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(source["header"])
        for number in range(7):
            writer.writerow([f"warehouse_{number}", *([1] * 10)])
    source["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    source["row_count"] = 7
    report = preflight_sources(validate_registry(data, root=tmp_path), root=tmp_path)
    hr = report["sources"]["workforce_params"]
    assert hr["row_count"] == 7
    assert hr["business_keys"] == ["warehouse"]
    assert hr["duplicate_key_groups"] == hr["null_key_rows"] == 0


def test_tmp_path_preflight_is_read_only_and_valid(tmp_path):
    data = registry_data()
    make_source_fixture(tmp_path, data)
    registry = validate_registry(data, root=tmp_path)
    before = {source.path: (tmp_path / source.path).read_bytes() for source in registry.active_sources.values()}
    report = preflight_sources(registry, root=tmp_path)
    after = {source.path: (tmp_path / source.path).read_bytes() for source in registry.active_sources.values()}
    assert report["active_source_count"] == 7
    assert before == after
    assert not (tmp_path / "data/warehouse").exists()


def test_missing_source_is_blocked(tmp_path):
    data = registry_data()
    make_source_fixture(tmp_path, data)
    missing = tmp_path / data["active_sources"]["cost_params"]["path"]
    missing.unlink()
    with pytest.raises(RegistryError, match="MISSING"):
        preflight_sources(validate_registry(data, root=tmp_path), root=tmp_path)


def test_wrong_header_is_blocked(tmp_path):
    data = registry_data()
    make_source_fixture(tmp_path, data)
    target = tmp_path / data["active_sources"]["workforce_params"]["path"]
    text = target.read_text(encoding="utf-8").replace("wage_eur_per_hour", "wrong_wage", 1)
    target.write_text(text, encoding="utf-8")
    data["active_sources"]["workforce_params"]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(RegistryError, match="wrong header"):
        preflight_sources(validate_registry(data, root=tmp_path), root=tmp_path)


def test_duplicate_business_key_is_blocked(tmp_path):
    data = registry_data()
    make_source_fixture(tmp_path, data)
    target = tmp_path / data["active_sources"]["cost_params"]["path"]
    lines = target.read_text(encoding="utf-8").splitlines()
    target.write_text("\n".join([lines[0], lines[1], lines[1]]) + "\n", encoding="utf-8")
    source = data["active_sources"]["cost_params"]
    source["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    source["row_count"] = 2
    with pytest.raises(RegistryError, match="duplicate_groups=1"):
        preflight_sources(validate_registry(data, root=tmp_path), root=tmp_path)


def test_duplicate_yaml_keys_are_blocked(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("registry_version: 4\nregistry_version: 4\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="Duplicate YAML key"):
        load_registry(path, root=tmp_path)


@pytest.mark.parametrize("unsafe", ["../outside.csv", "C:/private.csv", "/tmp/file.csv",
                                     "data/raw/orders/../train.csv", "data\\raw\\orders\\train.csv"])
def test_unsafe_source_paths_are_blocked(tmp_path, unsafe):
    data = registry_data()
    data["active_sources"]["orders"]["path"] = unsafe
    with pytest.raises(RegistryError, match="allowlist|seven unique"):
        validate_registry(data, root=tmp_path)


def test_contract_mapping_must_cover_canonical_columns():
    registry = load_registry()
    data = contract_data()
    del data["tables"]["src_hr.workforce_params"]["mapping"]["rule_buffer"]
    with pytest.raises(RegistryError, match="exact canonical columns"):
        validate_contract(data, registry)


def test_update_policies_are_explicitly_pending_not_invented():
    assert all(table.update_policy == "PENDING_CONFIRMATION" for table in load_contract().tables.values())
