"""Lớp Mart: 5 mart nền (M2 mục 8, D05) + 7 mart kết quả mô hình (D05 đã duyệt 22/10/2026).

Quy ước để dashboard v3 tự hiển thị đúng (app/services/reporting.py):
  * mỗi mart có đúng 1 cột thời gian (date hoặc month) – hoặc không có cột thời gian (bảng tham số);
  * có cột `warehouse` (lọc kho) và/hoặc `L1_category_name_en` (lọc ngành);
  * cột số là chỉ số CỘNG ĐƯỢC (biểu đồ cộng theo ngày); tỷ lệ/trung bình để dạng chữ *_txt.
5 mart nền được ghi thành TABLE (M2 cho phép đổi VIEW → TABLE, giữ nguyên tên/cột) để trang mở nhanh.
"""

from __future__ import annotations

import duckdb

from src.db.pipeline_metadata import table_exists

BASE_MARTS = (
    "mart.sales_orders_day",
    "mart.ops_warehouse_day",
    "mart.category_sku_day",
    "mart.marketing_promo_day",
    "mart.exec_kpi_month",
)

# mart kết quả mô hình → các bảng pred.* cần có
MODEL_MARTS = {
    "mart.bt1_forecast_orders": ("pred.fc_orders",),
    "mart.bt2_staff_driver_plan": ("pred.staff_plan", "pred.driver_plan"),
    "mart.bt3_lost_sales_day": ("pred.lost_sales",),
    "mart.bt4_bt6_sku_plan_day": ("pred.fc_sku",),
    "mart.bt5_promo_effect": ("pred.promo_effect",),
    "mart.bt7_markdown_day": ("pred.markdown_plan",),
    "mart.bt8_growth_month": ("pred.growth_curves", "pred.growth_projection"),
}


