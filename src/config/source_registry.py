"""V4 production source registry and read-only source/contract preflight."""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "sources.yaml"
DEFAULT_CONTRACT = PROJECT_ROOT / "config" / "contract.yaml"

ACTIVE_SOURCE_PATHS = frozenset({
    "data/raw/orders/train.csv",
    "data/raw/sales/sales_train.csv",
    "data/raw/sales/inventory.csv",
    "data/raw/sales/calendar.csv",
    "data/raw/sales/test_weights.csv",
    "data/raw/assumptions/cost_params.csv",
    "data/raw/assumptions/workforce_params.csv",
})
ACTIVE_SOURCE_IDS = frozenset({
    "orders", "sales", "inventory", "calendar", "weights", "cost_params", "workforce_params"
})
HISTORICAL_SOURCE_PATH = "data/raw/orders/train_calendar.csv"
EXPECTED_TABLES = frozenset({
    "src_sales.orders_daily", "src_sales.sku_sales_daily",
    "src_marketing.prices", "src_marketing.promotions", "src_marketing.mov_changes",
    "src_ops.availability", "src_ops.ops_events", "src_category.product_master",
    "src_planning.calendar", "src_digital.user_activity", "src_external.weather",
    "src_finance.sku_weights", "src_finance.cost_params", "src_hr.workforce_params",
})
EXPECTED_SCHEMAS = frozenset({
    "src_sales", "src_marketing", "src_ops", "src_category", "src_planning",
    "src_digital", "src_external", "src_finance", "src_hr",
})
ASSUMED_SOURCES = frozenset({"cost_params", "workforce_params"})
DUCKDB_TYPES = frozenset({"VARCHAR", "DATE", "BIGINT", "DOUBLE", "BOOLEAN"})
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]


class RegistryError(ValueError):
    """Invalid configuration or a blocking source preflight failure."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RangeCheck(StrictModel):
    min: float | int | None = None
    max: float | int | None = None

    @model_validator(mode="after")
    def valid_range(self) -> "RangeCheck":
        if self.min is None and self.max is None:
            raise ValueError("a value check needs min and/or max")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("value check min cannot exceed max")
        return self


class ActiveSource(StrictModel):
    path: str
    status: Literal["ACTIVE"]
    source_type: Literal["KAGGLE_ORIGINAL", "ASSUMED"]
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    row_count: Annotated[int, Field(ge=0)]
    encoding: Literal["UTF-8"]
    bom: bool
    header: Annotated[list[Identifier], Field(min_length=1)]
    column_types: dict[Identifier, str]
    business_keys: Annotated[list[Identifier], Field(min_length=1)]
    checks: dict[Identifier, RangeCheck]
    evidence: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def consistent_columns(self) -> "ActiveSource":
        header = set(self.header)
        if len(header) != len(self.header):
            raise ValueError("duplicate source header")
        if set(self.column_types) != header:
            raise ValueError("column_types must describe the exact source header")
        if any(value not in DUCKDB_TYPES for value in self.column_types.values()):
            raise ValueError("unsupported DuckDB type")
        if len(set(self.business_keys)) != len(self.business_keys) or not set(self.business_keys) <= header:
            raise ValueError("business_keys must be unique source columns")
        if not set(self.checks) <= header:
            raise ValueError("checks must reference source columns")
        return self


class HistoricalSource(StrictModel):
    path: str
    status: Literal["HISTORICAL_ONLY"]
    reason: Annotated[str, Field(min_length=1)]


class Registry(StrictModel):
    registry_version: Literal[4]
    scope: Literal["V4_LOCAL_FIRST_SOURCE_CONTRACT"]
    contract_file: Literal["config/contract.yaml"]
    active_sources: dict[Identifier, ActiveSource]
    historical_sources: dict[Identifier, HistoricalSource]


class ContractColumn(StrictModel):
    type: str
    required: bool
    nullable: bool


class BusinessContract(StrictModel):
    schema_name: Identifier = Field(alias="schema")
    table: Identifier
    raw_source: str
    mapping: dict[Identifier, Identifier]
    grain: Annotated[str, Field(min_length=1)]
    business_keys: Annotated[list[Identifier], Field(min_length=1)]
    columns: dict[Identifier, ContractColumn]
    editable_fields: list[Identifier]
    checks: dict[Identifier, RangeCheck]
    schema_version: Annotated[int, Field(ge=1)]
    source_type: Literal["KAGGLE_ORIGINAL", "ASSUMED"]
    update_policy: Literal["PENDING_CONFIRMATION"]


class ContractCatalog(StrictModel):
    contract_version: Literal[4]
    status: Literal["IMPLEMENTED_FOUNDATION"]
    tables: dict[str, BusinessContract]


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader which refuses silent duplicate-key overwrites."""


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise RegistryError("YAML mapping keys must be strings")
        if key in result:
            raise RegistryError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _load_yaml(path: Path) -> object:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RegistryError(f"Cannot load YAML {path}: {exc}") from exc


