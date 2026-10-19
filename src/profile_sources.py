"""Profile six historical CSVs without opening project databases or changing sources.

Run from the project root: python -m src.profile_sources. Only summary JSON and
DuckDB temporary spill files are written under the ignored report directory.
"""

import argparse
import codecs
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "orders": ("data/raw/orders/train.csv", ["warehouse", "date"]),
    "orders_calendar": ("data/raw/orders/train_calendar.csv", ["warehouse", "date"]),
    "sales": ("data/raw/sales/sales_train.csv", ["unique_id", "date"]),
    "inventory": ("data/raw/sales/inventory.csv", ["unique_id"]),
    "sales_calendar": ("data/raw/sales/calendar.csv", ["warehouse", "date"]),
    "weights": ("data/raw/sales/test_weights.csv", ["unique_id"]),
}
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "exports" / "source_profiling"


def json_safe(value: Any) -> Any:
    """Represent undefined correlation/nonfinite aggregates as JSON null."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def ident(name: str) -> str:
    """Quote a SQL identifier, including names supplied by a CSV header."""
    return '"' + name.replace('"', '""') + '"'


def sha256(path: Path) -> str:
    """Hash bytes using bounded memory; never open a source for writing."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utf8_check(path: Path) -> dict[str, Any]:
    """Validate the complete file as UTF-8, without guessing alternative encodings."""
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    with path.open("rb") as stream:
        bom = stream.read(3) == codecs.BOM_UTF8
        stream.seek(0)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
    return {"encoding": "UTF-8 (compatible; not proof of original encoding)", "bom": bom}