def build_base_marts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    conn.execute("CREATE SCHEMA IF NOT EXISTS mart")
    conn.execute("""
        CREATE OR REPLACE TABLE mart.sales_orders_day AS
        SELECT f.date, f.warehouse, f.orders,
               lw.orders AS orders_last_week,
               sum(f.orders) OVER w7 AS orders_7d_sum,
               count(f.orders) OVER w7 AS n_open_days_7d,
               CAST(round(avg(f.orders) OVER w7, 0) AS VARCHAR) AS orders_7d_avg_txt,
               CAST(round(100 * (f.orders / NULLIF(lw.orders, 0) - 1), 1) AS VARCHAR) AS orders_wow_pct_txt,
               f.order_index, f.user_activity_1, f.user_activity_2, f.mov_change,
               f.sku_sales_units, f.sku_revenue_eur, f.holiday, f.shops_closed
        FROM core.fct_warehouse_day f
        LEFT JOIN core.fct_warehouse_day lw
          ON lw.warehouse = f.warehouse AND lw.date = CAST(f.date - INTERVAL 7 DAY AS DATE)
        WHERE f.has_orders AND NOT f.is_forecast_period
        WINDOW w7 AS (PARTITION BY f.warehouse ORDER BY f.date
                      RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW)
        ORDER BY f.warehouse, f.date
    """)
    conn.execute("""
        CREATE OR REPLACE TABLE mart.ops_warehouse_day AS
        SELECT f.date, f.warehouse, f.orders,
               f.orders * w.items_per_order AS items_est,
               f.orders * w.items_per_order / w.picks_per_hour AS picking_hours_est,
               f.orders * w.items_per_order / w.picks_per_hour / w.shift_hours AS picker_shifts_est,
               f.orders / w.orders_per_driver_shift AS driver_shifts_est,
               f.orders * w.items_per_order / w.picks_per_hour * w.hourly_wage_eur AS picking_cost_est_eur,
               COALESCE(f.shutdown OR f.mini_shutdown OR f.blackout OR f.frankfurt_shutdown, FALSE) AS any_disruption,
               f.shutdown, f.mini_shutdown, f.blackout, f.frankfurt_shutdown,
               f.holiday, f.shops_closed, f.precipitation, f.snow
        FROM core.fct_warehouse_day f
        JOIN core.params_workforce w USING (warehouse)
        WHERE f.has_orders AND NOT f.is_forecast_period
        ORDER BY f.warehouse, f.date
    """)
    conn.execute("""
        CREATE OR REPLACE TABLE mart.category_sku_day AS
        SELECT date, warehouse, L1_category_name_en,
               any_value(currency) AS currency,
               count(DISTINCT unique_id) FILTER (WHERE NOT sales_missing) AS n_sku_sold,
               count(*) AS n_sku_rows,
               sum(sales) AS sales_units,
               sum(revenue_local) AS revenue_local,
               sum(revenue_eur) AS revenue_eur,
               sum(availability) AS sum_availability,
               count(availability) AS n_availability_rows,
               count(*) FILTER (WHERE stockout_flag) AS n_stockout_sku_days,
               CAST(round(avg(availability), 3) AS VARCHAR) AS avg_availability_txt,
               CAST(round(count(*) FILTER (WHERE stockout_flag) / count(*), 3) AS VARCHAR) AS stockout_share_txt,
               count(*) FILTER (WHERE sales_missing) AS n_null_sales
        FROM core.fct_sku_day
        GROUP BY date, warehouse, L1_category_name_en
        ORDER BY warehouse, date, L1_category_name_en
    """)
    conn.execute("""
        CREATE OR REPLACE TABLE mart.marketing_promo_day AS
        SELECT date, warehouse, L1_category_name_en,
               count(*) AS n_sku_rows,
               count(*) FILTER (WHERE has_promo) AS n_sku_promo,
               sum(max_discount) FILTER (WHERE has_promo) AS sum_discount_promo,
               CAST(round(count(*) FILTER (WHERE has_promo) / count(*), 3) AS VARCHAR) AS promo_sku_share_txt,
               CAST(round(avg(max_discount) FILTER (WHERE has_promo), 3) AS VARCHAR) AS avg_discount_promo_txt,
               sum(sales) FILTER (WHERE has_promo) AS sales_units_promo,
               sum(sales) FILTER (WHERE NOT has_promo) AS sales_units_no_promo,
               sum(revenue_eur) FILTER (WHERE has_promo) AS revenue_eur_promo,
               sum(revenue_eur) FILTER (WHERE NOT has_promo) AS revenue_eur_no_promo,
               count(*) FILTER (WHERE discount_anomaly) AS n_discount_anomaly
        FROM core.fct_sku_day
        GROUP BY date, warehouse, L1_category_name_en
        ORDER BY warehouse, date, L1_category_name_en
    """)
    conn.execute("""
        CREATE OR REPLACE TABLE mart.exec_kpi_month AS
        WITH m AS (
            SELECT warehouse, CAST(date_trunc('month', date) AS DATE) AS month,
                   count(*) FILTER (WHERE has_orders) AS days_with_orders,
                   sum(orders) AS total_orders,
                   avg(orders) AS avg_daily_orders,
                   sum(sku_revenue_eur) AS revenue_eur,
                   min(date) FILTER (WHERE has_orders) AS d0,
                   max(date) FILTER (WHERE has_orders) AS d1
            FROM core.fct_warehouse_day WHERE NOT is_forecast_period
            GROUP BY ALL)
        SELECT month, warehouse, days_with_orders, total_orders, revenue_eur,
               lag(total_orders) OVER w AS total_orders_prev_month,
               lag(days_with_orders) OVER w AS days_with_orders_prev_month,
               lag(revenue_eur) OVER w AS revenue_eur_prev_month,
               CAST(round(avg_daily_orders, 0) AS VARCHAR) AS avg_daily_orders_txt,
               CAST(round(100 * (avg_daily_orders / NULLIF(lag(avg_daily_orders) OVER w, 0) - 1), 1) AS VARCHAR)
                   AS avg_daily_orders_mom_pct_txt,
               CAST(round(100 * (revenue_eur / NULLIF(lag(revenue_eur) OVER w, 0) - 1), 1) AS VARCHAR)
                   AS revenue_eur_mom_pct_txt,
               COALESCE(d0 > month OR d1 < last_day(month), TRUE) AS is_partial_month
        FROM m
        WINDOW w AS (PARTITION BY warehouse ORDER BY month)
        ORDER BY warehouse, month
    """)
    return {name: int(conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]) for name in BASE_MARTS}


