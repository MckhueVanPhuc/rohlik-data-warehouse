"""Pricing and promotions dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Khuyến mãi",
    description="Phân tích lịch sử giá và khuyến mãi từ reporting mart đã kiểm định.",
    mart="mart.marketing_promo_day",
    model_states=(
        ModelState("BT5 · Promotion lift", "Doanh số tăng thêm khi giảm 10/20/30% theo ngành (E2 FE SKU + kiểm soát).",
                   "mart.bt5_promo_effect"),
        ModelState("BT7 · Markdown", "Đề xuất mức giảm giá lô cận hạn 14 ngày tới (mô phỏng theo lô).",
                   "mart.bt7_markdown_day"),
    ),
)


def render() -> None:
    render_page(SPEC)