def _safe_relative_path(path: str, allowed: frozenset[str], root: Path) -> Path:
    relative = PurePosixPath(path)
    if (path not in allowed or "\\" in path or relative.is_absolute()
            or PureWindowsPath(path).drive or ".." in relative.parts):
        raise RegistryError(f"Source path outside V4 allowlist: {path}")
    resolved = (root / path).resolve()
    raw = (root / "data" / "raw").resolve()
    if not resolved.is_relative_to(raw) or not resolved.is_relative_to(root.resolve()):
        raise RegistryError(f"Source path escapes project raw directory: {path}")
    return resolved


def source_path(path: str, root: Path = PROJECT_ROOT) -> Path:
    """Resolve one of the seven active V4 source paths."""
    return _safe_relative_path(path, ACTIVE_SOURCE_PATHS, root)


def validate_registry(data: object, *, root: Path = PROJECT_ROOT) -> Registry:
    try:
        registry = Registry.model_validate(data)
    except ValidationError as exc:
        raise RegistryError(f"Invalid V4 registry metadata: {exc}") from exc
    if set(registry.active_sources) != ACTIVE_SOURCE_IDS:
        raise RegistryError("V4 registry must contain exactly the seven approved active source IDs")
    paths = [source.path for source in registry.active_sources.values()]
    if len(set(paths)) != 7 or set(paths) != ACTIVE_SOURCE_PATHS:
        raise RegistryError("V4 registry must contain exactly seven unique active source paths")
    for source_id, source in registry.active_sources.items():
        source_path(source.path, root)
        expected_type = "ASSUMED" if source_id in ASSUMED_SOURCES else "KAGGLE_ORIGINAL"
        if source.source_type != expected_type:
            raise RegistryError(f"{source_id}: source_type must be {expected_type}")
    if set(registry.historical_sources) != {"orders_calendar"}:
        raise RegistryError("Only orders_calendar may be retained as historical-only")
    historical = registry.historical_sources["orders_calendar"]
    _safe_relative_path(historical.path, frozenset({HISTORICAL_SOURCE_PATH}), root)
    if historical.path in paths:
        raise RegistryError("train_calendar cannot be active in V4")
    return registry


