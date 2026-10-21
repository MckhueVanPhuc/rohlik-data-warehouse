"""Pricing and promotions dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Khuyến mãi",
    description="Phân tích lịch sử giá và khuyến mãi từ reporting mart đã kiểm định.",
    mart="mart.marketing_promo_day",
    model_states=(
        ModelState("BT5 · Promotion lift", "Chờ hiệu ứng uplift đã kiểm định và có lineage."),
        ModelState("BT7 · Markdown", "Chờ khuyến nghị markdown; không sinh đề xuất giả."),
    ),
)


def render() -> None:
    render_page(SPEC)
