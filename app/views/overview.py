"""Executive overview backed by sales-orders mart and BT1/BT8 models when available."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from app.auth import require_admin
from app.common import (
    DataStatus,
    ModelState,
    PageSpec,
    _find_column,
    _model_states,
    _readiness,
    _records,
)
from app.services.reporting import MartInfo, ReportingError, ReportingService, WarehouseInfo
from app.ui.components import render_chart_header, render_header, render_kpi


SPEC = PageSpec(
    title="Tổng quan",
    description="Theo dõi dữ liệu đơn hàng lịch sử đã được Data Engineering publish và kiểm định.",
    mart="mart.sales_orders_day",
    model_states=(
        ModelState(
            "Triển vọng · BT1 dự báo đơn 14 ngày",
            "Số đơn P50/P90 từng kho 16/03 → 29/03/2024 (LightGBM quantile, P90 đã hiệu chỉnh).",
            "mart.bt1_forecast_orders",
        ),
        ModelState(
            "BT8 · Tăng trưởng kho mới",
            "Đường cong ramp-up Munich_1, Frankfurt_1 + chiếu 12 tháng.",
            "mart.bt8_growth_month",
        ),
    ),
)


def _render_overview_content(
    service: ReportingService,
    info: MartInfo,
    warehouse: WarehouseInfo,
) -> None:
    warehouse_column = _find_column(info, ("warehouse",))
    date_column = _find_column(info, ("date",))

    filters: dict[str, object] = {}
    warehouses: tuple[object, ...] = ()
    bounds: tuple[object | None, object | None] = (None, None)

    with st.container(border=True):
        filter_cols = st.columns([1, 1.4])
        if warehouse_column:
            warehouses = service.distinct_values(info.name, warehouse_column)
            selected_wh = filter_cols[0].selectbox(
                "Kho hàng (Warehouse)",
                ("Tất cả", *warehouses),
                key="overview-warehouse-filter",
            )
            if selected_wh != "Tất cả":
                filters[warehouse_column] = selected_wh

        if date_column:
            bounds = service.date_bounds(info.name, date_column)
            if bounds[0] is not None and bounds[1] is not None:
                selected_dates = filter_cols[1].date_input(
                    "Khoảng thời gian phân tích",
                    value=(bounds[0], bounds[1]),
                    min_value=bounds[0],
                    max_value=bounds[1],
                    key="overview-date-filter",
                )
                if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
                    filters[date_column] = selected_dates

    # Business KPIs
    total_rows = service.row_count(info.name, filters=filters)
    series_rows: tuple[tuple[object, ...], ...] = ()
    if date_column:
        series_res = service.aggregate_series(
            info.name, date_column=date_column, metric_column="orders", filters=filters
        )
        series_rows = series_res.rows

    if series_rows:
        total_orders = sum(float(r[1]) for r in series_rows)
        days_count = len(series_rows)
        avg_daily = round(total_orders / days_count) if days_count else 0
        min_date = series_rows[0][0]
        max_date = series_rows[-1][0]
        coverage_text = f"{min_date} → {max_date}"
        wh_display = (
            "1 kho" if filters.get(warehouse_column or "") else f"{len(warehouses)} kho"
        )
    else:
        total_orders = 0
        avg_daily = 0
        coverage_text = "Chưa có dữ liệu"
        wh_display = "—"

    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        render_kpi(
            "Tổng đơn hàng",
            f"{int(total_orders):,}" if series_rows else "—",
            unit="đơn" if series_rows else "",
            subtitle=f"Trong phạm vi lọc ({len(series_rows)} ngày)" if series_rows else "Không có đơn hàng",
        )
    with kpi_cols[1]:
        render_kpi(
            "Trung bình / ngày",
            f"{int(avg_daily):,}" if series_rows else "—",
            unit="đơn/ngày" if series_rows else "",
            subtitle="Đơn hàng bình quân mỗi ngày",
        )
    with kpi_cols[2]:
        render_kpi(
            "Kho hoạt động",
            wh_display,
            subtitle="Số kho ghi nhận đơn hàng",
        )
    with kpi_cols[3]:
        render_kpi(
            "Phạm vi dữ liệu",
            coverage_text,
            subtitle="Thời điểm chốt as_of: 15/03/2024",
        )

    # Main Analytical Chart
    st.subheader("Diễn biến khối lượng đơn hàng")
    render_chart_header(
        "Khối lượng đơn hàng lịch sử theo thời gian",
        "Chuỗi đơn hàng thực tế (Historical Actual) · Nguồn: mart.sales_orders_day",
    )

    if series_rows:
        df_actual = pd.DataFrame(series_rows, columns=["date", "orders"])
        df_actual["date"] = pd.to_datetime(df_actual["date"])
        chart = (
            alt.Chart(df_actual)
            .mark_line(color="#172B4D", strokeWidth=2)
            .encode(
                x=alt.X("date:T", title="Thời gian (Ngày)"),
                y=alt.Y("orders:Q", title="Số lượng đơn hàng"),
                tooltip=[
                    alt.Tooltip("date:T", title="Ngày", format="%Y-%m-%d"),
                    alt.Tooltip("orders:Q", title="Đơn hàng", format=","),
                ],
            )
            .properties(height=360)
            .interactive()
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Không có dữ liệu trong khoảng thời gian hoặc bộ lọc đã chọn.")

    # Check for BT1 model results mart without creating fake data
    bt1_mart = next((m for m in warehouse.marts if m.name == "mart.bt1_forecast_orders"), None)
    if not (bt1_mart and bt1_mart.exists):
        st.info(
            "ℹ️ BT1: Chưa có kết quả dự báo — Kết quả dự báo 14 ngày (P50/P90) sẽ hiển thị tại đây "
            "sau khi chạy mô hình trên Terminal bằng lệnh `python -m pipeline.run models`."
        )

    # Model Results Section (BT1 & BT8)
    _model_states(SPEC.model_states, service, warehouse)

    # Detailed Data Table
    st.subheader("Dữ liệu chi tiết đơn hàng")
    st.caption("Trích xuất trực tiếp từ mart.sales_orders_day bằng truy vấn phân trang an toàn.")

    tbl_controls = st.columns([1, 1])
    page_size = tbl_controls[0].selectbox(
        "Số dòng mỗi trang", (25, 50, 100, 250), index=1, key="overview-page-size"
    )
    max_page = max(1, (total_rows + page_size - 1) // page_size)
    page = int(
        tbl_controls[1].number_input(
            "Trang", min_value=1, max_value=max_page, value=1, step=1, key="overview-page"
        )
    )
    result = service.fetch_page(
        info.name, filters=filters, limit=page_size, offset=(page - 1) * page_size
    )
    st.dataframe(_records(result), use_container_width=True, hide_index=True)
    st.caption(
        f"Trang {page}/{max_page} · {total_rows:,} dòng dữ liệu · Kết nối DuckDB read-only · Query SELECT allowlisted"
    )


def render() -> None:
    """Render the Modern Commerce Analytics Executive Overview page."""
    require_admin()
    render_header(
        SPEC.title,
        SPEC.description,
        as_of="15/03/2024",
    )

    service = ReportingService()
    try:
        warehouse = service.warehouse_info()
        info = next((mart for mart in warehouse.marts if mart.name == SPEC.mart), None)
    except ReportingError as exc:
        _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))
        _model_states(SPEC.model_states)
        return

    if not warehouse.exists:
        _readiness(
            DataStatus.WAREHOUSE_NOT_READY,
            "Warehouse chưa tồn tại. Dashboard không tạo database và không chạy pipeline từ giao diện.",
        )
        st.markdown(
            """
            <div class="rdh-empty">
              <h2>Kho dữ liệu DuckDB chưa sẵn sàng</h2>
              <p>
                Không tìm thấy file kho dữ liệu DuckDB tại đường dẫn đã cấu hình.
                Rohlik Decision Hub hoạt động ở chế độ read-only và không tự khởi tạo database qua giao diện web.
              </p>
              <p style="font-size: 0.85rem; color: var(--rdh-secondary-text);">
                Vui lòng mở Terminal và chạy lệnh sau để khởi tạo dữ liệu kho:
              </p>
              <code style="background: #F1F5F9; padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.88rem; color: #172B4D;">
                python -m pipeline.run init
              </code>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _model_states(SPEC.model_states)
        return

    if info is None or not info.exists:
        _readiness(
            DataStatus.TABLE_NOT_AVAILABLE,
            f"{SPEC.mart} chưa tồn tại. Chờ Data Engineering publish mart đã kiểm định.",
        )
        st.markdown(
            '<div class="rdh-empty"><h2>Chưa có dữ liệu để hiển thị</h2>'
            '<p>Trang này không dựng KPI thay thế và không đọc trực tiếp raw CSV. '
            'Sau khi mart sẵn sàng, khởi động lại Streamlit để mở dữ liệu lịch sử.</p></div>',
            unsafe_allow_html=True,
        )
        _model_states(SPEC.model_states, service, warehouse)
        return

    _readiness(
        DataStatus.DATA_READY,
        f"Đang đọc {SPEC.mart} bằng kết nối DuckDB read-only và query allowlisted.",
    )
    try:
        _render_overview_content(service, info, warehouse)
    except ReportingError as exc:
        _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))
