"""Warehouse operations dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Nhân sự kho",
    description="Phân tích vận hành kho theo dữ liệu lịch sử đã được publish.",
    mart="mart.ops_warehouse_day",
    model_states=(
        ModelState("BT1 · Dự báo đơn", "Chưa có forecast đơn hàng đã được kiểm định."),
        ModelState("BT2 · Kế hoạch nhân sự", "Chờ kế hoạch staffing và chi phí có lineage mô hình."),
    ),
)


def render() -> None:
    render_page(SPEC)
