"""Authenticated, allowlisted, read-only access to Rohlik reporting marts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterator, Mapping, Sequence

import duckdb

from src.db.duckdb import DEFAULT_DATABASE, connection, resolve_database


ALLOWED_MARTS = (
    "mart.sales_orders_day",
    "mart.ops_warehouse_day",
    "mart.category_sku_day",
    "mart.marketing_promo_day",
    "mart.exec_kpi_month",
)
MAX_PAGE_SIZE = 500
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
    "FLOAT", "DOUBLE", "DECIMAL", "REAL",
}
_DATE_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_TZ"}


class ReportingError(RuntimeError):
    """Base error for safe reporting failures."""


class UnsafeReportingQuery(ReportingError):
    """A caller requested a table, column, filter, or page outside the allowlist."""


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str

    @property
    def is_numeric(self) -> bool:
        base = self.data_type.upper().split("(", 1)[0]
        return base in _NUMERIC_TYPES

    @property
    def is_temporal(self) -> bool:
        return self.data_type.upper() in _DATE_TYPES


@dataclass(frozen=True)
class MartInfo:
    name: str
    exists: bool
    columns: tuple[ColumnInfo, ...] = ()

    def column(self, name: str) -> ColumnInfo | None:
        return next((column for column in self.columns if column.name == name), None)

    @property
    def numeric_columns(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns if column.is_numeric)

    @property
    def temporal_columns(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns if column.is_temporal)


@dataclass(frozen=True)
class WarehouseInfo:
    database: Path
    exists: bool
    marts: tuple[MartInfo, ...]

    @property
    def ready_mart_count(self) -> int:
        return sum(mart.exists for mart in self.marts)


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


def _require_admin() -> object:
    # Lazy import avoids coupling the data module to Streamlit during import.
    from app.auth import require_admin

    return require_admin()


def _split_mart(name: str) -> tuple[str, str]:
    if name not in ALLOWED_MARTS:
        raise UnsafeReportingQuery(f"Reporting mart is not allowlisted: {name}")
    schema, table = name.split(".", 1)
    return schema, table


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise UnsafeReportingQuery(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def _qualified(name: str) -> str:
    schema, table = _split_mart(name)
    return f"{_quote_identifier(schema)}.{_quote_identifier(table)}"


class ReportingService:
    """Read reporting data through fixed operations and schema-checked identifiers."""

    def __init__(self, database: str | Path = DEFAULT_DATABASE) -> None:
        self.database = resolve_database(database)

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        try:
            with connection(self.database) as conn:
                yield conn
        except ReportingError:
            raise
        except (duckdb.Error, OSError) as exc:
            raise ReportingError("Warehouse cannot be opened read-only.") from exc

    def warehouse_info(self) -> WarehouseInfo:
        _require_admin()
        if not self.database.is_file():
            missing = tuple(MartInfo(name, False) for name in ALLOWED_MARTS)
            return WarehouseInfo(self.database, False, missing)
        try:
            with self._connection() as conn:
                marts = tuple(self._mart_info(conn, name) for name in ALLOWED_MARTS)
        except (duckdb.Error, OSError) as exc:
            raise ReportingError("Warehouse cannot be opened read-only.") from exc
        return WarehouseInfo(self.database, True, marts)

    def mart_info(self, name: str) -> MartInfo:
        _require_admin()
        _split_mart(name)
        if not self.database.is_file():
            return MartInfo(name, False)
        try:
            with self._connection() as conn:
                return self._mart_info(conn, name)
        except (duckdb.Error, OSError) as exc:
            raise ReportingError("Warehouse cannot be opened read-only.") from exc

    def row_count(self, name: str, *, filters: Mapping[str, object] | None = None) -> int:
        _require_admin()
        with self._connection() as conn:
            info = self._require_mart(conn, name)
            where, parameters = self._where_clause(info, filters or {})
            return int(conn.execute(f"SELECT count(*) FROM {_qualified(name)}{where}", parameters).fetchone()[0])

    def distinct_values(self, name: str, column: str, *, limit: int = 200) -> tuple[object, ...]:
        _require_admin()
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise UnsafeReportingQuery("Distinct-value limit is outside the safe range.")
        with self._connection() as conn:
            info = self._require_mart(conn, name)
            self._require_column(info, column)
            quoted = _quote_identifier(column)
            rows = conn.execute(
                f"SELECT DISTINCT {quoted} FROM {_qualified(name)} "
                f"WHERE {quoted} IS NOT NULL ORDER BY {quoted} LIMIT ?",
                [limit],
            ).fetchall()
        return tuple(row[0] for row in rows)

    def date_bounds(self, name: str, column: str) -> tuple[object | None, object | None]:
        _require_admin()
        with self._connection() as conn:
            info = self._require_mart(conn, name)
            metadata = self._require_column(info, column)
            if not metadata.is_temporal:
                raise UnsafeReportingQuery(f"Column is not temporal: {column}")
            quoted = _quote_identifier(column)
            row = conn.execute(
                f"SELECT min({quoted}), max({quoted}) FROM {_qualified(name)}"
            ).fetchone()
        return row[0], row[1]

    def fetch_page(
        self,
        name: str,
        *,
        columns: Sequence[str] | None = None,
        filters: Mapping[str, object] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> QueryResult:
        _require_admin()
        if limit < 1 or limit > MAX_PAGE_SIZE or offset < 0:
            raise UnsafeReportingQuery("Pagination is outside the safe range.")
        with self._connection() as conn:
            info = self._require_mart(conn, name)
            selected = tuple(columns) if columns else tuple(column.name for column in info.columns)
            if not selected:
                raise UnsafeReportingQuery("No reporting columns are available.")
            for column in selected:
                self._require_column(info, column)
            projection = ", ".join(_quote_identifier(column) for column in selected)
            where, parameters = self._where_clause(info, filters or {})
            rows = conn.execute(
                f"SELECT {projection} FROM {_qualified(name)}{where} "
                "ORDER BY ALL LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        return QueryResult(selected, tuple(tuple(row) for row in rows))

    def aggregate_series(
        self,
        name: str,
        *,
        date_column: str,
        metric_column: str,
        filters: Mapping[str, object] | None = None,
        limit: int = 366,
    ) -> QueryResult:
        _require_admin()
        if limit < 1 or limit > 2000:
            raise UnsafeReportingQuery("Series limit is outside the safe range.")
        with self._connection() as conn:
            info = self._require_mart(conn, name)
            date_meta = self._require_column(info, date_column)
            metric_meta = self._require_column(info, metric_column)
            if not date_meta.is_temporal or not metric_meta.is_numeric:
                raise UnsafeReportingQuery("Series requires one temporal and one numeric column.")
            date_sql = _quote_identifier(date_column)
            metric_sql = _quote_identifier(metric_column)
            where, parameters = self._where_clause(info, filters or {})
            rows = conn.execute(
                f"SELECT {date_sql} AS period, sum({metric_sql}) AS value "
                f"FROM {_qualified(name)}{where} GROUP BY {date_sql} "
                f"ORDER BY {date_sql} LIMIT ?",
                [*parameters, limit],
            ).fetchall()
        return QueryResult(("period", "value"), tuple(tuple(row) for row in rows))

    @staticmethod
    def _mart_info(conn: duckdb.DuckDBPyConnection, name: str) -> MartInfo:
        schema, table = _split_mart(name)
        rows = conn.execute(
            """SELECT column_name, data_type
               FROM information_schema.columns
               WHERE table_schema = ? AND table_name = ?
               ORDER BY ordinal_position""",
            [schema, table],
        ).fetchall()
        if not rows:
            return MartInfo(name, False)
        return MartInfo(name, True, tuple(ColumnInfo(str(row[0]), str(row[1])) for row in rows))

    def _require_mart(self, conn: duckdb.DuckDBPyConnection, name: str) -> MartInfo:
        info = self._mart_info(conn, name)
        if not info.exists:
            raise ReportingError(f"Reporting mart is not available: {name}")
        return info

    @staticmethod
    def _require_column(info: MartInfo, column: str) -> ColumnInfo:
        metadata = info.column(column)
        if metadata is None:
            raise UnsafeReportingQuery(f"Column is not present in {info.name}: {column}")
        return metadata

    def _where_clause(
        self, info: MartInfo, filters: Mapping[str, object]
    ) -> tuple[str, list[object]]:
        conditions: list[str] = []
        parameters: list[object] = []
        for column, value in filters.items():
            metadata = self._require_column(info, column)
            quoted = _quote_identifier(column)
            if isinstance(value, tuple):
                if len(value) != 2 or not metadata.is_temporal:
                    raise UnsafeReportingQuery(
                        f"Range filters require a temporal column: {column}"
                    )
                start, end = value
                if start is not None:
                    conditions.append(f"{quoted} >= ?")
                    parameters.append(start)
                if end is not None:
                    conditions.append(f"{quoted} <= ?")
                    parameters.append(end)
            elif value is not None:
                conditions.append(f"{quoted} = ?")
                parameters.append(value)
        return (" WHERE " + " AND ".join(conditions) if conditions else "", parameters)
