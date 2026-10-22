"""Bộ kiểm định chất lượng (M2 mục 9): 21 kiểm tra nền V4 + kiểm tra bổ sung STG/Core/Mart.

Mỗi kiểm tra là 1 câu SQL trả về 1 số `observed`:
  * ERROR: observed phải = 0 (hoặc ≤ ngưỡng) – sai → FAIL → refresh rollback, mô hình không được chạy.
  * WARN : observed > 0 → WARN (không chặn) – hiện trên trang "Vận hành hệ thống" kèm số quan sát.
Kết quả ghi vào meta.quality_report.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from src.config.settings import Settings
from src.db.pipeline_metadata import now_utc


@dataclass(frozen=True)
class Check:
    check_id: str
    table: str
    severity: str          # ERROR / WARN
    sql: str
    description: str
    threshold: float = 0.0


@dataclass(frozen=True)
class CheckResult:
    check: Check
    observed: float
    status: str            # PASS / WARN / FAIL


def _dup(table: str, keys: list[str]) -> str:
    cols = ", ".join(f'"{k}"' for k in keys)
    return f"SELECT count(*) FROM (SELECT {cols} FROM {table} GROUP BY {cols} HAVING count(*) > 1)"


def build_checks(settings: Settings, stg_keys: dict[str, list[str]], run_id: str) -> list[Check]:
    wh = ", ".join(f"'{w}'" for w in settings.warehouses)
    n_wh = len(settings.warehouses)
    tf, ao, fe = settings.train_from.isoformat(), settings.as_of.isoformat(), settings.forecast_end.isoformat()
    checks: list[Check] = []
    # ---- B01–B14: không trùng khoá ở 14 bảng STG ----
    for i, (table, keys) in enumerate(sorted(stg_keys.items()), start=1):
        checks.append(Check(f"B{i:02d}", table, "ERROR", _dup(table, keys), f"Không trùng khoá {keys}"))
    # ---- B15–B21: 7 kiểm tra chuyên biệt V4 ----
    checks += [
        Check("B15", "stg.sku_sales_daily", "ERROR",
              "SELECT count(*) FROM stg.sku_sales_daily s ANTI JOIN stg.product_master p USING (unique_id)",
              "SKU có bán nhưng không có trong danh mục"),
        Check("B16", "stg.prices", "ERROR", "SELECT count(*) FROM stg.prices WHERE sell_price_main <= 0",
              "Giá bán ≤ 0"),
        Check("B17", "stg.orders_daily", "ERROR", "SELECT count(*) FROM stg.orders_daily WHERE orders < 0",
              "Số đơn âm"),
        Check("B18", "stg.sku_sales_daily", "WARN",
              f"""SELECT count(*) FROM (SELECT DISTINCT warehouse, date FROM stg.sku_sales_daily
                  WHERE date BETWEEN DATE '{tf}' AND DATE '{ao}') s ANTI JOIN stg.calendar c USING (warehouse, date)""",
              "Ngày có doanh số nhưng thiếu lịch"),
        Check("B19", "stg.orders_daily", "WARN",
              f"""SELECT {n_wh} - count(*) FROM stg.orders_daily
                  WHERE date = (SELECT max(date) FROM stg.orders_daily WHERE date <= DATE '{ao}')
                    AND warehouse IN ({wh})""",
              "Ngày mới nhất (≤ as_of): số kho chưa có số đơn"),
        Check("B20", "stg.sku_sales_daily", "WARN",
              f"""SELECT count(*) FROM (SELECT unique_id, date FROM stg.sku_sales_daily
                  WHERE date BETWEEN DATE '{tf}' AND DATE '{ao}') s ANTI JOIN stg.availability a USING (unique_id, date)""",
              "Doanh số SKU thiếu availability"),
        Check("B21", "stg.calendar", "ERROR",
              f"""SELECT count(*) FROM (SELECT w.warehouse, max(c.date) AS d
                  FROM (SELECT UNNEST([{wh}]) AS warehouse) w LEFT JOIN stg.calendar c USING (warehouse)
                  GROUP BY w.warehouse) WHERE d IS NULL OR d < DATE '{fe}'""",
              f"Lịch chưa phủ tới {fe} cho mọi kho (BT1, BT2 cần lịch kỳ dự báo)"),
    ]
    # ---- S-01…S-04: lô dữ liệu & STG ----
    s01 = " + ".join(
        f"(SELECT count(*) FROM {t} s JOIN meta.v_batch_current b ON b.batch_id = s._batch_id "
        "WHERE b.status <> 'COMPLETED')" for t in sorted(stg_keys))
    checks += [
        Check("S-01", "stg.*", "ERROR", f"SELECT {s01}", "Không lọt dòng của lô UNDONE/FAILED vào STG"),
        Check("S-02", "meta.stg_rejects", "WARN",
              f"SELECT count(*) FROM meta.stg_rejects WHERE run_id = '{run_id}' AND reason <> 'DUP_IN_BATCH'",
              "Bản lỗi KEY_NULL / NULL_REQUIRED bị loại khỏi STG"),
        Check("S-03", "meta.stg_rejects", "ERROR",
              f"SELECT count(*) FROM meta.stg_rejects WHERE run_id = '{run_id}' AND reason = 'DUP_IN_BATCH'",
              "Trùng khoá trong cùng một lô"),
    ]
    # ---- Core: fct_warehouse_day ----
    checks += [
        Check("C-WD-01", "core.fct_warehouse_day", "ERROR", _dup("core.fct_warehouse_day", ["warehouse", "date"]),
              "Không trùng khoá"),
        Check("C-WD-02", "core.fct_warehouse_day", "ERROR",
              f"SELECT {n_wh} - count(DISTINCT warehouse) FROM core.fct_warehouse_day", f"Đủ {n_wh} kho"),
        Check("C-WD-03", "core.fct_warehouse_day", "ERROR",
              "SELECT count(*) FROM core.fct_warehouse_day WHERE orders < 0", "Số đơn không âm"),
        Check("C-WD-04", "core.fct_warehouse_day", "ERROR",
              f"""SELECT count(*) FROM (SELECT warehouse, max(date) d FROM core.fct_warehouse_day
                  WHERE NOT calendar_missing GROUP BY 1) WHERE d < DATE '{fe}'""",
              f"Lịch phủ tới {fe} cho mọi kho"),
        Check("C-WD-05", "core.fct_warehouse_day", "WARN",
              "SELECT count(*) FROM core.fct_warehouse_day WHERE has_orders AND order_index IS NULL",
              "Ngày có đơn nhưng thiếu order_index"),
        Check("C-WD-06", "core.fct_warehouse_day", "WARN",
              "SELECT count(*) FROM core.fct_warehouse_day WHERE has_orders AND weather_missing",
              "Thời tiết NULL (kỳ vọng ≈ 270 – giữ NULL theo D04)"),
        Check("C-WD-07", "core.fct_warehouse_day", "ERROR",
              f"""SELECT abs(COALESCE((SELECT sum(orders) FROM core.fct_warehouse_day), 0)
                  - COALESCE((SELECT sum(orders) FROM stg.orders_daily
                              WHERE date BETWEEN DATE '{tf}' AND DATE '{ao}' AND warehouse IN ({wh})), 0))""",
              "Tổng orders khớp STG (không nhân dòng)", 0.001),
    ]
    # ---- Core: fct_sku_day ----
    checks += [
        Check("C-SD-01", "core.fct_sku_day", "ERROR", _dup("core.fct_sku_day", ["unique_id", "date"]), "Không trùng khoá"),
        Check("C-SD-02", "core.fct_sku_day", "ERROR",
              f"""SELECT abs((SELECT count(*) FROM core.fct_sku_day) - (SELECT count(*) FROM stg.sku_sales_daily
                  WHERE date BETWEEN DATE '{tf}' AND DATE '{ao}' AND warehouse IN ({wh})))""",
              "Số dòng = stg.sku_sales_daily trong phạm vi (không nhân dòng)"),
        Check("C-SD-03", "core.fct_sku_day", "ERROR",
              "SELECT count(*) FROM core.fct_sku_day WHERE L1_category_name_en IS NULL", "Mọi SKU có trong product_master"),
        Check("C-SD-03b", "core.fct_sku_day", "ERROR",
              "SELECT count(*) FROM core.fct_sku_day f JOIN stg.product_master m USING (unique_id) WHERE f.warehouse <> m.warehouse",
              "Kho của dòng Sales khớp kho ở product_master"),
        Check("C-SD-04", "core.fct_sku_day", "ERROR",
              "SELECT count(*) FROM core.fct_sku_day WHERE sell_price_main <= 0", "Giá bán > 0"),
        Check("C-SD-04b", "core.fct_sku_day", "WARN",
              "SELECT count(*) FROM core.fct_sku_day WHERE price_missing", "Thiếu giá"),
        Check("C-SD-05", "core.fct_sku_day", "WARN",
              "SELECT count(*) FROM core.fct_sku_day WHERE sales_missing", "NULL sales (giữ NULL theo D04)"),
        Check("C-SD-06", "core.fct_sku_day", "WARN",
              "SELECT count(*) FROM core.fct_sku_day WHERE discount_anomaly",
              "Giảm giá bất thường (âm hoặc > 1) – max_discount đã kẹp [0,1]"),
        Check("C-SD-07", "core.fct_sku_day", "ERROR",
              "SELECT count(*) FROM core.fct_sku_day WHERE final_price > sell_price_main + 1e-9",
              "Giá sau giảm không lớn hơn giá gốc"),
        Check("C-SD-08", "core.fct_sku_day", "WARN",
              "SELECT count(*) FROM core.fct_sku_day WHERE availability < 0 OR availability > 1",
              "availability ngoài [0, 1]"),
        Check("C-SD-09", "core.fct_sku_day", "WARN",
              "SELECT count(*) FROM core.fct_sku_day WHERE availability IS NULL", "Thiếu availability"),
    ]
    # ---- Core: dimension, tham số ----
    checks += [
        Check("C-DP-01", "core.dim_product", "ERROR",
              "SELECT count(*) - count(DISTINCT unique_id) FROM core.dim_product", "Không trùng unique_id"),
        Check("C-DP-02", "core.dim_product", "WARN",
              f"SELECT count(*) FROM core.dim_product WHERE warehouse NOT IN ({wh})", "Kho ngoài phạm vi settings"),
        Check("C-DP-03", "core.dim_product", "WARN",
              "SELECT count(*) FROM core.dim_product WHERE L1_category_name_en IS NULL", "Thiếu L1"),
        Check("C-DP-04", "core.dim_product", "WARN",
              "SELECT count(*) FROM core.dim_product WHERE n_sale_days > 0 AND NOT has_weight",
              "SKU có bán nhưng thiếu trọng số chấm điểm"),
        Check("C-DW-01", "core.dim_warehouse", "ERROR",
              f"SELECT abs({n_wh} - count(DISTINCT warehouse)) + (count(*) - count(DISTINCT warehouse)) FROM core.dim_warehouse",
              f"Đúng {n_wh} kho, không trùng"),
        Check("C-DW-02", "core.dim_warehouse", "ERROR",
              "SELECT count(*) FROM core.dim_warehouse WHERE n_order_days IS NULL OR NOT has_workforce_params",
              "Kho có đơn và có tham số nhân sự"),
        Check("C-PC-01", "core.params_cost", "ERROR",
              "SELECT (count(*) = 0)::INT + (count(*) - count(DISTINCT L1_category_name_en)) FROM core.params_cost",
              "Có tham số chi phí, không trùng ngành"),
        Check("C-PC-02", "core.params_cost", "ERROR",
              """SELECT count(*) FROM core.params_cost WHERE NOT (cost_ratio BETWEEN 0 AND 1
                 AND shelf_life_days > 0 AND waste_handling_cost_ratio >= 0)""", "Miền giá trị tham số chi phí"),
        Check("C-PW-01", "core.params_workforce", "ERROR",
              f"""SELECT count(*) FROM (SELECT UNNEST([{wh}]) AS warehouse) w
                  ANTI JOIN core.params_workforce USING (warehouse)""",
              f"Đủ tham số nhân sự cho {n_wh} kho"),
        Check("C-PW-02", "core.params_workforce", "ERROR",
              """SELECT count(*) FROM core.params_workforce WHERE NOT (hourly_wage_eur > 0 AND items_per_order > 0
                 AND picks_per_hour > 0 AND shift_hours > 0 AND morning_shift_ratio BETWEEN 0 AND 1
                 AND overtime_cap_ratio BETWEEN 0 AND 1 AND overtime_multiplier >= 1
                 AND orders_per_driver_shift > 0)""", "Miền giá trị tham số nhân sự"),
    ]
    # ---- Mart ----
    checks += [
        Check("M-SO-01", "mart.sales_orders_day", "ERROR", _dup("mart.sales_orders_day", ["warehouse", "date"]), "Không trùng khoá"),
        Check("M-SO-02", "mart.sales_orders_day", "ERROR",
              """SELECT abs(COALESCE((SELECT sum(orders) FROM mart.sales_orders_day), 0)
                 - COALESCE((SELECT sum(orders) FROM core.fct_warehouse_day WHERE NOT is_forecast_period), 0))""",
              "Tổng đơn khớp Core", 0.001),
        Check("M-OP-01", "mart.ops_warehouse_day", "ERROR", _dup("mart.ops_warehouse_day", ["warehouse", "date"]), "Không trùng khoá"),
        Check("M-OP-02", "mart.ops_warehouse_day", "ERROR",
              """SELECT (SELECT count(*) FROM core.fct_warehouse_day WHERE has_orders AND NOT is_forecast_period)
                 - (SELECT count(*) FROM mart.ops_warehouse_day)""", "Mọi kho có tham số (không mất dòng khi JOIN)"),
        Check("M-OP-03", "mart.ops_warehouse_day", "ERROR",
              "SELECT count(*) FROM mart.ops_warehouse_day WHERE LEAST(items_est, picking_hours_est, driver_shifts_est) < 0",
              "Ước lượng không âm"),
        Check("M-CS-01", "mart.category_sku_day", "ERROR",
              _dup("mart.category_sku_day", ["warehouse", "date", "L1_category_name_en"]), "Không trùng khoá"),
        Check("M-CS-02", "mart.category_sku_day", "ERROR",
              """SELECT abs(COALESCE((SELECT sum(revenue_eur) FROM mart.category_sku_day), 0)
                 - COALESCE((SELECT sum(revenue_eur) FROM core.fct_sku_day), 0))""",
              "Tổng doanh thu EUR khớp Core", 0.01),
        Check("M-CS-03", "mart.category_sku_day", "ERROR",
              "SELECT (SELECT sum(n_sku_rows) FROM mart.category_sku_day) - (SELECT count(*) FROM core.fct_sku_day)",
              "Tổng số dòng khớp Core"),
        Check("M-CS-04", "mart.category_sku_day", "WARN",
              "SELECT count(*) FROM mart.category_sku_day WHERE L1_category_name_en IS NULL", "Ngành NULL"),
        Check("M-PR-01", "mart.marketing_promo_day", "ERROR",
              _dup("mart.marketing_promo_day", ["warehouse", "date", "L1_category_name_en"]), "Không trùng khoá"),
        Check("M-PR-02", "mart.marketing_promo_day", "ERROR",
              "SELECT count(*) FROM mart.marketing_promo_day WHERE n_sku_promo > n_sku_rows", "Số SKU có KM không vượt số dòng"),
        Check("M-PR-03", "mart.marketing_promo_day", "ERROR",
              """SELECT (SELECT sum(n_discount_anomaly) FROM mart.marketing_promo_day)
                 - (SELECT count(*) FROM core.fct_sku_day WHERE discount_anomaly)""", "Tổng bất thường khớp C-SD-06"),
        Check("M-EX-01", "mart.exec_kpi_month", "ERROR", _dup("mart.exec_kpi_month", ["warehouse", "month"]), "Không trùng khoá"),
        Check("M-EX-02", "mart.exec_kpi_month", "ERROR",
              """SELECT abs(COALESCE((SELECT sum(total_orders) FROM mart.exec_kpi_month), 0)
                 - COALESCE((SELECT sum(orders) FROM mart.sales_orders_day), 0))""",
              "Tổng đơn tháng = tổng đơn ngày", 0.001),
    ]
    return checks


def run_checks(conn: duckdb.DuckDBPyConnection, checks: list[Check]) -> list[CheckResult]:
    results = []
    for check in checks:
        value = conn.execute(check.sql).fetchone()[0]
        observed = float(value or 0)
        if check.severity == "ERROR":
            status = "FAIL" if abs(observed) > check.threshold else "PASS"
        else:
            status = "WARN" if observed > check.threshold else "PASS"
        results.append(CheckResult(check, observed, status))
    return results


def stg_row_checks(stg_results) -> list[CheckResult]:
    """S-04: số dòng STG ≤ số dòng Landing của lô COMPLETED (tính sẵn từ kết quả build_stg)."""
    out = []
    for r in stg_results:
        c = Check(f"S-04:{r.table}", r.table, "ERROR", "", "Số dòng STG ≤ số dòng Landing của lô COMPLETED")
        excess = max(0, r.stg_rows - r.completed_rows)
        out.append(CheckResult(c, float(excess), "FAIL" if excess else "PASS"))
    return out


def write_report(conn: duckdb.DuckDBPyConnection, run_id: str, results: list[CheckResult]) -> None:
    at = now_utc()
    conn.execute("DELETE FROM meta.quality_report WHERE run_id = ?", [run_id])
    conn.executemany(
        "INSERT INTO meta.quality_report VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, r.check.check_id, r.check.table, r.check.severity, r.observed,
          f"{'=' if r.check.severity == 'ERROR' else '≤'} {r.check.threshold:g}", r.status, r.check.description, at)
         for r in results],
    )
