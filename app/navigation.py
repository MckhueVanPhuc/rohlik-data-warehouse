"""Stable registry for the ten authenticated dashboard pages (8 trang báo cáo + 2 trang nhập liệu, D01)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st

from app.views import batches, demand, entry, explorer, growth, logistics, ops, overview, pricing, system


@dataclass(frozen=True)
class PageDefinition:
    module: str
    title: str
    icon: str
    url_path: str
    group: str
    renderer: Callable[[], None]
    default: bool = False


PAGE_DEFINITIONS = (
    PageDefinition("overview", "Tổng quan", ":material/space_dashboard:", "tong-quan", "Tổng quan", overview.render, True),
    PageDefinition("ops", "Nhân sự kho", ":material/groups:", "nhan-su-kho", "Nghiệp vụ", ops.render),
    PageDefinition("logistics", "Tài xế", ":material/local_shipping:", "tai-xe", "Nghiệp vụ", logistics.render),
    PageDefinition("demand", "Nhu cầu & Đặt hàng", ":material/inventory_2:", "nhu-cau-dat-hang", "Nghiệp vụ", demand.render),
    PageDefinition("pricing", "Khuyến mãi", ":material/sell:", "khuyen-mai", "Nghiệp vụ", pricing.render),
    PageDefinition("growth", "Tăng trưởng", ":material/trending_up:", "tang-truong", "Nghiệp vụ", growth.render),
    PageDefinition("explorer", "Truy vấn & EDA", ":material/query_stats:", "truy-van-eda", "Dữ liệu & hệ thống", explorer.render),
    PageDefinition("entry", "Nhập dữ liệu", ":material/upload_file:", "nhap-du-lieu", "Dữ liệu & hệ thống", entry.render),
    PageDefinition("batches", "Lịch sử lô / Undo", ":material/history:", "lich-su-lo", "Dữ liệu & hệ thống", batches.render),
    PageDefinition("system", "Vận hành hệ thống", ":material/settings_suggest:", "van-hanh-he-thong", "Dữ liệu & hệ thống", system.render),
)


def build_navigation() -> dict[str, list[st.Page]]:
    """Build grouped ``st.Page`` objects with stable, explicit URL paths."""

    groups: dict[str, list[st.Page]] = {}
    for definition in PAGE_DEFINITIONS:
        page = st.Page(
            definition.renderer,
            title=definition.title,
            icon=definition.icon,
            url_path=definition.url_path,
            default=definition.default,
        )
        groups.setdefault(definition.group, []).append(page)
    return groups
