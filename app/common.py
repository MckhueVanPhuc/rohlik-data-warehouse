"""Shared dashboard UI primitives for the admin-only Streamlit application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from html import escape
import os
from typing import Sequence

import pandas as pd
import streamlit as st

from app.services.reporting import (
    BASE_MARTS, MODEL_MARTS, MartInfo, QueryResult, ReportingError, ReportingService, WarehouseInfo,
)


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
    mart: str | None = None          # mart kết quả mô hình (D05); chưa có → PENDING_MODEL


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
    DataStatus.REFRESH_REQUIRED: ("warning", "Có lô nhập liệu chưa vào báo cáo – cần cập nhật kho"),
    DataStatus.SOURCES_READY: ("success", "Nguồn sẵn sàng"),
    DataStatus.LANDING_READY: ("success", "Landing sẵn sàng"),
    DataStatus.MART_READY: ("success", "Mart sẵn sàng"),
}


def apply_app_styles() -> None:
    """Apply the Modern Commerce Analytics light visual system."""
    from app.ui.styles import APP_CSS

    st.markdown(APP_CSS, unsafe_allow_html=True)


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
        warehouse_label = "Chưa có warehouse"
        badge_variant = "warning"
        badge_text = "CHƯA KHỞI TẠO"
    elif warehouse.ready_mart_count == len(BASE_MARTS):
        warehouse_label = f"{len(BASE_MARTS)}/{len(BASE_MARTS)} reporting marts"
        badge_variant = "success"
        badge_text = "SẴN SÀNG"
    else:
        warehouse_label = f"{warehouse.ready_mart_count}/{len(BASE_MARTS)} reporting marts"
        badge_variant = "neutral"
        badge_text = f"{warehouse.ready_mart_count}/{len(BASE_MARTS)}"
    model_label = f"{warehouse.ready_model_mart_count}/{len(MODEL_MARTS)} mart mô hình"

    st.sidebar.markdown(
        f"""
        <div class="rdh-brand">
          <div class="rdh-brand__header">
            <div class="rdh-brand__name">Rohlik Decision Hub</div>
            <div class="rdh-mode">{network_mode()}</div>
          </div>
          <div class="rdh-brand__meta">Executive BI & Analytics · Desktop-first</div>
        </div>
        <div class="rdh-sidebar-card">
          <div class="rdh-sidebar-card__title">Kho dữ liệu DuckDB</div>
          <div class="rdh-sidebar-card__item">
            <span>📊 {warehouse_label}</span>
            <span class="rdh-status rdh-status--{badge_variant}" style="margin-left: auto;">{badge_text}</span>
          </div>
          <div class="rdh-sidebar-card__item" style="margin-top: 0.35rem;">
            <span>🤖 {model_label}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    pending = _pending_batches()
    if pending:
        st.sidebar.warning(f"⏳ {pending} lô nhập liệu/undo chờ cập nhật kho")
    st.sidebar.caption(f"Tài khoản quản trị: **{username}**")
    st.sidebar.divider()



def _pending_batches() -> int:
    try:
        from app.services.operations import OperationsService
        return OperationsService().pending_refresh()
    except Exception:  # noqa: BLE001 – sidebar không được làm hỏng trang
        return 0


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


