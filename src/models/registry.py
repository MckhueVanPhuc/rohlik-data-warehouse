"""Danh mục 8 mô hình BT1–BT8: thứ tự chạy (DAG), bảng kết quả, nguồn input (D06 đã duyệt 22/10/2026)."""

from __future__ import annotations

from dataclasses import dataclass, field

# Thứ tự chạy theo phụ thuộc: BT1 → BT3 → BT5 → BT8 → BT2 → BT4 → BT6 → BT7
DAG = ("BT1", "BT3", "BT5", "BT8", "BT2", "BT4", "BT6", "BT7")


@dataclass(frozen=True)
class ModelSpec:
    bt_id: str
    title: str
    module: str
    model_version: str
    pred_tables: tuple[str, ...]          # kết quả nghiệp vụ → schema pred (ghi mỗi lần models/evaluate)
    eval_tables: tuple[str, ...]          # backtest / so sánh → schema pred_eval (chỉ khi evaluate)
    n_jobs: int | None = None             # None = theo settings.models.n_jobs
    extra_config: dict = field(default_factory=dict)


SPECS: dict[str, ModelSpec] = {
    "BT1": ModelSpec("BT1", "Dự báo số đơn 14 ngày (P50/P90)", "src.models.bt1", "BT1-final-tinhgon-v1",
                     ("fc_orders",), ("bt1_backtest", "bt1_model_comparison")),
    "BT2": ModelSpec("BT2", "Xếp ca nhân viên kho + ca tài xế", "src.models.bt2", "BT2-final-tinhgon-v1",
                     ("staff_plan", "driver_plan"),
                     ("bt2_policy_comparison", "bt2_policy_by_warehouse", "bt2_sensitivity", "bt2_solve_log"),
                     n_jobs=1),                                    # CBC 1 luồng = kết quả tất định như notebook
    "BT3": ModelSpec("BT3", "Nhu cầu bị mất do hết hàng (lost sales)", "src.models.bt3", "BT3-M4-tweedie-tinhgon-v1",
                     ("lost_sales", "lost_sales_summary", "lost_sales_monthly"), ("bt3_model_comparison",)),
    "BT4": ModelSpec("BT4", "Dự báo nhu cầu SKU 14 ngày (P20…P90)", "src.models.bt4", "BT4-final-tinhgon-v1",
                     ("fc_sku",), ("bt4_backtest", "bt4_quantile_ratios", "bt4_model_comparison")),
    "BT5": ModelSpec("BT5", "Hiệu ứng giảm giá (E2 FE SKU + kiểm soát)", "src.models.bt5", "BT5-E2-tinhgon-v1",
                     ("promo_effect", "promo_type_effect"), ("bt5_method_comparison",)),
    "BT6": ModelSpec("BT6", "Lượng đặt hàng (newsvendor)", "src.models.bt6", "BT6-final-tinhgon-v1",
                     ("replenishment",),
                     ("bt6_backtest", "bt6_policy_comparison", "bt6_policy_by_warehouse", "bt6_sensitivity")),
    "BT7": ModelSpec("BT7", "Giảm giá lô cận hạn (markdown)", "src.models.bt7", "BT7-final-tinhgon-v1",
                     ("markdown_plan", "markdown_summary"),
                     ("bt7_policy_comparison", "bt7_policy_by_warehouse", "bt7_sensitivity")),
    "BT8": ModelSpec("BT8", "Đường cong tăng trưởng kho mới", "src.models.bt8", "BT8-final-tinhgon-v1",
                     ("growth_curves", "growth_projection", "bt8_milestones"), ("bt8_model_comparison",)),
}

# input do BT khác sinh ra → (BT nguồn, schema, bảng)
UPSTREAM_TABLES: dict[str, tuple[str, str, str]] = {
    "fc_orders": ("BT1", "pred", "fc_orders"),
    "bt1_backtest": ("BT1", "pred_eval", "bt1_backtest"),
    "lost_sales": ("BT3", "pred", "lost_sales"),
    "promo_effect": ("BT5", "pred", "promo_effect"),
    "fc_sku": ("BT4", "pred", "fc_sku"),
    "bt4_backtest": ("BT4", "pred_eval", "bt4_backtest"),
    "replenishment": ("BT6", "pred", "replenishment"),
    "bt6_backtest": ("BT6", "pred_eval", "bt6_backtest"),
}

# BT nào cần chạy lại khi 1 BT thay đổi (dùng để báo người dùng)
def downstream(bt_id: str) -> list[str]:
    import importlib
    out: list[str] = []
    for other in DAG:
        mod = importlib.import_module(SPECS[other].module)
        needs = set(getattr(mod, "REQUIRED_INPUTS", [])) | set(getattr(mod, "FAST_INPUTS", []))
        if any(UPSTREAM_TABLES.get(n, ("",))[0] == bt_id for n in needs):
            out.append(other)
    return out
