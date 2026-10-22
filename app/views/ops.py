"""Warehouse operations dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Nhân sự kho",
    description="Phân tích vận hành kho theo dữ liệu lịch sử đã được publish.",
    mart="mart.ops_warehouse_day",
    model_states=(
        ModelState("BT1 · Dự báo đơn", "Số đơn P50/P90 14 ngày tới – đầu vào lập ca.", "mart.bt1_forecast_orders"),
        ModelState("BT2 · Kế hoạch nhân sự", "Số người ca sáng/chiều và chi phí lương theo phương án MIP cải tiến.",
                   "mart.bt2_staff_driver_plan"),
    ),
)


def render() -> None:
    render_page(SPEC)
