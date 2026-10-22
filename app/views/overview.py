"""Executive overview backed by the sales-orders mart when available."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Tổng quan",
    description="Theo dõi dữ liệu đơn hàng lịch sử đã được Data Engineering publish và kiểm định.",
    mart="mart.sales_orders_day",
    model_states=(
        ModelState("Triển vọng · BT1 dự báo đơn 14 ngày",
                   "Số đơn P50/P90 từng kho 16/03 → 29/03/2024 (LightGBM quantile, P90 đã hiệu chỉnh).",
                   "mart.bt1_forecast_orders"),
        ModelState("BT8 · Tăng trưởng kho mới", "Đường cong ramp-up Munich_1, Frankfurt_1 + chiếu 12 tháng.",
                   "mart.bt8_growth_month"),
    ),
)


def render() -> None:
    render_page(SPEC)
