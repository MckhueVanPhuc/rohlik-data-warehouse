"""Demand and replenishment dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Nhu cầu & Đặt hàng",
    description="Khám phá lịch sử SKU và category để chuẩn bị quyết định bổ sung hàng.",
    mart="mart.category_sku_day",
    model_states=(
        ModelState("BT3 · Lost demand", "Chờ output ước lượng nhu cầu bị mất đã xác minh."),
        ModelState("BT4 / BT6", "Chờ forecast SKU và khuyến nghị replenishment có contract hợp lệ."),
    ),
)


def render() -> None:
    render_page(SPEC)
