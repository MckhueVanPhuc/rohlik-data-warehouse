"""Lớp Core: 6 bảng (M2 mục 7) – 2 fact, 2 dimension, 2 bảng tham số giả định.

Thứ tự: params_cost, params_workforce → dim_product, dim_warehouse → fct_sku_day → fct_warehouse_day.
Quy tắc bất thường (D04): giữ NULL + gắn cờ; giảm giá âm giữ nguyên 7 cột gốc, max_discount kẹp [0, 1]
+ cờ discount_anomaly; không thay 0. Tiền tệ (D07): nội tệ + fx_eur giả định từ settings.
"""

from __future__ import annotations

import duckdb

from src.config.settings import Settings

CORE_TABLES = (
    "core.params_cost", "core.params_workforce", "core.dim_product",
    "core.dim_warehouse", "core.fct_sku_day", "core.fct_warehouse_day",
)
DISCOUNTS = [f"type_{i}_discount" for i in range(7)]


def _register_reference(conn: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    """Bảng tạm danh sách kho + tiền tệ + tỷ giá từ settings (không viết cứng trong SQL)."""
    conn.execute("CREATE OR REPLACE TEMP TABLE _wh (warehouse VARCHAR, currency VARCHAR, fx_eur DOUBLE, "
                 "is_new_warehouse BOOLEAN)")
    rows = [(w, settings.currency(w), settings.fx(w), w in settings.new_warehouses) for w in settings.warehouses]
    conn.executemany("INSERT INTO _wh VALUES (?, ?, ?, ?)", rows)


def build_core(conn: duckdb.DuckDBPyConnection, settings: Settings) -> dict[str, int]:
    """Ghi lại 6 bảng Core trong transaction của người gọi; trả số dòng mỗi bảng."""
    p = settings.sql_params()
    conn.execute("CREATE SCHEMA IF NOT EXISTS core")
    _register_reference(conn, settings)

    conn.execute("""
        CREATE OR REPLACE TABLE core.params_cost AS
        SELECT L1_category_name_en, cost_ratio, shelf_life_days, waste_handling_cost_ratio,
               'ASSUMED' AS source_type
        FROM stg.cost_params ORDER BY L1_category_name_en
    """)
    conn.execute("""
        CREATE OR REPLACE TABLE core.params_workforce AS
        SELECT warehouse, hourly_wage_eur, items_per_order, picks_per_hour, shift_hours,
               morning_shift_ratio, overtime_multiplier, overtime_cap_ratio,
               shortage_penalty_multiplier, legacy_rule_buffer_ratio, orders_per_driver_shift,
               'ASSUMED' AS source_type
        FROM stg.workforce_params ORDER BY warehouse
    """)
    conn.execute("""
        CREATE OR REPLACE TABLE core.dim_product AS
        WITH s AS (
            SELECT unique_id, min(date) AS first_sale_date, max(date) AS last_sale_date, count(*) AS n_sale_days
            FROM stg.sku_sales_daily WHERE date BETWEEN ? AND ? GROUP BY unique_id)
        SELECT p.unique_id, p.product_unique_id, p.name, p.warehouse,
               p.L1_category_name_en, p.L2_category_name_en, p.L3_category_name_en, p.L4_category_name_en,
               w.weight, w.weight IS NOT NULL AS has_weight,
               s.first_sale_date, s.last_sale_date, s.n_sale_days
        FROM stg.product_master p
        LEFT JOIN stg.sku_weights w USING (unique_id)
        LEFT JOIN s USING (unique_id)
        ORDER BY p.unique_id
    """, [p["train_from"], p["as_of"]])
    conn.execute("""
        CREATE OR REPLACE TABLE core.dim_warehouse AS
        WITH o AS (
            SELECT warehouse,
                   min(date) FILTER (WHERE orders IS NOT NULL) AS first_order_date,
                   max(date) FILTER (WHERE orders IS NOT NULL) AS last_order_date,
                   count(orders) AS n_order_days
            FROM stg.orders_daily WHERE date BETWEEN ? AND ? GROUP BY warehouse)
        SELECT wh.warehouse, wh.currency, wh.fx_eur, wh.is_new_warehouse,
               o.first_order_date, o.last_order_date, o.n_order_days,
               pw.warehouse IS NOT NULL AS has_workforce_params
        FROM _wh wh
        LEFT JOIN o USING (warehouse)
        LEFT JOIN core.params_workforce pw USING (warehouse)
        ORDER BY wh.warehouse
    """, [p["train_from"], p["as_of"]])

    greatest = "GREATEST(" + ", ".join(f"pr.{c}" for c in DISCOUNTS) + ")"
    least = "LEAST(" + ", ".join(f"pr.{c}" for c in DISCOUNTS) + ")"
    clipped = f"LEAST(GREATEST({greatest}, 0), 1)"
    # Thiếu dòng promotions → max_discount NULL, has_promo FALSE (không bịa 0 – M2 7.2 cảnh báo).
    conn.execute(f"""
        CREATE OR REPLACE TABLE core.fct_sku_day AS
        SELECT s.unique_id, s.date, s.warehouse, wh.currency, wh.fx_eur,
               m.product_unique_id, m.name, m.L1_category_name_en, m.L2_category_name_en,
               m.L3_category_name_en, m.L4_category_name_en,
               s.sales, s.sales IS NULL AS sales_missing, s.total_orders,
               p.sell_price_main, p.sell_price_main IS NULL AS price_missing,
               {", ".join(f"pr.{c}" for c in DISCOUNTS)},
               CASE WHEN pr.unique_id IS NULL THEN NULL ELSE {clipped} END AS max_discount,
               COALESCE({least} < 0 OR {greatest} > 1, FALSE) AS discount_anomaly,
               COALESCE({clipped} > 0, FALSE) AS has_promo,
               p.sell_price_main * (1 - COALESCE({clipped}, 0)) AS final_price,
               s.sales * p.sell_price_main * (1 - COALESCE({clipped}, 0)) AS revenue_local,
               s.sales * p.sell_price_main * (1 - COALESCE({clipped}, 0)) * wh.fx_eur AS revenue_eur,
               a.availability, a.availability < 1 AS stockout_flag,
               m.weight, c.holiday = 1 AS holiday, c.shops_closed = 1 AS shops_closed
        FROM stg.sku_sales_daily s
        JOIN _wh wh USING (warehouse)
        LEFT JOIN stg.prices p ON p.unique_id = s.unique_id AND p.date = s.date
        LEFT JOIN stg.promotions pr ON pr.unique_id = s.unique_id AND pr.date = s.date
        LEFT JOIN stg.availability a ON a.unique_id = s.unique_id AND a.date = s.date
        LEFT JOIN core.dim_product m ON m.unique_id = s.unique_id
        LEFT JOIN stg.calendar c ON c.warehouse = s.warehouse AND c.date = s.date
        WHERE s.date BETWEEN ? AND ?
    """, [p["train_from"], p["as_of"]])

    conn.execute("""
        CREATE OR REPLACE TABLE core.fct_warehouse_day AS
        WITH spine AS (
            SELECT c.warehouse, c.date FROM stg.calendar c
            WHERE c.warehouse IN (SELECT warehouse FROM _wh) AND c.date BETWEEN ? AND ?
            UNION
            SELECT o.warehouse, o.date FROM stg.orders_daily o
            WHERE o.warehouse IN (SELECT warehouse FROM _wh) AND o.date BETWEEN ? AND ?),
        sku AS (
            SELECT warehouse, date,
                   median(total_orders) AS order_index,
                   count(*) FILTER (WHERE NOT sales_missing) AS n_sku_rows,
                   count(*) FILTER (WHERE sales_missing) AS n_null_sales,
                   sum(sales) AS sku_sales_units,
                   sum(revenue_local) AS sku_revenue_local
            FROM core.fct_sku_day GROUP BY ALL)
        SELECT s.warehouse, s.date, wh.currency, wh.fx_eur,
               CASE WHEN s.date <= ? THEN o.orders END AS orders,
               (s.date <= ? AND o.orders IS NOT NULL) AS has_orders, s.date > ? AS is_forecast_period,
               k.order_index, k.n_sku_rows, k.n_null_sales, k.sku_sales_units,
               k.sku_revenue_local, k.sku_revenue_local * wh.fx_eur AS sku_revenue_eur,
               c.holiday_name, c.holiday = 1 AS holiday, c.shops_closed = 1 AS shops_closed,
               c.winter_school_holidays = 1 AS winter_school_holidays, c.school_holidays = 1 AS school_holidays,
               c.warehouse IS NULL AS calendar_missing,
               e.shutdown = 1 AS shutdown, e.mini_shutdown = 1 AS mini_shutdown,
               e.blackout = 1 AS blackout, e.frankfurt_shutdown = 1 AS frankfurt_shutdown,
               m.mov_change, u.user_activity_1, u.user_activity_2, w.precipitation, w.snow,
               (w.precipitation IS NULL OR w.snow IS NULL) AS weather_missing
        FROM spine s
        JOIN _wh wh USING (warehouse)
        LEFT JOIN stg.orders_daily o ON o.warehouse = s.warehouse AND o.date = s.date
        LEFT JOIN stg.calendar c ON c.warehouse = s.warehouse AND c.date = s.date
        LEFT JOIN stg.ops_events e ON e.warehouse = s.warehouse AND e.date = s.date
        LEFT JOIN stg.mov_changes m ON m.warehouse = s.warehouse AND m.date = s.date
        LEFT JOIN stg.user_activity u ON u.warehouse = s.warehouse AND u.date = s.date
        LEFT JOIN stg.weather w ON w.warehouse = s.warehouse AND w.date = s.date
        LEFT JOIN sku k ON k.warehouse = s.warehouse AND k.date = s.date
        ORDER BY s.warehouse, s.date
    """, [p["train_from"], p["forecast_end"], p["train_from"], p["as_of"], p["as_of"], p["as_of"], p["as_of"]])
    counts = {name: int(conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]) for name in CORE_TABLES}
    conn.execute("DROP TABLE IF EXISTS _wh")
    return counts
