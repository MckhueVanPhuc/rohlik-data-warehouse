"""BT8 – Tăng trưởng (ramp-up) kho mới – bản tinh gọn để tích hợp pipeline.

Nguồn phương án: /home/claude/final8/bt8/BT8_final.ipynb (= original_notebook.ipynb).
Giữ nguyên: order_index = trung vị total_orders kho-ngày (ô 2.1) → TB/ngày theo tháng, bỏ tháng < 20 ngày (3.1);
4 đường cong tuyến tính (baseline) / logarit / logistic / Gompertz khớp bằng scipy curve_fit (5.1);
phát hiện gãy cấu trúc (tăng > 20%/tháng sau tháng 12) → chỉ dùng giai đoạn trước; chọn theo MAPE 6 tháng cuối;
khớp lại toàn giai đoạn, thử mô hình kế tiếp nếu không hội tụ, chiếu thêm 12 tháng (5.2–8.1); mốc quy mô (9.1).
Bỏ (chỉ có ở notebook): biểu đồ, model card dạng markdown.
Hai chế độ (D06): mode="models" khớp thẳng đường cong đã chốt cho từng kho mới (frozen["final_models"]) – không chấm
MAPE 6 tháng; mode="evaluate" chấm 4 đường cong, chọn theo MAPE và trả "_params".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BT_ID = "BT8"
REQUIRED_INPUTS = ["sku_sales_daily"]
OPTIONAL_INPUTS: list[str] = []
UPSTREAM: dict[str, tuple[str, str]] = {}
OUTPUTS = ["growth_curves", "growth_projection", "bt8_model_comparison", "bt8_milestones", "run_log"]
FAST_INPUTS = REQUIRED_INPUTS
FAST_OUTPUTS = ["growth_curves", "growth_projection", "bt8_milestones", "run_log"]

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",
    "train_start": "2020-12-05",
    "horizon": 14,                      # không dùng trực tiếp (BT8 theo tháng) – giữ để thống nhất config
    "seed": 42,                         # không có ngẫu nhiên (curve_fit tất định) – giữ để thống nhất
    "n_jobs": 1,
    "warehouses": None,                 # None = tất cả kho có trong sku_sales_daily
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},   # ASSUMED – BT8 không dùng tiền
    "required_inputs": REQUIRED_INPUTS,
    "new_warehouses": ["Munich_1", "Frankfurt_1"],
    "mature_prefix": ["Prague", "Brno", "Budapest"],
    "min_days": 20,                     # bỏ tháng có < 20 ngày dữ liệu
    "n_test_months": 6,                 # MAPE 6 tháng cuối
    "break_jump": 0.20,                 # gãy cấu trúc: tăng > 20%/tháng sau tháng 12
    "break_min_t": 12,
    "proj_months": 12,                  # chiếu thêm 12 tháng
    "maxfev": 20000,
    "curve_order": ["Tuyến tính", "Logarit", "Logistic", "Gompertz"],
    "baseline_model": "Tuyến tính",
    "mode": "evaluate",                 # "models" | "evaluate"
    "frozen": None,                     # {"final_models": {kho: tên đường cong}}
}

INPUT_COLUMNS = {"sku_sales_daily": ["unique_id", "date", "warehouse", "total_orders"]}


def linear(t, a, b):
    return a + b * t


def logt(t, a, b):
    return a + b * np.log1p(t)


def logistic(t, K, r, t0):
    return K / (1 + np.exp(-r * (t - t0)))


def gompertz(t, K, b, c):
    return K * np.exp(-b * np.exp(-c * t))


CURVES = {"Tuyến tính": (linear, [1000, 50]), "Logarit": (logt, [1000, 500]),
          "Logistic": (logistic, [6000, 0.1, 12]), "Gompertz": (gompertz, [6000, 2, 0.05])}


def _mape(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.mean(np.abs(y - p) / y) * 100)


def _log(log, step, rows_in, rows_out, note):
    log.append({"step": step, "rows_in": rows_in, "rows_out": rows_out, "note": note})


def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    import warnings
    from scipy.optimize import curve_fit

    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log: list = []
    _log(log, "config", None, None, f"as_of={cfg['as_of']}, kho mới={cfg['new_warehouses']}, min_days={cfg['min_days']}, "
                                    f"test={cfg['n_test_months']} tháng, break_jump={cfg['break_jump']}, proj={cfg['proj_months']} tháng; "
                                    "artifact_dir không dùng (khớp lại mỗi run)")
    missing = sorted(set(cfg["required_inputs"]) - set(inputs))
    if missing:
        raise ValueError(f"{BT_ID}: thiếu input bắt buộc {missing}")
    s = inputs["sku_sales_daily"]
    if not isinstance(s, pd.DataFrame):
        raise ValueError(f"{BT_ID}: sku_sales_daily phải là DataFrame")
    miss_c = [c for c in INPUT_COLUMNS["sku_sales_daily"] if c not in s.columns]
    if miss_c:
        raise ValueError(f"{BT_ID}: sku_sales_daily thiếu cột {miss_c}")
    s = s[["unique_id", "warehouse", "date", "total_orders"]].copy()
    try:
        s["date"] = pd.to_datetime(s["date"])
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"{BT_ID}: cột date không chuyển được sang ngày: {e}") from e
    if s.duplicated(["unique_id", "date"]).any():
        raise ValueError(f"{BT_ID}: sku_sales_daily trùng khoá unique_id+date")
    t0, as_of = pd.Timestamp(cfg["train_start"]), pd.Timestamp(cfg["as_of"])
    n0 = len(s)
    s = s[(s["date"] >= t0) & (s["date"] <= as_of)]
    _log(log, "cut_sku_sales_daily", n0, len(s), f"giữ {t0.date()} ≤ date ≤ {as_of.date()}")
    _log(log, "null_total_orders", len(s), int(s["total_orders"].notna().sum()), "total_orders NULL bỏ qua khi lấy trung vị kho-ngày")
    if cfg.get("warehouses") is not None:
        lack = sorted(set(cfg["warehouses"]) - set(s["warehouse"]))
        if lack:
            raise ValueError(f"{BT_ID}: sku_sales_daily không có kho {lack}")
        s = s[s["warehouse"].isin(cfg["warehouses"])]
    if s.empty:
        raise ValueError(f"{BT_ID}: sku_sales_daily rỗng sau khi cắt mốc")

    # ---- ô 2.1 + 3.1: order_index kho-ngày → bảng tháng ----
    oi = s.groupby(["warehouse", "date"]).total_orders.median().rename("order_index").reset_index()
    oi["month"] = oi.date.dt.to_period("M").dt.to_timestamp()
    m = oi.groupby(["warehouse", "month"]).agg(orders=("order_index", "mean"), days=("date", "count")).reset_index()
    n_m = len(m)
    m = m[m.days >= int(cfg["min_days"])].drop(columns="days").reset_index(drop=True)
    first = m.groupby("warehouse").month.transform("min")
    m["t"] = ((m.month.dt.year - first.dt.year) * 12 + m.month.dt.month - first.dt.month).astype(float)
    growth_curves = m[["warehouse", "month", "t", "orders"]].sort_values(["warehouse", "month"]).reset_index(drop=True)
    _log(log, "growth_curves", len(oi), len(growth_curves), f"{n_m - len(growth_curves)} kho-tháng < {cfg['min_days']} ngày bị bỏ")
    m = growth_curves

    mature_whs = m[m.warehouse.str.startswith(tuple(cfg["mature_prefix"]))]
    if mature_whs.empty:
        raise ValueError(f"{BT_ID}: không có kho trưởng thành ({cfg['mature_prefix']}) để làm quy mô tham chiếu")
    MATURE = mature_whs.groupby("warehouse").orders.last().mean()
    NEW = [w for w in cfg["new_warehouses"] if w in set(m.warehouse)]
    if not NEW:
        raise ValueError(f"{BT_ID}: không có kho mới nào {cfg['new_warehouses']} trong dữ liệu")
    lack_new = sorted(set(cfg["new_warehouses"]) - set(NEW))
    if lack_new and cfg.get("warehouses") is None:
        raise ValueError(f"{BT_ID}: thiếu dữ liệu kho mới {lack_new}")
    _log(log, "mature_scale", None, None, f"quy mô TB kho trưởng thành (tháng gần nhất) = {MATURE:.1f}; kho mới: {NEW}")

    # ---- ô 5.2–7: gãy cấu trúc, chia 6 tháng cuối, khớp & chấm ----
    rows, used = [], {}
    nt = int(cfg["n_test_months"])
    evaluate = cfg["mode"] == "evaluate"
    frozen_models = (cfg.get("frozen") or {}).get("final_models") or {}
    if not evaluate:
        lack_f = sorted(w for w in NEW if frozen_models.get(w) not in CURVES)
        if lack_f:
            raise ValueError(f"{BT_ID}: chế độ models cần tham số chốt final_models cho kho {lack_f} – chạy `evaluate` trước "
                             "hoặc kiểm tra config/model_params/BT8.json")
    for wh in NEW:
        g = m[m.warehouse == wh].reset_index(drop=True)
        jump = g.orders.pct_change()
        brk = g[(g.t >= cfg["break_min_t"]) & (jump > cfg["break_jump"])]
        note = ""
        if len(brk):
            tb = brk.t.iloc[0]
            note = f"gãy cấu trúc tháng {brk.month.iloc[0]:%m/%Y} (+{jump[brk.index[0]] * 100:.0f}%) – chỉ dùng giai đoạn trước"
            g = g[g.t < tb]
        if len(g) <= nt + 1:
            raise ValueError(f"{BT_ID}: {wh} không đủ tháng để chia {nt} tháng kiểm tra")
        used[wh] = g
        tr, te = g.iloc[:-nt], g.iloc[-nt:]
        for name in (cfg["curve_order"] if evaluate else []):
            f, p0 = CURVES[name]
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    p, _ = curve_fit(f, tr.t, tr.orders, p0=p0, maxfev=int(cfg["maxfev"]))
                    val = round(_mape(te.orders, f(te.t, *p)), 2)
                rows.append({"warehouse": wh, "model": name, "MAPE_6_thang_cuoi_%": val, "note": note})
            except Exception:  # noqa: BLE001 – giữ đúng notebook: không hội tụ → MAPE NaN + ghi chú
                rows.append({"warehouse": wh, "model": name, "MAPE_6_thang_cuoi_%": np.nan,
                             "note": (note + "; " if note else "") + "không hội tụ"})
        _log(log, f"fit_{wh}", len(m[m.warehouse == wh]), len(g), note or "không có gãy cấu trúc")
    comp = pd.DataFrame(rows, columns=["warehouse", "model", "MAPE_6_thang_cuoi_%", "note"])
    comp["MAPE_6_thang_cuoi_%"] = comp["MAPE_6_thang_cuoi_%"].replace([np.inf, -np.inf], np.nan)

    # ---- ô 8.1: đường cong final ----
    proj, FINAL = [], {}
    for wh in NEW:
        xep_hang = (comp[comp.warehouse == wh].dropna(subset=["MAPE_6_thang_cuoi_%"]).sort_values("MAPE_6_thang_cuoi_%", kind="stable").model.tolist()
                    if evaluate else [frozen_models[wh]])
        g = used[wh]
        tt = np.arange(0, m[m.warehouse == wh].t.max() + int(cfg["proj_months"]) + 1)
        best, p = None, None
        for cand in xep_hang:
            f, p0 = CURVES[cand]
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    p, _ = curve_fit(f, g.t, g.orders, p0=p0, maxfev=int(cfg["maxfev"]))
                    if not np.all(np.isfinite(f(tt, *p))):
                        raise RuntimeError("đường chiếu tràn số")
                best = cand
                break
            except Exception:  # noqa: BLE001
                _log(log, f"refit_{wh}", None, None, f"{cand} không hội tụ khi khớp lại → thử mô hình kế tiếp")
        if best is None:
            raise RuntimeError(f"{BT_ID}: {wh}: không mô hình nào khớp được – kiểm tra dữ liệu")
        FINAL[wh] = best
        f = CURVES[best][0]
        proj.append(pd.DataFrame({"warehouse": wh, "t": tt.astype(float), "fitted": f(tt, *p), "model": best}))
    comp["selected"] = [FINAL.get(w) == mdl for w, mdl in zip(comp.warehouse, comp.model)]
    comp["role"] = np.where(comp["model"] == cfg["baseline_model"], "baseline", "candidate")
    comp["note"] = comp["note"].fillna("")
    growth_projection = pd.concat(proj, ignore_index=True)
    _log(log, "final_curves", None, len(growth_projection), "; ".join(f"{w}: {mdl}" for w, mdl in FINAL.items()))

    # ---- ô 9.1: mốc quy mô ----
    moc = []
    for wh in NEW:
        a = m[m.warehouse == wh].set_index("t").orders
        for k in [0, 6, 12, 24]:
            moc.append({"warehouse": wh, "moc": f"thực tế t={k}", "orders": a.get(float(k), np.nan)})
        gp = growth_projection[growth_projection.warehouse == wh]
        moc.append({"warehouse": wh, "moc": f"dự kiến +{cfg['proj_months']} tháng ({FINAL[wh]})", "orders": gp.fitted.iloc[-1]})
    moc = pd.DataFrame(moc)
    moc["pct_of_mature_%"] = (moc.orders / MATURE * 100).round(0)
    moc["orders"] = moc.orders.round(0)
    moc["mature_scale"] = round(float(MATURE), 1)

    run_log = pd.DataFrame(log, columns=["step", "rows_in", "rows_out", "note"])
    run_log["rows_in"] = run_log["rows_in"].astype("Int64"); run_log["rows_out"] = run_log["rows_out"].astype("Int64")
    outputs = {"growth_curves": growth_curves, "growth_projection": growth_projection, "bt8_milestones": moc, "run_log": run_log}
    if evaluate:
        outputs["bt8_model_comparison"] = comp
        outputs["_params"] = {"final_models": dict(FINAL)}
    validate_outputs(outputs, cfg)
    return outputs


def validate_outputs(outputs: dict[str, pd.DataFrame], config: dict) -> None:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    evaluate = cfg.get("mode", "evaluate") == "evaluate"
    for name in (OUTPUTS if evaluate else FAST_OUTPUTS):
        if name not in outputs or not isinstance(outputs[name], pd.DataFrame):
            raise ValueError(f"{BT_ID}: thiếu output '{name}'")
    spec = {"growth_curves": (["warehouse", "month", "t", "orders"], ["warehouse", "month"]),
            "growth_projection": (["warehouse", "t", "fitted", "model"], ["warehouse", "t"]),
            "bt8_model_comparison": (["warehouse", "model", "MAPE_6_thang_cuoi_%", "selected"], ["warehouse", "model"]),
            "bt8_milestones": (["warehouse", "moc", "orders"], ["warehouse", "moc"]),
            "run_log": (["step", "rows_in", "rows_out", "note"], [])}
    for name, (cols, keys) in spec.items():
        if name not in outputs:
            continue
        df = outputs[name]
        miss = [c for c in cols if c not in df.columns]
        if miss:
            raise ValueError(f"{BT_ID}: output '{name}' thiếu cột {miss}")
        if keys and df.duplicated(keys).any():
            raise ValueError(f"{BT_ID}: output '{name}' trùng khoá {keys}")
    gc, gp = outputs["growth_curves"], outputs["growth_projection"]
    if gc[["warehouse", "month", "t", "orders"]].isna().any().any() or (gc[["t", "orders"]] < 0).any().any():
        raise ValueError(f"{BT_ID}: growth_curves có NaN hoặc giá trị âm")
    if pd.to_datetime(gc["month"]).max() > pd.Timestamp(cfg["as_of"]):
        raise ValueError(f"{BT_ID}: growth_curves có tháng sau as_of")
    if cfg.get("warehouses") is not None and set(gc["warehouse"]) != set(cfg["warehouses"]):
        raise ValueError(f"{BT_ID}: growth_curves thiếu kho")
    if gp[["warehouse", "t", "fitted", "model"]].isna().any().any() or (gp["t"] < 0).any() or not np.isfinite(gp["fitted"]).all():
        raise ValueError(f"{BT_ID}: growth_projection có NaN/âm/vô hạn")
    if evaluate:
        sel = outputs["bt8_model_comparison"].groupby("warehouse")["selected"].sum()
        if (sel != 1).any() or set(sel.index) != set(gp["warehouse"]):
            raise ValueError(f"{BT_ID}: mỗi kho mới phải có đúng 1 mô hình selected và có đường chiếu")
    elif gp.groupby("warehouse")["model"].nunique().ne(1).any():
        raise ValueError(f"{BT_ID}: mỗi kho mới phải có đúng 1 đường cong")