def _model_states(states: Sequence[ModelState], service: ReportingService | None = None,
                  warehouse: WarehouseInfo | None = None) -> None:
    """Khối "Đầu ra mô hình": mart kết quả có sẵn → DATA_READY + bảng/biểu đồ; chưa có → PENDING_MODEL."""
    if not states:
        return
    st.subheader("Đầu ra mô hình")
    ready = {m.name: m for m in (warehouse.marts if warehouse and warehouse.exists else ()) if m.exists}
    rows = "".join(
            f'<div class="rdh-model" role="listitem"><div class="rdh-model__title">{escape(state.title)}</div>'
            f'<div class="rdh-model__copy">{escape(state.detail)}</div>'
            f'<div>{status_badge(DataStatus.DATA_READY if state.mart in ready else DataStatus.PENDING_MODEL)}</div></div>'
            for state in states
    )
    st.markdown(
        f'<div role="list" aria-label="Trạng thái đầu ra mô hình">{rows}</div>',
        unsafe_allow_html=True,
    )
    if service is None:
        return
    for state in states:
        if state.mart in ready:
            with st.expander(f"{state.title} – xem kết quả ({state.mart})", expanded=False):
                try:
                    _render_ready_mart(service, ready[state.mart], key_prefix=state.mart.replace(".", "-"))
                except ReportingError as exc:
                    _readiness(DataStatus.WAREHOUSE_NOT_READY, str(exc))
        elif state.mart:
            st.caption(f"{state.title}: chưa có {state.mart} – chạy `python -m pipeline.run models` "
                       "(hoặc `import-outputs`) rồi tải lại trang.")


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
    _model_states(spec.model_states, service, warehouse)


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
        _readiness(DataStatus.DATA_READY, f"{len(ready)}/{len(warehouse.marts)} mart (nền + kết quả mô hình) sẵn sàng cho EDA allowlisted.")
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
        "Theo dõi kho, kiểm định chất lượng dữ liệu (DQ), các lần chạy pipeline và 8 mô hình.",
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
        _readiness(DataStatus.WAREHOUSE_NOT_READY, "Không tìm thấy warehouse; chạy `python -m pipeline.run init` trên Terminal.")
        return
    from app.services.operations import OperationsService
    ops = OperationsService()
    dq = ops.quality_report()
    if not dq.empty and (dq["status"] == "FAIL").any():
        _readiness(DataStatus.DQ_FAILED, "Lần refresh gần nhất có kiểm tra ERROR – dữ liệu báo cáo vẫn là bản trước đó.")
    elif ops.pending_refresh():
        _readiness(DataStatus.REFRESH_REQUIRED, f"{ops.pending_refresh()} lô nhập liệu/undo chưa vào báo cáo – bấm "
                   "\"Cập nhật kho\" ở trang Nhập dữ liệu.")
    elif warehouse.ready_mart_count == len(BASE_MARTS):
        _readiness(DataStatus.DATA_READY, "Tất cả reporting marts mục tiêu đang sẵn sàng.")
    else:
        _readiness(
            DataStatus.TABLE_NOT_AVAILABLE,
            f"{warehouse.ready_mart_count}/{len(BASE_MARTS)} reporting marts sẵn sàng – chạy `python -m pipeline.run refresh`.",
        )
    rows = [
        {"Mart": mart.name, "Loại": "nền" if mart.name in BASE_MARTS else "kết quả mô hình",
         "Trạng thái": "DATA_READY" if mart.exists else ("PENDING_MODEL" if mart.name in MODEL_MARTS else "TABLE_NOT_AVAILABLE"),
         "Số cột": len(mart.columns)}
        for mart in warehouse.marts
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.subheader("Kiểm định chất lượng – lần refresh gần nhất")
    if dq.empty:
        st.info("Chưa có báo cáo DQ.")
    else:
        m = st.columns(3)
        m[0].metric("PASS", int((dq["status"] == "PASS").sum()))
        m[1].metric("WARN", int((dq["status"] == "WARN").sum()))
        m[2].metric("FAIL", int((dq["status"] == "FAIL").sum()))
        st.dataframe(dq, use_container_width=True, hide_index=True)
    st.subheader("8 mô hình – lần chạy gần nhất")
    mr = ops.model_runs()
    st.dataframe(mr, use_container_width=True, hide_index=True) if not mr.empty else st.info("Chưa chạy mô hình.")
    st.subheader("Lịch sử chạy pipeline")
    pr = ops.pipeline_runs()
    st.dataframe(pr, use_container_width=True, hide_index=True) if not pr.empty else st.info("Chưa có lần chạy nào.")
    st.caption("Chạy mô hình bằng lệnh `python -m pipeline.run models` trên Terminal (không chạy từ giao diện).")
