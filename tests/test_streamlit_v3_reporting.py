"""Read-only reporting adapter tests using temporary DuckDB fixtures."""

from hashlib import sha256
from datetime import date
from pathlib import Path

import duckdb
import pytest

from app.services import reporting
from app.services.reporting import ReportingError, ReportingService, UnsafeReportingQuery


@pytest.fixture(autouse=True)
def authenticated(monkeypatch):
    calls = []
    monkeypatch.setattr(reporting, "_require_admin", lambda: calls.append("admin") or object())
    return calls


@pytest.fixture
def mart_database(tmp_path: Path) -> Path:
    path = tmp_path / "reporting.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute("CREATE SCHEMA mart")
    conn.execute(
        """CREATE TABLE mart.sales_orders_day (
               date DATE, warehouse VARCHAR, category VARCHAR, orders BIGINT, revenue DOUBLE
           )"""
    )
    conn.execute(
        """INSERT INTO mart.sales_orders_day VALUES
           ('2026-01-01', 'Prague_1', 'Fresh', 10, 120.5),
           ('2026-01-02', 'Prague_1', 'Fresh', 15, 180.0),
           ('2026-01-01', 'Brno_1', 'Ambient', 8, 90.0)"""
    )
    conn.close()
    return path


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_missing_database_is_reported_without_creation(tmp_path: Path, authenticated) -> None:
    path = tmp_path / "missing.duckdb"
    info = ReportingService(path).warehouse_info()
    assert info.exists is False
    assert info.ready_mart_count == 0
    assert not path.exists()
    assert authenticated == ["admin"]


def test_data_query_on_missing_database_is_a_safe_reporting_error(tmp_path: Path) -> None:
    path = tmp_path / "missing.duckdb"
    with pytest.raises(ReportingError, match="read-only"):
        ReportingService(path).row_count("mart.sales_orders_day")
    assert not path.exists()


def test_schema_introspection_and_missing_marts(mart_database: Path, authenticated) -> None:
    info = ReportingService(mart_database).warehouse_info()
    assert info.exists is True
    assert info.ready_mart_count == 1
    mart = next(item for item in info.marts if item.name == "mart.sales_orders_day")
    assert mart.temporal_columns == ("date",)
    assert mart.numeric_columns == ("orders", "revenue")
    assert authenticated == ["admin"]


def test_filter_pagination_aggregation_and_file_immutability(mart_database: Path, authenticated) -> None:
    before = digest(mart_database)
    service = ReportingService(mart_database)
    assert service.distinct_values("mart.sales_orders_day", "warehouse") == ("Brno_1", "Prague_1")
    assert service.date_bounds("mart.sales_orders_day", "date") == (
        date(2026, 1, 1),
        date(2026, 1, 2),
    )
    assert service.row_count("mart.sales_orders_day", filters={"warehouse": "Prague_1"}) == 2
    page = service.fetch_page(
        "mart.sales_orders_day", columns=("date", "orders"),
        filters={"warehouse": "Prague_1"}, limit=1, offset=1,
    )
    assert page.columns == ("date", "orders") and len(page.rows) == 1
    series = service.aggregate_series(
        "mart.sales_orders_day", date_column="date", metric_column="orders",
        filters={"warehouse": "Prague_1"},
    )
    assert [row[1] for row in series.rows] == [10, 15]
    assert digest(mart_database) == before
    assert len(authenticated) == 5


@pytest.mark.parametrize(
    "operation",
    [
        lambda service: service.mart_info("main.secret"),
        lambda service: service.fetch_page("mart.sales_orders_day", columns=("orders; DROP TABLE x",)),
        lambda service: service.fetch_page("mart.sales_orders_day", limit=501),
        lambda service: service.aggregate_series(
            "mart.sales_orders_day", date_column="warehouse", metric_column="orders"
        ),
        lambda service: service.fetch_page(
            "mart.sales_orders_day", filters={"warehouse": ("A", "Z")}
        ),
    ],
)
def test_unsafe_queries_are_rejected(mart_database: Path, operation) -> None:
    with pytest.raises(UnsafeReportingQuery):
        operation(ReportingService(mart_database))


def test_missing_allowlisted_mart_never_falls_back_to_raw(mart_database: Path) -> None:
    service = ReportingService(mart_database)
    assert service.mart_info("mart.exec_kpi_month").exists is False
    with pytest.raises(ReportingError, match="not available"):
        service.fetch_page("mart.exec_kpi_month")