def validate_contract(data: object, registry: Registry) -> ContractCatalog:
    try:
        catalog = ContractCatalog.model_validate(data)
    except ValidationError as exc:
        raise RegistryError(f"Invalid V4 business contract: {exc}") from exc
    if set(catalog.tables) != EXPECTED_TABLES:
        raise RegistryError(
            f"Expected 14 business contracts; missing={sorted(EXPECTED_TABLES-set(catalog.tables))}; "
            f"extra={sorted(set(catalog.tables)-EXPECTED_TABLES)}"
        )
    if {table.schema_name for table in catalog.tables.values()} != EXPECTED_SCHEMAS:
        raise RegistryError("V4 contracts must use exactly the nine approved src_* schemas")
    sources_by_path = {source.path: source for source in registry.active_sources.values()}
    for qualified, table in catalog.tables.items():
        if qualified != f"{table.schema_name}.{table.table}":
            raise RegistryError(f"{qualified}: schema/table fields disagree with qualified name")
        source = sources_by_path.get(table.raw_source)
        if source is None:
            raise RegistryError(f"{qualified}: raw_source is not one of the seven active sources")
        if table.source_type != source.source_type:
            raise RegistryError(f"{qualified}: source_type disagrees with source registry")
        if not table.mapping or not set(table.mapping) <= set(source.header):
            raise RegistryError(f"{qualified}: mapping references an unknown raw column")
        if set(table.mapping.values()) != set(table.columns):
            raise RegistryError(f"{qualified}: mapping must cover the exact canonical columns")
        if len(set(table.business_keys)) != len(table.business_keys) or not set(table.business_keys) <= set(table.columns):
            raise RegistryError(f"{qualified}: invalid business keys")
        if any(table.columns[key].nullable for key in table.business_keys):
            raise RegistryError(f"{qualified}: business keys cannot be nullable")
        if not set(table.editable_fields) <= set(table.columns) or not set(table.checks) <= set(table.columns):
            raise RegistryError(f"{qualified}: editable/check fields must be canonical columns")
        if any(column.type not in DUCKDB_TYPES for column in table.columns.values()):
            raise RegistryError(f"{qualified}: unsupported canonical DuckDB type")
    return catalog


def load_registry(path: str | Path = DEFAULT_REGISTRY, *, root: Path = PROJECT_ROOT) -> Registry:
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    return validate_registry(_load_yaml(candidate), root=root)


def load_contract(path: str | Path = DEFAULT_CONTRACT, *, registry: Registry | None = None,
                  root: Path = PROJECT_ROOT) -> ContractCatalog:
    active_registry = registry or load_registry(root=root)
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved != (root / "config" / "contract.yaml").resolve():
        raise RegistryError("Contract path must be config/contract.yaml inside the project")
    return validate_contract(_load_yaml(resolved), active_registry)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reader_sql(source: ActiveSource) -> str:
    fields = ", ".join(f"'{name}': '{kind}'" for name, kind in source.column_types.items())
    return "read_csv(?, header=true, columns={" + fields + "}, strict_mode=true, ignore_errors=false, encoding='utf-8')"


