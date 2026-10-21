"""Read-only source registry, without CSV parsing, ingestion or database access."""

from collections import Counter
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "sources_task08a.yaml"
Status = Literal["VERIFIED", "REFERENCE_ONLY", "PENDING_CONFIRMATION", "MISSING", "NOT_APPLICABLE"]
Text = Annotated[str, Field(min_length=1)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
ALLOWED_SOURCE_PATHS = frozenset({
    "data/raw/orders/train.csv", "data/raw/orders/train_calendar.csv",
    "data/raw/sales/sales_train.csv", "data/raw/sales/inventory.csv",
    "data/raw/sales/calendar.csv", "data/raw/sales/test_weights.csv",
})
EXPECTED_TABLES = frozenset({
    "sales_ecommerce.orders_daily", "sales_ecommerce.sku_sales_daily",
    "marketing_pricing.prices", "marketing_pricing.promotions",
    "marketing_pricing.min_order_value_changes", "warehouse_ops.availability",
    "warehouse_ops.ops_events", "category.product_master", "planning.calendar",
    "digital_product.user_activity", "external.weather", "finance.sku_weights",
    "finance.cost_params", "hr.workforce_params",
})
MISSING_TABLES = frozenset({"finance.cost_params", "hr.workforce_params"})
TYPES = {"VARCHAR", "TEXT", "DATE", "BIGINT", "INTEGER", "DOUBLE", "REAL", "BOOLEAN"}
RULES = frozenset(f"SRC-{i:02}" for i in range(1, 27))
BATCH_METADATA = frozenset({
    "batch_id", "source_table", "department", "uploaded_by", "uploaded_at",
    "original_filename", "file_hash", "total_rows", "accepted_rows", "rejected_rows", "status",
})


class RegistryError(ValueError):
    """Configuration errors, distinct from pending business decisions."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Decision(StrictModel):
    status: Status
    detail: Text
    evidence: Text
    approved_by: str | None = None
    approved_at: str | None = None

    @model_validator(mode="after")
    def approval_evidence(self) -> Self:
        if self.status == "VERIFIED" and not (self.approved_by and self.approved_at):
            raise ValueError("VERIFIED decisions require approved_by and approved_at")
        return self


class ObservedColumn(StrictModel):
    inferred_type: Text
    null_count: Annotated[int, Field(ge=0)]


class SourceFile(StrictModel):
    path: Text
    verification_status: Literal["VERIFIED"]
    evidence: Text
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    row_count: Annotated[int, Field(ge=0)]
    encoding: Text
    delimiter: Text
    header: Literal[True]
    columns: dict[Identifier, ObservedColumn]

    @model_validator(mode="after")
    def observed_metadata(self) -> Self:
        if not self.columns or any(c.null_count > self.row_count for c in self.columns.values()):
            raise ValueError("Source columns required; null_count cannot exceed row_count")
        return self


class Column(StrictModel):
    name: Identifier
    proposed_duckdb_type: str | None
    proposed_sqlite_type: str | None
    nullable: bool | None
    required: bool | None
    definition: Text
    status: Status

    @model_validator(mode="after")
    def proposed_types(self) -> Self:
        for field in (self.proposed_duckdb_type, self.proposed_sqlite_type):
            if field is not None and field not in TYPES:
                raise ValueError(f"Unsupported proposed type: {field}; unresolved precision uses null")
        if self.status == "VERIFIED" and (self.proposed_duckdb_type is None or self.required is None or self.nullable is None):
            raise ValueError("VERIFIED column cannot have unresolved type/required/nullable")
        return self


class Mapping(StrictModel):
    target: Identifier
    file_id: Identifier
    source_column: Identifier
    kind: Literal["DIRECT"]
    status: Status


class DeferredMapping(StrictModel):
    file_id: Identifier
    source_column: Identifier
    proposed_target: Identifier | None
    decision: Decision


class Upload(StrictModel):
    eligibility: Decision
    access: Literal["BLOCKED_PENDING_APPROVAL", "READ_ONLY", "UPDATABLE"]
    enabled: Literal[False]  # Task 07 is design only; never an authorization service.
    allowed_columns: list[Identifier]
    required_columns: list[Identifier]
    optional_columns: list[Identifier]
    unresolved_columns: list[Identifier]
    backend_authorization_required: Literal[True]
    write_policy: Decision
    duplicate_policy: Decision
    batch_metadata_ref: Literal["upload_batch_metadata"]
    validation_refs: list[Text]


class SourceTable(StrictModel):
    name: Annotated[str, Field(pattern=r"^[a-z_]+\.[a-z_]+$")]
    department: Identifier
    description: Text
    source_type: Literal["HISTORICAL_CSV", "MISSING_EXTERNAL_CSV"]
    source_files: list[Identifier]
    source_availability: Literal["VERIFIED", "MISSING"]
    grain: Decision
    business_keys: Annotated[list[Identifier], Field(min_length=1)]
    key_status: Status
    columns: Annotated[list[Column], Field(min_length=1)]
    mappings: list[Mapping]
    deferred_mappings: list[DeferredMapping]
    transformations: list[Decision]
    dq_rules: Annotated[list[Text], Field(min_length=1)]
    consumers: list[Annotated[str, Field(pattern=r"^BT[1-8]$")]]
    consumer_status: Status
    schema_approval: Decision
    mapping_approval: Decision
    expected_rows: Decision
    upload: Upload
    provenance: Annotated[list[Text], Field(min_length=1)]
    pending_decisions: list[Text]


class Registry(StrictModel):
    registry_version: Literal[1]
    scope: Text
    source_files: dict[Identifier, SourceFile]
    upload_batch_metadata: Annotated[list[Identifier], Field(min_length=1)]
    global_decisions: dict[Identifier, Decision]
    analysis_only_derived_fields: dict[Identifier, Decision]
    tables: Annotated[list[SourceTable], Field(min_length=1)]

    def get_table(self, name: str) -> SourceTable:
        """Get validated metadata; returns a copy so a caller cannot mutate registry state."""
        for table in self.tables:
            if table.name == name:
                return table.model_copy(deep=True)
        raise KeyError(f"Unknown source table: {name}")

    def list_tables(self, department: str | None = None) -> list[str]:
        """List registered logical names, optionally scoped to the owning department."""
        return [table.name for table in self.tables if department is None or table.department == department]


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loading that rejects silent overwrites by duplicate mapping keys."""


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise RegistryError("YAML mapping keys must be strings")
        if key in mapping:
            raise RegistryError(f"Duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def source_path(path: str, root: Path = PROJECT_ROOT) -> Path:
    """Resolve only the six approved local CSV paths, rejecting traversal and symlink escape."""
    relative = PurePosixPath(path)
    if (path not in ALLOWED_SOURCE_PATHS or "\\" in path or relative.is_absolute()
            or PureWindowsPath(path).drive or ".." in relative.parts):
        raise RegistryError(f"Source path outside approved six-file allowlist: {path}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to((root / "data" / "raw").resolve()) or not resolved.is_relative_to(root.resolve()):
        raise RegistryError(f"Source path escapes project raw directory: {path}")
    return resolved


def validate_registry(data: object, *, root: Path = PROJECT_ROOT,
                      expected_tables: frozenset[str] = EXPECTED_TABLES) -> Registry:
    """Validate structure, paths and cross-references without requiring CSV files to exist.

    expected_tables can narrow scope for tests; the CLI always requires all 14.
    VERIFIED file metadata documents Task 06 evidence, not schema approval.
    """
    try:
        registry = Registry.model_validate(data)
    except ValidationError as exc:
        raise RegistryError(f"Invalid registry metadata: {exc}") from exc
    names = [table.name for table in registry.tables]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    if duplicates:
        raise RegistryError(f"Duplicate source table names: {duplicates}")
    if set(names) != expected_tables:
        raise RegistryError(f"Expected source tables mismatch; missing={sorted(expected_tables-set(names))}; extra={sorted(set(names)-expected_tables)}")
    if not BATCH_METADATA.issubset(registry.upload_batch_metadata) or len(set(registry.upload_batch_metadata)) != len(registry.upload_batch_metadata):
        raise RegistryError("Upload batch metadata must contain all required fields without duplicates")
    if not registry.global_decisions:
        raise RegistryError("Global business decisions are required")
    paths = []
    for source in registry.source_files.values():
        source_path(source.path, root)
        paths.append(source.path)
    if len(set(paths)) != len(paths):
        raise RegistryError("Source catalog has duplicate file paths")
    if expected_tables == EXPECTED_TABLES and set(paths) != ALLOWED_SOURCE_PATHS:
        raise RegistryError("Production registry must describe the six verified source files")
    for table in registry.tables:
        prefix = table.name + ": "
        if table.department != table.name.split(".")[0]:
            raise RegistryError(prefix + "department does not match table namespace")
        cols = {column.name: column for column in table.columns}
        if len(cols) != len(table.columns) or len(set(table.business_keys)) != len(table.business_keys):
            raise RegistryError(prefix + "duplicate columns or business keys")
        if not set(table.business_keys).issubset(cols):
            raise RegistryError(prefix + "business keys must exist in target schema")
        if any(cols[key].nullable is True or cols[key].required is False for key in table.business_keys):
            raise RegistryError(prefix + "business key cannot be nullable/optional in a proposed schema")
        if len(set(table.source_files)) != len(table.source_files) or not set(table.source_files).issubset(registry.source_files):
            raise RegistryError(prefix + "unknown/duplicate source file reference")
        missing = table.name in MISSING_TABLES
        if missing:
            if (table.source_availability != "MISSING" or table.source_type != "MISSING_EXTERNAL_CSV"
                    or table.source_files or table.mappings):
                raise RegistryError(prefix + "Finance/HR must remain MISSING without fabricated paths/mappings")
        elif table.source_availability != "VERIFIED" or table.source_type != "HISTORICAL_CSV" or not table.source_files:
            raise RegistryError(prefix + "historical sources need VERIFIED file evidence; use file checks for unexpected absence")
        mapped = set()
        mapping_keys = set()
        for mapping in table.mappings:
            if mapping.file_id not in table.source_files or mapping.target not in cols:
                raise RegistryError(prefix + "mapping references undeclared file or target column")
            source = registry.source_files[mapping.file_id]
            if mapping.source_column not in source.columns:
                raise RegistryError(prefix + f"source column not in verified metadata: {mapping.source_column}")
            key = (mapping.target, mapping.file_id, mapping.source_column)
            if key in mapping_keys:
                raise RegistryError(prefix + "duplicate mapping")
            mapping_keys.add(key)
            mapped.add(mapping.target)
            if mapping.target == "order_index":
                raise RegistryError(prefix + "order_index belongs to analysis, not a CSV source column")
        if not missing and mapped != set(cols):
            raise RegistryError(prefix + "all proposed source targets require explicit direct mappings")
        for deferred in table.deferred_mappings:
            if (deferred.file_id not in table.source_files
                    or deferred.source_column not in registry.source_files[deferred.file_id].columns):
                raise RegistryError(prefix + "deferred source column missing from verified metadata")
            if deferred.decision.status != "PENDING_CONFIRMATION":
                raise RegistryError(prefix + "deferred mappings must remain pending until explicitly mapped")
        if not set(table.dq_rules).issubset(RULES):
            raise RegistryError(prefix + "unknown Data Quality rule reference")
        upload = table.upload
        if not set(upload.validation_refs).issubset(RULES | {"docs/csv_upload_contract.md"}):
            raise RegistryError(prefix + "unknown upload validation reference")
        groups = [set(upload.required_columns), set(upload.optional_columns), set(upload.unresolved_columns)]
        if (set(upload.allowed_columns) != set(cols) or len(upload.allowed_columns) != len(cols)
                or set().union(*groups) != set(cols) or any(groups[i] & groups[j] for i in range(3) for j in range(i+1,3))
                or sum(len(x) for x in [upload.required_columns, upload.optional_columns, upload.unresolved_columns]) != len(cols)):
            raise RegistryError(prefix + "upload allowed/required/optional/unresolved columns must form a partition of target schema")
        for name, column in cols.items():
            expected_group = upload.required_columns if column.required is True else upload.optional_columns if column.required is False else upload.unresolved_columns
            if name not in expected_group:
                raise RegistryError(prefix + "upload requirement lists disagree with column metadata")
        if (upload.access == "UPDATABLE" and upload.eligibility.status != "VERIFIED"):
            raise RegistryError(prefix + "UPDATABLE needs verified eligibility, not a department supplied by the client")
        decisions = [table.schema_approval, table.mapping_approval, table.grain, upload.eligibility,
                     upload.write_policy, upload.duplicate_policy, *table.transformations]
        if any(d.status == "PENDING_CONFIRMATION" for d in decisions) and not table.pending_decisions:
            raise RegistryError(prefix + "pending policies need explicit pending_decisions")
        if missing and any(d.status == "VERIFIED" for d in [table.schema_approval, table.mapping_approval]):
            raise RegistryError(prefix + "missing Finance/HR schema/mapping cannot be reported approved")
        if table.schema_approval.status == "VERIFIED" and (table.key_status != "VERIFIED" or any(c.status != "VERIFIED" for c in table.columns)):
            raise RegistryError(prefix + "approved schema requires verified keys and columns")
        if table.mapping_approval.status == "VERIFIED" and any(m.status != "VERIFIED" for m in table.mappings):
            raise RegistryError(prefix + "approved mapping requires verified field mappings")
    return registry


def load_registry(path: str | Path = DEFAULT_REGISTRY, *, root: Path = PROJECT_ROOT,
                  expected_tables: frozenset[str] = EXPECTED_TABLES) -> Registry:
    """Load YAML safely; relative config paths resolve against root, never cwd."""
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        data = yaml.load(candidate.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RegistryError(f"Cannot load registry {candidate}: {exc}") from exc
    return validate_registry(data, root=root, expected_tables=expected_tables)


def check_source_files(registry: Registry, root: Path = PROJECT_ROOT) -> list[str]:
    """Read-only existence/hash verification, no CSV parser or database connection."""
    errors = []
    for file_id, source in registry.source_files.items():
        path = source_path(source.path, root)
        try:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != source.sha256:
                errors.append(f"{file_id}: source hash changed; rerun profiling and review metadata")
        except OSError as exc:
            errors.append(f"{file_id}: unexpected source absence/unreadable file: {path}: {exc}")
    return errors


def registry_report(registry: Registry) -> dict:
    """Summarize valid configuration separately from source existence and business readiness."""
    pending = {t.name: t.pending_decisions for t in registry.tables if t.pending_decisions}
    return {
        "configuration": "VALID", "source_count": len(registry.tables),
        "verified_source_files": len(registry.source_files),
        "missing_by_design": [t.name for t in registry.tables if t.source_availability == "MISSING"],
        "table_status": {t.name: {"source": t.source_availability, "schema": t.schema_approval.status,
                                  "mapping": t.mapping_approval.status, "upload": t.upload.eligibility.status} for t in registry.tables},
        "pending_decisions": pending,
        "global_pending": {k: v.detail for k, v in registry.global_decisions.items() if v.status == "PENDING_CONFIRMATION"},
        "task08": "NOT_READY" if pending or any(t.source_availability == "MISSING" for t in registry.tables)
                  or any(t.schema_approval.status != "VERIFIED" or t.mapping_approval.status != "VERIFIED" for t in registry.tables)
                  or any(d.status == "PENDING_CONFIRMATION" for d in registry.global_decisions.values()) else "PARTIALLY_READY",
        "execution": "NOT_IMPLEMENTED: configuration only; no ingestion or upload authorized",
    }
