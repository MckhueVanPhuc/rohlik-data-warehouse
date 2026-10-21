"""Shared dashboard UI primitives for the admin-only Streamlit application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from html import escape
import os
from typing import Sequence

import pandas as pd
import streamlit as st

from app.services.reporting import MartInfo, QueryResult, ReportingError, ReportingService, WarehouseInfo


class DataStatus(str, Enum):
    WAREHOUSE_NOT_READY = "WAREHOUSE_NOT_READY"
    TABLE_NOT_AVAILABLE = "TABLE_NOT_AVAILABLE"
    DATA_READY = "DATA_READY"
    PENDING_MODEL = "PENDING_MODEL"
    DQ_FAILED = "DQ_FAILED"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"
    SOURCES_READY = "SOURCES_READY"
    LANDING_READY = "LANDING_READY"
    MART_READY = "MART_READY"


@dataclass(frozen=True)
class ModelState:
    title: str
    detail: str


@dataclass(frozen=True)
class PageSpec:
    title: str
    description: str
    mart: str
    model_states: tuple[ModelState, ...] = ()


_STATUS_META = {
    DataStatus.WAREHOUSE_NOT_READY: ("warning", "Kho dữ liệu chưa sẵn sàng"),
    DataStatus.TABLE_NOT_AVAILABLE: ("neutral", "Mart chưa có"),
    DataStatus.DATA_READY: ("success", "Dữ liệu sẵn sàng"),
    DataStatus.PENDING_MODEL: ("model", "Chờ mô hình"),
    DataStatus.DQ_FAILED: ("danger", "Kiểm tra chất lượng thất bại"),
    DataStatus.REFRESH_REQUIRED: ("warning", "Dữ liệu cần được cập nhật ngoài UI"),
    DataStatus.SOURCES_READY: ("success", "Nguồn sẵn sàng"),
    DataStatus.LANDING_READY: ("success", "Landing sẵn sàng"),
    DataStatus.MART_READY: ("success", "Mart sẵn sàng"),
}


def apply_app_styles() -> None:
    """Apply the established restrained dark visual system."""

    st.markdown(
        """
        <style>
        :root {
            --rdh-ink: #eef4f2; --rdh-muted: #a5b5b0; --rdh-line: #263b37;
            --rdh-panel: #111d1b; --rdh-accent: #54d2a0;
            --rdh-warning: #f1bd66; --rdh-danger: #ff8585;
        }
        .stApp { background: #09110f; }
        .block-container { max-width: 1180px; padding-top: 2.7rem; }
        [data-testid="stSidebar"] { border-right: 1px solid var(--rdh-line); }
        [data-testid="stSidebarNav"] { padding-top: 0.4rem; }
        [data-testid="stSidebarNav"] span { letter-spacing: -0.01em; }
        .rdh-brand { padding: 0.35rem 0 0.9rem; }
        .rdh-brand__name { color: var(--rdh-ink); font-size: 1.06rem; font-weight: 720; }
        .rdh-brand__meta { color: var(--rdh-muted); font-size: 0.77rem; margin-top: 0.2rem; }
        .rdh-mode {
            align-items: center; background: #10241e; border: 1px solid #285a49;
            border-radius: 999px; color: #9aebca; display: inline-flex;
            font-size: 0.68rem; font-weight: 750; letter-spacing: 0.09em;
            margin-top: 0.7rem; padding: 0.23rem 0.58rem;
        }
        .rdh-mode::before {
            background: var(--rdh-accent); border-radius: 50%; content: "";
            height: 0.42rem; margin-right: 0.42rem; width: 0.42rem;
        }
        .rdh-heading-copy { border-bottom: 1px solid var(--rdh-line); padding-bottom: 1.5rem; }
        h1 { color: var(--rdh-ink); font-size: 2.65rem; letter-spacing: -0.035em; line-height: 1.05; }
        .rdh-heading-copy p {
            color: var(--rdh-muted); font-size: 1rem; line-height: 1.65;
            margin: 0.8rem 0 0; max-width: 72ch;
        }
        .rdh-readiness {
            align-items: flex-start; background: var(--rdh-panel); border: 1px solid var(--rdh-line);
            border-radius: 0.7rem; display: flex; gap: 0.9rem; margin: 1.5rem 0 2rem;
            padding: 1rem 1.1rem;
        }
        .rdh-readiness__copy { color: var(--rdh-muted); font-size: 0.88rem; line-height: 1.55; }
        .rdh-status {
            border: 1px solid currentColor; border-radius: 999px; display: inline-flex;
            flex: 0 0 auto; font-size: 0.64rem; font-weight: 780; letter-spacing: 0.07em;
            line-height: 1; padding: 0.34rem 0.5rem; text-transform: uppercase;
        }
        .rdh-status--warning { color: var(--rdh-warning); }
        .rdh-status--neutral { color: #b8c5c1; }
        .rdh-status--success { color: var(--rdh-accent); }
        .rdh-status--model { color: #b7c3ff; }
        .rdh-status--danger { color: var(--rdh-danger); }
        .rdh-empty { max-width: 72ch; padding: 0.4rem 0 1.4rem; }
        .rdh-empty h3 { color: var(--rdh-ink); margin-bottom: 0.45rem; }
        .rdh-empty p { color: var(--rdh-muted); line-height: 1.65; }
        .rdh-model {
            border-top: 1px solid var(--rdh-line); display: grid; gap: 1rem;
            grid-template-columns: minmax(12rem, .7fr) minmax(16rem, 1.4fr) auto; padding: 1rem 0;
        }
        .rdh-model:last-child { border-bottom: 1px solid var(--rdh-line); }
        .rdh-model__title { color: var(--rdh-ink); font-weight: 650; }
        .rdh-model__copy { color: var(--rdh-muted); font-size: .86rem; line-height: 1.55; }
        div[data-testid="stMetric"] { background: var(--rdh-panel); border: 1px solid var(--rdh-line); padding: .9rem 1rem; }
        div[data-testid="stDataFrame"] { border: 1px solid var(--rdh-line); }
        div.stButton > button:focus-visible, input:focus-visible,
        [role="combobox"]:focus-visible { outline: 2px solid var(--rdh-accent); outline-offset: 2px; }
        ::selection { background: #256e56; color: #fff; }
        * { scrollbar-color: #35534b #0d1715; }
        [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
        @media (max-width: 700px) {
            .block-container { padding-top: 1.8rem; }
            h1 { font-size: 2.1rem; }
            .rdh-model { grid-template-columns: 1fr; gap: .45rem; }
            .rdh-readiness { flex-direction: column; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: DataStatus) -> str:
    variant, label = _STATUS_META[status]
    return (
        f'<span class="rdh-status rdh-status--{variant}" '
        f'aria-label="Trạng thái: {escape(label)}">{escape(status.value)}</span>'
    )


def network_mode() -> str:
    return "LAN" if os.getenv("RDH_NETWORK_MODE", "").upper() == "LAN" else "LOCAL"


def render_sidebar_context(username: str, warehouse: WarehouseInfo) -> None:
    if not warehouse.exists:
        warehouse_label = "Không tìm thấy warehouse"
    elif warehouse.ready_mart_count == len(warehouse.marts):
        warehouse_label = "5/5 reporting marts sẵn sàng"
    else:
        warehouse_label = f"{warehouse.ready_mart_count}/5 reporting marts sẵn sàng"
    st.sidebar.markdown(
        f"""
        <div class="rdh-brand">
          <div class="rdh-brand__name">Rohlik Decision Hub</div>
          <div class="rdh-brand__meta">Dashboard quản trị · Chỉ đọc</div>
          <div class="rdh-mode">{network_mode()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.caption("Trạng thái warehouse")
    st.sidebar.caption(warehouse_label)
    st.sidebar.caption(f"Đăng nhập: **{username}**")
    st.sidebar.divider()


def _page_heading(spec: PageSpec) -> None:
    st.title(spec.title)
    st.markdown(
        f'<div class="rdh-heading-copy"><p>{escape(spec.description)}</p></div>',
        unsafe_allow_html=True,
    )


def _readiness(status: DataStatus, detail: str) -> None:
    st.markdown(
        f'<div class="rdh-readiness" role="status" aria-live="polite">{status_badge(status)}'
        f'<div class="rdh-readiness__copy">{escape(detail)}</div></div>',
        unsafe_allow_html=True,
    )


def _model_states(states: Sequence[ModelState]) -> None:
    if not states:
        return
    st.subheader("Đầu ra mô hình")
    rows = "".join(
            f'<div class="rdh-model" role="listitem"><div class="rdh-model__title">{escape(state.title)}</div>'
            f'<div class="rdh-model__copy">{escape(state.detail)}</div>'
            f'<div>{status_badge(DataStatus.PENDING_MODEL)}</div></div>'
            for state in states
    )
    st.markdown(
        f'<div role="list" aria-label="Trạng thái đầu ra mô hình">{rows}</div>',
        unsafe_allow_html=True,
    )


def _find_column(info: MartInfo, names: Sequence[str]) -> str | None:
    actual = {column.name.casefold(): column.name for column in info.columns}
    return next((actual[name.casefold()] for name in names if name.casefold() in actual), None)


def _records(result: QueryResult) -> list[dict[str, object]]:
    return [dict(zip(result.columns, row, strict=True)) for row in result.rows]


def _render_ready_mart(service: ReportingService, info: MartInfo, *, key_prefix: str) -> None:
    date_column = info.temporal_columns[0] if len(info.temporal_columns) == 1 else None
    if len(info.temporal_columns) > 1:
        date_column = st.selectbox("Cột thời gian", info.temporal_columns, key=f"{key_prefix}-date-column")
    warehouse_column = _find_column(info, ("warehouse",))
    category_column = _find_column(info, ("category", "l1_category_name_en"))

    filters: dict[str, object] = {}
    filter_count = sum(value is not None for value in (date_column, warehouse_column, category_column))
    filter_columns = st.columns(filter_count or 1)
    cursor = 0
    if warehouse_column:
        values = service.distinct_values(info.name, warehouse_column)
        selected = filter_columns[cursor].selectbox(
            "Warehouse", ("Tất cả", *values), key=f"{key_prefix}-warehouse"
        )
        cursor += 1
        if selected != "Tất cả":
            filters[warehouse_column] = selected
    if category_column:
        values = service.distinct_values(info.name, category_column)
        selected = filter_columns[cursor].selectbox(
            "Category", ("Tất cả", *values), key=f"{key_prefix}-category"
        )
        cursor += 1
        if selected != "Tất cả":
            filters[category_column] = selected
    bounds: tuple[object | None, object | None] = (None, None)
    if date_column:
        bounds = service.date_bounds(info.name, date_column)
        if bounds[0] is not None and bounds[1] is not None:
            selected_dates = filter_columns[cursor].date_input(
                "Khoảng thời gian", value=(bounds[0], bounds[1]),
                min_value=bounds[0], max_value=bounds[1], key=f"{key_prefix}-dates",
            )
            if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
                filters[date_column] = selected_dates

    total_rows = service.row_count(info.name, filters=filters)
    metrics = st.columns(3)
    metrics[0].metric("Số dòng phù hợp", f"{total_rows:,}")
    metrics[1].metric("Số cột", len(info.columns))
    coverage = "Chưa có cột thời gian"
    if bounds[0] is not None and bounds[1] is not None:
        coverage = f"{bounds[0]} → {bounds[1]}"
    metrics[2].metric("Phạm vi dữ liệu", coverage)

    if date_column and info.numeric_columns:
        metric_column = st.selectbox(
            "Chỉ số lịch sử", info.numeric_columns, key=f"{key_prefix}-metric",
            help="Danh sách lấy trực tiếp từ schema mart; biểu đồ dùng tổng theo thời gian.",
        )
        series = service.aggregate_series(
            info.name, date_column=date_column, metric_column=metric_column, filters=filters
        )
        if series.rows:
            frame = pd.DataFrame(series.rows, columns=series.columns).set_index("period")
            st.line_chart(frame, y="value", use_container_width=True)
        else:
            st.info("Không có dữ liệu trong phạm vi lọc đã chọn.")

    st.subheader("Dữ liệu chi tiết")
    page_controls = st.columns(2)
    page_size = page_controls[0].selectbox(
        "Số dòng mỗi trang", (25, 50, 100, 250), index=1, key=f"{key_prefix}-page-size"
    )
    max_page = max(1, (total_rows + page_size - 1) // page_size)
    page = int(page_controls[1].number_input(
        "Trang", min_value=1, max_value=max_page, value=1, step=1, key=f"{key_prefix}-page"
    ))
    result = service.fetch_page(
        info.name, filters=filters, limit=page_size, offset=(page - 1) * page_size
    )
    st.dataframe(_records(result), use_container_width=True, hide_index=True)
    st.caption(f"Trang {page}/{max_page} · Query SELECT allowlisted · Kết nối DuckDB read-only")


def render_page(spec: PageSpec) -> None:
    from app.auth import require_admin

    require_admin()
    _page_heading(spec)
    service = ReportingService()
    try:
        warehouse = service.warehouse_info()
        info = next(mart for mart in warehouse.marts if mart.name == spec.mart)
    except ReportingError as exc:
        _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))
        _model_states(spec.model_states)
        return

    if not warehouse.exists:
        _readiness(
            DataStatus.WAREHOUSE_NOT_READY,
            "Warehouse chưa tồn tại. Dashboard không tạo database và không chạy pipeline từ giao diện.",
        )
    elif not info.exists:
        _readiness(
            DataStatus.TABLE_NOT_AVAILABLE,
            f"{spec.mart} chưa tồn tại. Chờ Data Engineering publish mart đã kiểm định.",
        )
        st.markdown(
            '<div class="rdh-empty"><h2>Chưa có dữ liệu để hiển thị</h2>'
            '<p>Trang này không dựng KPI thay thế và không đọc trực tiếp raw CSV. '
            'Sau khi mart sẵn sàng, khởi động lại Streamlit để mở dữ liệu lịch sử.</p></div>',
            unsafe_allow_html=True,
        )
    else:
        _readiness(
            DataStatus.DATA_READY,
            f"Đang đọc {spec.mart} bằng kết nối DuckDB read-only và query allowlisted.",
        )
        try:
            _render_ready_mart(service, info, key_prefix=spec.mart.replace(".", "-"))
        except ReportingError as exc:
            _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))
    _model_states(spec.model_states)


def render_explorer() -> None:
    from app.auth import require_admin

    require_admin()
    spec = PageSpec(
        "Truy vấn & EDA",
        "Khám phá các reporting mart đã publish bằng bộ lọc và phân trang an toàn; không có SQL tùy ý.",
        "mart.sales_orders_day",
    )
    _page_heading(spec)
    service = ReportingService()
    try:
        warehouse = service.warehouse_info()
    except ReportingError as exc:
        _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))
        return
    ready = tuple(mart for mart in warehouse.marts if mart.exists)
    if not warehouse.exists:
        _readiness(DataStatus.WAREHOUSE_NOT_READY, "Warehouse chưa tồn tại; không có file nào được tạo.")
    elif not ready:
        _readiness(DataStatus.TABLE_NOT_AVAILABLE, "Chưa có reporting mart nào để truy vấn.")
    else:
        _readiness(DataStatus.DATA_READY, f"{len(ready)}/5 mart sẵn sàng cho EDA allowlisted.")
        selected = st.selectbox("Reporting mart", tuple(mart.name for mart in ready), key="eda-mart")
        info = next(mart for mart in ready if mart.name == selected)
        try:
            _render_ready_mart(service, info, key_prefix="eda")
        except ReportingError as exc:
            _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))


def render_system() -> None:
    from app.auth import require_admin

    require_admin()
    spec = PageSpec(
        "Vận hành hệ thống",
        "Theo dõi khả dụng của warehouse và reporting marts ở chế độ chỉ đọc.",
        "mart.exec_kpi_month",
    )
    _page_heading(spec)
    service = ReportingService()
    try:
        warehouse = service.warehouse_info()
    except ReportingError as exc:
        _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))
        return
    if not warehouse.exists:
        _readiness(DataStatus.WAREHOUSE_NOT_READY, "Không tìm thấy warehouse; UI không tự khởi tạo.")
    elif warehouse.ready_mart_count == len(warehouse.marts):
        _readiness(DataStatus.DATA_READY, "Tất cả reporting marts mục tiêu đang sẵn sàng.")
    else:
        _readiness(
            DataStatus.TABLE_NOT_AVAILABLE,
            f"{warehouse.ready_mart_count}/5 reporting marts sẵn sàng. Pipeline chỉ được vận hành ngoài Streamlit.",
        )
    rows = [
        {"Mart": mart.name, "Trạng thái": "DATA_READY" if mart.exists else "TABLE_NOT_AVAILABLE", "Số cột": len(mart.columns)}
        for mart in warehouse.marts
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("Không có nút init, refresh pipeline hoặc chạy model trên trang này.")