def _preflight_one(conn: duckdb.DuckDBPyConnection, source_id: str, source: ActiveSource,
                   root: Path) -> dict[str, Any]:
    path = source_path(source.path, root)
    if not path.is_file():
        raise RegistryError(f"{source_id}: MISSING source file: {path}")
    with path.open("rb") as stream:
        prefix = stream.read(3)
    actual_bom = prefix == b"\xef\xbb\xbf"
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            actual_header = next(csv.reader(stream))
    except (OSError, UnicodeError, StopIteration, csv.Error) as exc:
        raise RegistryError(f"{source_id}: cannot read UTF-8 CSV header: {exc}") from exc
    if actual_bom != source.bom:
        raise RegistryError(f"{source_id}: BOM mismatch; expected={source.bom}, actual={actual_bom}")
    if actual_header != source.header:
        raise RegistryError(f"{source_id}: wrong header; expected={source.header}, actual={actual_header}")
    actual_hash = _sha256(path)
    if actual_hash != source.sha256:
        raise RegistryError(f"{source_id}: SHA-256 mismatch; source changed")
    reader = _reader_sql(source)
    keys = ", ".join(f'"{key}"' for key in source.business_keys)
    null_key_filter = " OR ".join(f'"{key}" IS NULL' for key in source.business_keys)
    check_exprs: list[str] = []
    null_exprs = [
        f'count(*) FILTER (WHERE "{name}" IS NULL) AS "null__{name}"'
        for name in source.header
    ]
    for name, limits in source.checks.items():
        conditions = []
        if limits.min is not None:
            conditions.append(f'"{name}" < {float(limits.min)}')
        if limits.max is not None:
            conditions.append(f'"{name}" > {float(limits.max)}')
        check_exprs.append(
            f"count(*) FILTER (WHERE {' OR '.join(conditions)}) AS \"check__{name}\""
        )
    select_checks = ", " + ", ".join([*null_exprs, *check_exprs])
    try:
        result = conn.execute(
            f"SELECT count(*) AS row_count{select_checks} FROM {reader}", [str(path)]
        )
        row = result.fetchone()
        stats = dict(zip([column[0] for column in result.description], row))
        duplicate_groups, duplicate_rows, null_key_rows = conn.execute(
            f"""WITH source AS (SELECT * FROM {reader}), grouped AS (
                    SELECT {keys}, count(*) AS n FROM source GROUP BY {keys})
                SELECT count(*) FILTER (WHERE n > 1),
                       coalesce(sum(n - 1) FILTER (WHERE n > 1), 0),
                       (SELECT count(*) FROM source WHERE {null_key_filter})
                FROM grouped""",
            [str(path)],
        ).fetchone()
    except duckdb.Error as exc:
        raise RegistryError(f"{source_id}: data type/CSV parse failed: {exc}") from exc
    if stats["row_count"] != source.row_count:
        raise RegistryError(
            f"{source_id}: row count mismatch; expected={source.row_count}, actual={stats['row_count']}"
        )
    if duplicate_groups or null_key_rows:
        raise RegistryError(
            f"{source_id}: business key failed; duplicate_groups={duplicate_groups}, "
            f"duplicate_rows={duplicate_rows}, null_key_rows={null_key_rows}"
        )
    violations = {name.removeprefix("check__"): count for name, count in stats.items()
                  if name.startswith("check__") and count}
    null_counts = {name.removeprefix("null__"): count for name, count in stats.items()
                   if name.startswith("null__")}
    return {
        "path": source.path,
        "status": "VERIFIED_WITH_WARNINGS" if violations else "VERIFIED",
        "source_type": source.source_type,
        "sha256": actual_hash,
        "encoding": source.encoding,
        "bom": actual_bom,
        "header": actual_header,
        "required_columns": source.header,
        "row_count": stats["row_count"],
        "column_types": source.column_types,
        "null_counts": null_counts,
        "business_keys": source.business_keys,
        "duplicate_key_groups": duplicate_groups,
        "null_key_rows": null_key_rows,
        "constraint_violations": violations,
    }


def preflight_sources(registry: Registry, *, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Read all seven active CSVs without writing raw files or opening a warehouse."""
    conn = duckdb.connect(":memory:")
    try:
        conn.execute("SET threads=2")
        conn.execute("SET memory_limit='1GB'")
        sources = {
            source_id: _preflight_one(conn, source_id, source, root)
            for source_id, source in registry.active_sources.items()
        }
    finally:
        conn.close()
    return {
        "status": "VERIFIED_WITH_WARNINGS" if any(s["constraint_violations"] for s in sources.values()) else "VERIFIED",
        "active_source_count": len(sources),
        "sources": sources,
        "historical_only": {
            name: {"path": item.path, "status": item.status, "exists": (root / item.path).is_file()}
            for name, item in registry.historical_sources.items()
        },
    }


def check_source_files(registry: Registry, root: Path = PROJECT_ROOT) -> list[str]:
    """Compatibility API: return blocking full-preflight errors as a list."""
    try:
        preflight_sources(registry, root=root)
    except RegistryError as exc:
        return [str(exc)]
    return []


def registry_report(registry: Registry, contract: ContractCatalog | None = None) -> dict[str, Any]:
    catalog = contract or load_contract(registry=registry)
    return {
        "configuration": "VALID",
        "registry_version": registry.registry_version,
        "active_source_count": len(registry.active_sources),
        "active_source_paths": [source.path for source in registry.active_sources.values()],
        "historical_only": [source.path for source in registry.historical_sources.values()],
        "contract_count": len(catalog.tables),
        "schemas": sorted({table.schema_name for table in catalog.tables.values()}),
        "assumed_sources": sorted(
            source_id for source_id, source in registry.active_sources.items() if source.source_type == "ASSUMED"
        ),
        "pending_update_policies": sorted(
            name for name, table in catalog.tables.items() if table.update_policy == "PENDING_CONFIRMATION"
        ),
        "execution": "NOT_IMPLEMENTED: contract/preflight only; no ingestion or database writes",
    }
