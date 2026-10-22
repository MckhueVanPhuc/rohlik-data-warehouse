"""Demand and replenishment dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Nhu cầu & Đặt hàng",
    description="Khám phá lịch sử SKU và category để chuẩn bị quyết định bổ sung hàng.",
    mart="mart.category_sku_day",
    model_states=(
        ModelState("BT3 · Lost demand", "Nhu cầu bị mất do hết hàng theo kho × ngành × ngày (M4 LightGBM Tweedie).",
                   "mart.bt3_lost_sales_day"),
        ModelState("BT4 / BT6", "Dự báo nhu cầu SKU P50/P90 14 ngày + lượng đặt hàng newsvendor, gộp theo ngành.",
                   "mart.bt4_bt6_sku_plan_day"),
    ),
)


def render() -> None:
    render_page(SPEC)
