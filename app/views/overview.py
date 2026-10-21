"""Executive overview backed by the sales-orders mart when available."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Tổng quan",
    description="Theo dõi dữ liệu đơn hàng lịch sử đã được Data Engineering publish và kiểm định.",
    mart="mart.sales_orders_day",
    model_states=(
        ModelState("Triển vọng", "Forecast P50/P90 chỉ xuất hiện sau khi đầu ra mô hình hợp lệ được bàn giao."),
    ),
)


def render() -> None:
    render_page(SPEC)
