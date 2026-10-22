"""Logistics capacity dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Tài xế",
    description="Theo dõi dữ liệu vận hành liên quan năng lực giao hàng theo warehouse và thời gian.",
    mart="mart.ops_warehouse_day",
    model_states=(
        ModelState("BT2 · Kế hoạch tài xế", "Số ca tài xế cần mỗi ngày (theo số đơn P90 + dự phòng lễ).",
                   "mart.bt2_staff_driver_plan"),
    ),
)


def render() -> None:
    render_page(SPEC)