def rows(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    """Return small aggregate result sets as dictionaries."""
    result = conn.execute(sql)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def key_profile(conn: duckdb.DuckDBPyConnection, table: str, keys: list[str]) -> dict[str, Any]:
    """Distinguish duplicate key groups, excess rows, full rows and null keys."""
    t = ident(table)
    k = ", ".join(map(ident, keys))
    missing = " OR ".join(f"{ident(key)} IS NULL OR trim(CAST({ident(key)} AS VARCHAR))=''" for key in keys)
    stats = rows(conn, f"SELECT count(*) distinct_keys, count(*) FILTER (WHERE n>1) duplicate_key_groups, "
                 f"coalesce(sum(n-1),0) duplicate_key_excess_rows FROM (SELECT {k}, count(*) n FROM {t} GROUP BY {k})")[0]
    stats["null_or_blank_key_rows"] = conn.execute(f"SELECT count(*) FROM {t} WHERE {missing}").fetchone()[0]
    stats["keys"] = keys
    stats["duplicate_key_examples"] = rows(conn, f"SELECT {k}, count(*) n FROM {t} GROUP BY {k} HAVING count(*)>1 ORDER BY n DESC, {k} LIMIT 5")
    stats["full_row_duplicate_excess"] = conn.execute(
        f"SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM {t} GROUP BY "
        + ", ".join(ident(c[0]) for c in conn.execute(f"DESCRIBE {t}").fetchall()) + ")").fetchone()[0]
    return stats


def profile_csv(conn: duckdb.DuckDBPyConnection, path: Path, table: str, keys: list[str]) -> dict[str, Any]:
    """Load one source only into a temporary in-memory table and profile all columns.

    Whole-file type inference and strict parsing: malformed records fail visibly.
    Nullability is observed, not a future business-schema constraint.
    """
    before = sha256(path)
    encoding = utf8_check(path)
    result = conn.execute("SELECT * FROM sniff_csv(?, sample_size=20480)", [str(path)])
    sniff = dict(zip([column[0] for column in result.description], result.fetchone()))
    # This materialization is ephemeral in :memory:, never a source/warehouse table.
    conn.execute(f"CREATE TEMP TABLE {ident(table)} AS SELECT * FROM read_csv(?, "
                 "header=true, sample_size=-1, strict_mode=true, ignore_errors=false, encoding='utf-8')", [str(path)])
    schema = conn.execute(f"DESCRIBE {ident(table)}").fetchall()
    n = conn.execute(f"SELECT count(*) FROM {ident(table)}").fetchone()[0]
    profiles = []
    for name, inferred, *_ in schema:
        col, t = ident(name), ident(table)
        numeric = inferred.startswith(("BIGINT", "INTEGER", "SMALLINT", "TINYINT", "HUGEINT", "DOUBLE", "FLOAT", "DECIMAL", "UBIGINT"))
        stat = rows(conn, f"SELECT count(*) FILTER (WHERE {col} IS NULL) null_count, "
                    f"count(DISTINCT {col}) distinct_count, min({col}) minimum, max({col}) maximum FROM {t}")[0]
        stat.update(column=name, inferred_type=inferred, proposed_duckdb_type=inferred,
                    proposed_sqlite_type="INTEGER" if "INT" in inferred else "REAL" if numeric else "TEXT",
                    null_percentage=100 * stat["null_count"] / n if n else None,
                    observed_nullable=stat["null_count"] > 0)
        stat["examples"] = [r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM {t} WHERE {col} IS NOT NULL ORDER BY {col} LIMIT 5").fetchall()]
        if numeric:
            stat.update(rows(conn, f"SELECT count(*) FILTER (WHERE {col}<0) negative_count, "
                        f"count(*) FILTER (WHERE isfinite({col}) AND {col}<>trunc({col})) fractional_count, "
                        f"count(*) FILTER (WHERE NOT isfinite({col})) nonfinite_count FROM {t}")[0])
            if name == "availability" or name.startswith("type_") and name.endswith("_discount"):
                stat["outside_0_1"] = conn.execute(f"SELECT count(*) FROM {t} WHERE {col}<0 OR {col}>1").fetchone()[0]
            if name in {"orders", "sales", "total_orders", "sell_price_main", "weight"}:
                stat["zero_count"] = conn.execute(f"SELECT count(*) FROM {t} WHERE {col}=0").fetchone()[0]
        if inferred == "VARCHAR":
            stat.update(rows(conn, f"SELECT count(*) FILTER (WHERE trim({col})='') blank_count, "
                        f"count(*) FILTER (WHERE {col}<>trim({col})) whitespace_count, "
                        f"count(DISTINCT lower(trim({col}))) normalized_distinct FROM {t}")[0])
            if stat["distinct_count"] <= 100:
                stat["categories"] = rows(conn, f"SELECT {col} AS value, count(*) n FROM {t} GROUP BY {col} ORDER BY {col}")
        if name == "date":
            stat["invalid_date_count"] = conn.execute(f"SELECT count(*) FROM {t} WHERE {col} IS NOT NULL AND try_cast({col} AS DATE) IS NULL").fetchone()[0]
        profiles.append(stat)
    names = [c[0] for c in schema]
    coverage = []
    if "warehouse" in names:
        date_stats = ", min(try_cast(date AS DATE)) min_date, max(try_cast(date AS DATE)) max_date" if "date" in names else ""
        coverage = rows(conn, f"SELECT warehouse, count(*) n{date_stats} FROM {ident(table)} GROUP BY warehouse ORDER BY warehouse")
    result = dict(path=str(path), exists=True, size_bytes=path.stat().st_size, sha256=before,
                  rows=n, column_count=len(schema), columns=profiles, warehouse_coverage=coverage,
                  key=key_profile(conn, table, keys), read_issues=[], **encoding,
                  dialect={k: str(sniff[k]) for k in ["Delimiter", "Quote", "Escape", "NewLineDelimiter", "HasHeader", "DateFormat"]})
    result["sha256_after"] = sha256(path)
    if before != result["sha256_after"]:
        raise RuntimeError(f"Source changed during profiling: {path}")
    return result


def join_profile(conn: duckdb.DuckDBPyConnection, left: str, right: str, keys: list[str]) -> dict[str, Any]:
    """Count LEFT/INNER JOIN rows exactly via key multiplicities; no physical join table."""
    k = ",".join(map(ident, keys))
    sql = f"""WITH l AS (SELECT {k}, count(*) nl FROM {ident(left)} GROUP BY {k}),
        r AS (SELECT {k}, count(*) nr FROM {ident(right)} GROUP BY {k})
        SELECT coalesce(sum(nl*coalesce(nr,1)),0) left_join_rows,
        coalesce(sum(nl*coalesce(nr,0)),0) inner_join_rows,
        coalesce(sum(nl) FILTER (WHERE nr IS NULL),0) unmatched_left_rows,
        count(*) FILTER (WHERE nr IS NULL) unmatched_left_keys,
        coalesce(max(nl),0) max_left_multiplicity, coalesce(max(nr),0) max_right_multiplicity
        FROM l LEFT JOIN r USING ({k})"""
    result = rows(conn, sql)[0]
    result.update(left=left, right=right, keys=keys)
    reverse = rows(conn, f"WITH l AS (SELECT {k},count(*) nl FROM {ident(left)} GROUP BY {k}), "
                   f"r AS (SELECT {k},count(*) nr FROM {ident(right)} GROUP BY {k}) "
                   f"SELECT count(*) unmatched_right_keys, coalesce(sum(nr),0) unmatched_right_rows "
                   f"FROM r LEFT JOIN l USING ({k}) WHERE nl IS NULL")[0]
    result.update(reverse)
    return result


def gap_analysis(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Compare actual orders with warehouse-day medians, never sum repeated totals."""
    cte = """WITH s AS (SELECT warehouse,date,count(*) sku_rows,count(DISTINCT total_orders) n_values,
        median(total_orders) order_index,min(total_orders) min_total,max(total_orders) max_total
        FROM sales GROUP BY warehouse,date) """
    distribution = rows(conn, cte + "SELECT warehouse,count(*) AS days, sum(sku_rows) sku_rows, "
                        "count(*) FILTER(WHERE n_values>1) multi_total_days, max(n_values) max_distinct_totals, "
                        "min(date) min_date,max(date) max_date FROM s GROUP BY warehouse ORDER BY warehouse")
    comparison = rows(conn, cte + "SELECT o.warehouse,count(*) overlap_days,min(o.date) min_date,max(o.date) max_date, "
                      "corr(o.orders,s.order_index) correlation,median(abs(o.orders-s.order_index)) median_absolute_gap, "
                      "median(abs(o.orders-s.order_index)/nullif(abs(o.orders),0))*100 median_relative_gap_pct, "
                      "count(*) FILTER(WHERE o.orders=0) zero_order_denominators "
                      "FROM orders o JOIN s USING(warehouse,date) GROUP BY o.warehouse ORDER BY o.warehouse")
    examples = rows(conn, cte + "SELECT * FROM s WHERE n_values>1 ORDER BY warehouse,date LIMIT 7")
    counts = rows(conn, cte + "SELECT count(*) overlap_days FROM orders JOIN s USING(warehouse,date)")[0]
    counts["distribution"] = distribution
    counts["comparison"] = comparison
    counts["examples"] = examples
    counts["quality_rates"] = rows(conn, "SELECT count(*) n, count(*) FILTER(WHERE availability<1) availability_below_one, "
                                      "count(*) FILTER(WHERE greatest(type_0_discount,type_1_discount,type_2_discount,type_3_discount,"
                                      "type_4_discount,type_5_discount,type_6_discount)>0) discounted_rows FROM sales")[0]
    counts["id_consistency"] = rows(conn, "SELECT count(*) FILTER(WHERE s.warehouse IS DISTINCT FROM i.warehouse) warehouse_mismatch_rows "
                                   "FROM sales s JOIN inventory i USING(unique_id)")[0]
    counts["inventory_grain"] = rows(conn, "SELECT count(DISTINCT unique_id) sku_ids,count(DISTINCT product_unique_id) product_ids "
                                     "FROM inventory")[0]
    return counts


def reconcile_calendars(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Compare shared calendar fields null-safely on common warehouse/date keys."""
    left = dict((r[0], r[1]) for r in conn.execute("DESCRIBE orders_calendar").fetchall())
    right = dict((r[0], r[1]) for r in conn.execute("DESCRIBE sales_calendar").fetchall())
    common = sorted(set(left) & set(right) - {"warehouse", "date"})
    result: dict[str, Any] = {"common_columns": common, "orders_only": sorted(set(left)-set(right)),
                              "sales_only": sorted(set(right)-set(left)), "types": {c:[left[c],right[c]] for c in common}}
    result["overlap_rows"] = conn.execute("SELECT count(*) FROM orders_calendar JOIN sales_calendar USING(warehouse,date)").fetchone()[0]
    result["conflicts"] = {}
    for name in common:
        q = ident(name)
        predicate = f"a.{q} IS DISTINCT FROM b.{q}"
        result["conflicts"][name] = {
            "count": conn.execute(f"SELECT count(*) FROM orders_calendar a JOIN sales_calendar b USING(warehouse,date) WHERE {predicate}").fetchone()[0],
            "examples": rows(conn, f"SELECT a.warehouse,a.date,a.{q} orders_value,b.{q} sales_value "
                             f"FROM orders_calendar a JOIN sales_calendar b USING(warehouse,date) WHERE {predicate} ORDER BY warehouse,date LIMIT 5")}
    return result


def run_profile(root: Path, report_dir: Path) -> dict[str, Any]:
    """Profile the fixed six-file allowlist and write only a bounded summary JSON."""
    root, report_dir = root.resolve(), report_dir.resolve()
    # Outputs must remain in ignored exports, even when a custom location is given.
    if not report_dir.is_relative_to(root / "data" / "exports"):
        raise ValueError("Report directory must be inside project data/exports")
    report_dir.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(":memory:")
    report: dict[str, Any] = {"generated_at": datetime.now(timezone.utc).isoformat(),
                              "duckdb_version": duckdb.__version__, "sources": {}, "errors": [],
                              "options": {"sample_size": -1, "header": True, "strict_mode": True,
                                          "ignore_errors": False, "memory_limit": "1GB", "threads": 2}}
    try:
        conn.execute("SET threads=2")
        conn.execute("SET memory_limit='1GB'")
        conn.execute("SET temp_directory=?", [str(report_dir / "spill")])
        for name, (relative, keys) in SOURCES.items():
            print(f"Profiling {relative}", flush=True)
            path = root / relative
            try:
                profile = profile_csv(conn, path, name, keys)
                profile["path"] = relative
                report["sources"][name] = profile
            except (OSError, UnicodeError, duckdb.Error, RuntimeError) as exc:
                report["sources"][name] = {"path": relative, "exists": path.exists(), "read_issues": [str(exc)]}
                report["errors"].append(f"{name}: {exc}")
        if not report["errors"]:
            relations = [("sales", "inventory", ["unique_id"]), ("sales", "weights", ["unique_id"]),
                         ("sales", "sales_calendar", ["warehouse", "date"]),
                         ("orders", "orders_calendar", ["warehouse", "date"]),
                         ("orders", "sales", ["warehouse", "date"]),
                         ("orders_calendar", "sales_calendar", ["warehouse", "date"])]
            report["joins"] = [join_profile(conn, *args) for args in relations]
            print("Orders/Sales gap and calendar reconciliation", flush=True)
            report["orders_sales"] = gap_analysis(conn)
            report["calendars"] = reconcile_calendars(conn)
        for name, source in report["sources"].items():
            if "sha256" in source and sha256(root / source["path"]) != source["sha256"]:
                report["errors"].append(f"{name}: source hash changed before completion")
        target = report_dir / "profile.json"
        target.write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding="utf-8")
        print(f"{'FAILED' if report['errors'] else 'SUCCESS'}: {target}", flush=True)
        return report
    finally:
        conn.close()


def main() -> int:
    """Exit nonzero when a source is unavailable/unreadable, without silently skipping it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    directory = args.report_dir if args.report_dir.is_absolute() else PROJECT_ROOT / args.report_dir
    try:
        result = run_profile(PROJECT_ROOT, directory)
    except (OSError, ValueError, duckdb.Error) as exc:
        print(f"FAILED: {exc}")
        return 1
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
