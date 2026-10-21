"""Logistics capacity dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Tài xế",
    description="Theo dõi dữ liệu vận hành liên quan năng lực giao hàng theo warehouse và thời gian.",
    mart="mart.ops_warehouse_day",
    model_states=(
        ModelState("BT2 · Kế hoạch tài xế", "Chưa có output kế hoạch ca tài xế đã được kiểm định."),
    ),
)


def render() -> None:
    render_page(SPEC)