_MODEL_MART_SQL = {
    "mart.bt1_forecast_orders": """
        CREATE OR REPLACE VIEW mart.bt1_forecast_orders AS
        SELECT o.date, o.warehouse,
               o.p50 AS orders_p50, o.p90 AS orders_p90, o.p90_scenario AS orders_p90_scenario,
               i.p50 AS order_index_p50, i.p90 AS order_index_p90,
               o.closed, o.risk_flag, o.note, o.model, o.run_id
        FROM pred.fc_orders o
        LEFT JOIN pred.fc_orders i ON i.series = 'order_index' AND i.warehouse = o.warehouse AND i.date = o.date
        WHERE o.series = 'orders'""",
    "mart.bt2_staff_driver_plan": """
        CREATE OR REPLACE VIEW mart.bt2_staff_driver_plan AS
        WITH s AS (
            SELECT warehouse, date,
                   sum(staff) FILTER (WHERE shift = 'morning') AS staff_morning,
                   sum(staff) FILTER (WHERE shift = 'afternoon') AS staff_afternoon,
                   sum(staff) AS staff_total, sum(cost_eur) AS staff_cost_eur,
                   any_value(policy) AS policy, any_value(run_id) AS run_id
            FROM pred.staff_plan GROUP BY warehouse, date)
        SELECT s.date, s.warehouse, s.staff_morning, s.staff_afternoon, s.staff_total, s.staff_cost_eur,
               d.orders_p50, d.orders_p90, d.drivers_needed, s.policy, s.run_id
        FROM s LEFT JOIN pred.driver_plan d ON d.warehouse = s.warehouse AND d.date = s.date""",
    "mart.bt3_lost_sales_day": """
        CREATE OR REPLACE VIEW mart.bt3_lost_sales_day AS
        SELECT date, warehouse, L1 AS L1_category_name_en,
               count(*) AS n_sku_rows,
               count(*) FILTER (WHERE lost_units > 0) AS n_sku_stockout,
               sum(sales) AS sales_units, sum(est_demand) AS est_demand_units,
               sum(lost_units) AS lost_units,
               sum(lost_revenue) AS lost_revenue_local,
               sum(lost_revenue_eur) AS lost_revenue_eur,
               any_value(currency) AS currency
        FROM pred.lost_sales GROUP BY date, warehouse, L1""",
    "mart.bt4_bt6_sku_plan_day": """
        CREATE OR REPLACE VIEW mart.bt4_bt6_sku_plan_day AS
        SELECT f.date, f.warehouse, f.L1 AS L1_category_name_en,
               count(*) AS n_sku,
               sum(f.p50) AS demand_p50_units, sum(f.p90) AS demand_p90_units,
               sum(r.order_qty) AS order_qty_units,
               sum(f.p50 * f.final_price * dw.fx_eur) AS demand_p50_value_eur,
               sum(r.order_qty * r.final_price * dw.fx_eur) AS order_value_eur,
               any_value(r.policy) AS replenishment_policy, any_value(f.model) AS forecast_model
        FROM pred.fc_sku f
        LEFT JOIN core.dim_warehouse dw ON dw.warehouse = f.warehouse
        LEFT JOIN {replenishment} r ON r.unique_id = f.unique_id AND r.date = f.date
        GROUP BY f.date, f.warehouse, f.L1""",
    "mart.bt5_promo_effect": """
        CREATE OR REPLACE VIEW mart.bt5_promo_effect AS
        SELECT L1 AS L1_category_name_en, discount, "lift_%" AS lift_pct, "ci_low_%" AS ci_low_pct,
               "ci_high_%" AS ci_high_pct, theta, method, run_id
        FROM pred.promo_effect""",
    "mart.bt7_markdown_day": """
        CREATE OR REPLACE VIEW mart.bt7_markdown_day AS
        SELECT date, warehouse, L1 AS L1_category_name_en,
               count(*) AS n_sku,
               count(*) FILTER (WHERE discount > 0) AS n_sku_markdown,
               sum(stock) AS stock_units, sum(expiring_today) AS expiring_units,
               sum(expected_waste) AS expected_waste_units,
               CAST(round(avg(discount) FILTER (WHERE discount > 0), 3) AS VARCHAR) AS avg_markdown_txt,
               any_value(currency) AS currency
        FROM pred.markdown_plan GROUP BY date, warehouse, L1""",
    "mart.bt8_growth_month": """
        CREATE OR REPLACE VIEW mart.bt8_growth_month AS
        WITH base AS (SELECT warehouse, min(month) AS m0 FROM pred.growth_curves GROUP BY warehouse)
        SELECT CAST(b.m0 + to_months(CAST(p.t AS INTEGER)) AS DATE) AS month, p.warehouse, p.t,
               c.orders AS orders_actual, p.fitted AS orders_fitted, p.model
        FROM pred.growth_projection p
        JOIN base b USING (warehouse)
        LEFT JOIN pred.growth_curves c ON c.warehouse = p.warehouse AND c.t = p.t""",
}


def build_model_marts(conn: duckdb.DuckDBPyConnection) -> dict[str, bool]:
    """Tạo/ghi lại view kết quả mô hình nếu đã có bảng pred.* tương ứng (chưa có → bỏ qua)."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS mart")
    built = {}
    for mart, needs in MODEL_MARTS.items():
        ok = all(table_exists(conn, *name.split(".")) for name in needs)
        if ok and mart == "mart.bt4_bt6_sku_plan_day" and not table_exists(conn, "core", "dim_warehouse"):
            ok = False
        if ok:
            sql = _MODEL_MART_SQL[mart]
            if mart == "mart.bt4_bt6_sku_plan_day":
                repl = ("pred.replenishment" if table_exists(conn, "pred", "replenishment") else
                        "(SELECT NULL::BIGINT AS unique_id, NULL::DATE AS date, NULL::DOUBLE AS order_qty, "
                        "NULL::DOUBLE AS final_price, NULL::VARCHAR AS policy WHERE FALSE)")
                sql = sql.format(replenishment=repl)
            conn.execute(sql)
        else:
            conn.execute(f"DROP VIEW IF EXISTS {mart}")
        built[mart] = ok
    return built
