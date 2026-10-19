"""Profiling validation uses only small CSV fixtures in pytest temporary paths."""

import csv
from pathlib import Path

import duckdb
import pytest

from src.profile_sources import (SOURCES, gap_analysis, join_profile, key_profile,
                                 profile_csv, reconcile_calendars, run_profile, sha256)


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


def write_csv(path, header, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(records)


def test_column_stats_ranges_and_hash(conn, tmp_path):
    path = tmp_path / "sample.csv"
    write_csv(path, ["unique_id", "availability", "sales", "label"],
              [[1, 1, 2.5, " A "], [2, -0.2, -1, "a"], [3, 1.2, "", ""]])
    before = sha256(path)
    result = profile_csv(conn, path, "sample", ["unique_id"])
    cols = {c["column"]: c for c in result["columns"]}
    assert result["rows"] == 3
    assert cols["availability"]["outside_0_1"] == 2
    assert cols["sales"]["negative_count"] == 1
    assert cols["sales"]["null_count"] == 1
    assert cols["sales"]["fractional_count"] == 1
    assert cols["label"]["whitespace_count"] == 1
    assert cols["label"]["normalized_distinct"] == 1
    assert result["sha256"] == result["sha256_after"] == before == sha256(path)


def test_full_row_and_key_duplicates_are_different(conn):
    conn.execute("CREATE TEMP TABLE fixture (key INTEGER, value VARCHAR)")
    conn.execute("INSERT INTO fixture VALUES (1,'a'),(1,'a'),(1,'b'),(NULL,'c')")
    result = key_profile(conn, "fixture", ["key"])
    assert result["duplicate_key_groups"] == 1
    assert result["duplicate_key_excess_rows"] == 2
    assert result["full_row_duplicate_excess"] == 1
    assert result["null_or_blank_key_rows"] == 1
    assert result["distinct_keys"] == 2  # Includes the null key group; reported explicitly.


def test_join_multiplicities_unmatched_and_null(conn):
    conn.execute("CREATE TEMP TABLE l (key INTEGER)")
    conn.execute("CREATE TEMP TABLE r (key INTEGER)")
    conn.execute("INSERT INTO l VALUES (1),(1),(2),(NULL)")
    conn.execute("INSERT INTO r VALUES (1),(1),(3),(NULL)")
    result = join_profile(conn, "l", "r", ["key"])
    assert result["left_join_rows"] == 6
    assert result["inner_join_rows"] == 4
    assert result["unmatched_left_rows"] == 2
    assert result["unmatched_right_rows"] == 2
    assert result["max_right_multiplicity"] == 2


def test_date_parse_failures_are_visible(conn, tmp_path):
    path = tmp_path / "dates.csv"
    write_csv(path, ["warehouse", "date"], [["A", "2024-01-01"], ["A", "not-a-date"]])
    result = profile_csv(conn, path, "dates", ["warehouse", "date"])
    date = next(c for c in result["columns"] if c["column"] == "date")
    assert date["invalid_date_count"] == 1
    assert date["inferred_type"] == "VARCHAR"


def test_calendar_null_safe_conflict(conn):
    conn.execute("CREATE TEMP TABLE orders_calendar (warehouse VARCHAR,date DATE,holiday INTEGER,warehouse_limited INTEGER)")
    conn.execute("CREATE TEMP TABLE sales_calendar (warehouse VARCHAR,date DATE,holiday INTEGER)")
    conn.execute("INSERT INTO orders_calendar VALUES ('A','2024-01-01',NULL,1),('A','2024-01-02',1,0)")
    conn.execute("INSERT INTO sales_calendar VALUES ('A','2024-01-01',0),('A','2024-01-02',1)")
    result = reconcile_calendars(conn)
    assert result["orders_only"] == ["warehouse_limited"]
    assert result["overlap_rows"] == 2
    assert result["conflicts"]["holiday"]["count"] == 1


def populate(root):
    sources = {
        "orders": (["warehouse", "date", "orders"], [["A", "2024-01-01", 10]]),
        "orders_calendar": (["warehouse", "date", "holiday"], [["A", "2024-01-01", 0]]),
        "sales": (["unique_id", "date", "warehouse", "total_orders", "sales", "availability"]
                  + [f"type_{n}_discount" for n in range(7)],
                  [[1, "2024-01-01", "A", 8, 1, 0.5] + [0]*7,
                   [2, "2024-01-01", "A", 12, 2, 1] + [0.1]*7]),
        "inventory": (["unique_id", "warehouse", "product_unique_id"], [[1, "A", 99], [2, "A", 100]]),
        "sales_calendar": (["warehouse", "date", "holiday"], [["A", "2024-01-01", 0]]),
        "weights": (["unique_id", "weight"], [[1, 0.5], [2, 1]]),
    }
    for name, (header, records) in sources.items():
        write_csv(root / SOURCES[name][0], header, records)


def test_end_to_end_six_files_gap_median_and_summary(tmp_path):
    populate(tmp_path)
    before = {p:sha256(p) for p in tmp_path.rglob('*.csv')}
    result = run_profile(tmp_path, tmp_path / "data/exports/reports")
    assert result["errors"] == []
    assert len(result["sources"]) == 6
    assert result["orders_sales"]["overlap_days"] == 1
    assert result["orders_sales"]["comparison"][0]["median_absolute_gap"] == 0
    assert result["orders_sales"]["distribution"][0]["multi_total_days"] == 1
    assert result["orders_sales"]["quality_rates"]["discounted_rows"] == 1
    assert (tmp_path / "data/exports/reports/profile.json").exists()
    assert {p:sha256(p) for p in before} == before
    assert not list(tmp_path.rglob('*.duckdb'))


def test_missing_sources_reported_not_skipped(tmp_path):
    result = run_profile(tmp_path, tmp_path / "data/exports/reports")
    assert len(result["errors"]) == 6
    assert all(not s["exists"] for s in result["sources"].values())
    assert "joins" not in result


def test_report_directory_cannot_overwrite_sources(tmp_path):
    with pytest.raises(ValueError, match="data/exports"):
        run_profile(tmp_path, tmp_path / "data/raw")


def test_invalid_utf8_not_silently_replaced(conn, tmp_path):
    path=tmp_path / 'invalid.csv'
    path.write_bytes(b'key,label\n1,\xff\n')
    with pytest.raises(UnicodeDecodeError):
        profile_csv(conn, path, 'invalid', ['key'])


def test_quoted_identifier_supported(conn, tmp_path):
    path=tmp_path / 'quoted.csv'
    write_csv(path, ['key"id', 'label'], [[1, 'hello, world']])
    result=profile_csv(conn,path,'safe',['key"id'])
    assert result['columns'][1]['examples'] == ['hello, world']
