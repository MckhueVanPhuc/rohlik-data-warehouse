"""Growth dashboard."""

from app.common import ModelState, PageSpec, render_page

SPEC = PageSpec(
    title="Tăng trưởng",
    description="Theo dõi chỉ số lịch sử theo tháng từ mart điều hành đã publish.",
    mart="mart.exec_kpi_month",
    model_states=(
        ModelState("BT8 · Kịch bản tăng trưởng", "Chờ fitted growth và projection kho mới đã được bàn giao."),
    ),
)


def render() -> None:
    render_page(SPEC)
