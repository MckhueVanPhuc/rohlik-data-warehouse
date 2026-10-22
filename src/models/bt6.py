"""BT6 – Lượng đặt hàng hàng tươi (newsvendor) – bản tinh gọn để tích hợp pipeline, 7 kho.

Thuật toán giữ nguyên notebook final (final8/bt6/BT6_final.ipynb):
  Cu = giá × (1 − cost_ratio + goodwill); Co = giá × (cost_ratio + waste_handling_cost_ratio); CR = Cu/(Cu+Co)
  lượng đặt newsvendor = nội suy tuyến tính phân vị CR trên P20…P90 của BT4 (ngoài [0,2;0,9] → P20/P90).
  So 3 chính sách trên kỳ kiểm tra (as_of−13 → as_of), chấm bằng nhu cầu đã sửa của BT3 (est_demand):
  quy tắc cũ (TB bán 28 ngày trước kỳ × 1,1) · P50 · newsvendor → chính sách thiệt hại nhỏ nhất lập kế hoạch 14 ngày.
7 kho: Cu/Co tính theo NỘI TỆ từng SKU (giá nội tệ), quy đổi EUR (fx_eur) trước khi cộng nhiều kho.
KHÔNG có inventory snapshot thật: lượng đặt là lượng nhập/ngày (giả định hàng thừa huỷ trong ngày); không tạo tồn kho.
Hai chế độ (D06): mode="models" lập kế hoạch 14 ngày bằng chính sách đã chốt (frozen["policy"], mặc định Newsvendor) –
không cần bt4_backtest; mode="evaluate" chấm 3 chính sách trên kỳ kiểm tra + độ nhạy và trả "_params".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BT_ID = "BT6"
REQUIRED_INPUTS = ["bt4_backtest", "fc_sku", "lost_sales", "cost_params"]
OPTIONAL_INPUTS: list[str] = []
UPSTREAM = {"bt4_backtest": ("BT4", "bt4_backtest"), "fc_sku": ("BT4", "fc_sku"), "lost_sales": ("BT3", "lost_sales")}
OUTPUTS = ["replenishment", "bt6_backtest", "bt6_policy_comparison", "bt6_policy_by_warehouse", "bt6_sensitivity", "run_log"]
FAST_INPUTS = ["fc_sku", "lost_sales", "cost_params"]
FAST_OUTPUTS = ["replenishment", "run_log"]

QC = [f"p{q}" for q in range(20, 100, 10)]
POL = ["Quy tắc cũ: TB 28 ngày x 1,1", "Đặt theo P50 (BT4)", "Newsvendor: phân vị = tỷ lệ tới hạn"]
POL_SHORT = {POL[0]: "Quy tắc cũ", POL[1]: "P50", POL[2]: "Newsvendor"}

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",
    "train_start": "2020-12-05",
    "horizon": 14,
    "seed": 42,                       # không có thành phần ngẫu nhiên; giữ cho thống nhất
    "warehouses": None,               # None = mọi kho có trong input
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},   # ASSUMED
    "currency_by_warehouse": {"Prague_1": "CZK", "Prague_2": "CZK", "Prague_3": "CZK", "Brno_1": "CZK",
                              "Budapest_1": "HUF", "Munich_1": "EUR", "Frankfurt_1": "EUR"},
    "goodwill": 0.30,                 # chi phí uy tín khi thiếu (tỷ lệ giá) – ASSUMED
    "old_rule_window_days": 28,
    "old_rule_multiplier": 1.1,
    "sensitivity_goodwill": [0.1, 0.3, 0.6, 1.0],
    "required_inputs": REQUIRED_INPUTS,
    "mode": "evaluate",               # "models" | "evaluate"
    "frozen": None,                   # {"policy": tên chính sách trong POL}
}

REQ_COLS = {
    "bt4_backtest": ["unique_id", "date", "warehouse", "L1", "actual"] + QC,
    "fc_sku": ["unique_id", "date", "warehouse", "L1", "final_price"] + QC,
    "lost_sales": ["unique_id", "date", "warehouse", "L1", "sales", "final_price", "est_demand"],
    "cost_params": ["L1_category_name_en", "cost_ratio", "shelf_life_days", "waste_handling_cost_ratio"],
}


# ---------------------------------------------------------------- tiện ích
def _cfg(config: dict | None) -> dict:
    c = {**DEFAULT_CONFIG, **(config or {})}
    c["as_of"], c["train_start"] = pd.Timestamp(c["as_of"]), pd.Timestamp(c["train_start"])
    return c


def _log(log: list, step: str, rin: int, rout: int, note: str = "") -> None:
    log.append({"step": step, "rows_in": int(rin), "rows_out": int(rout), "note": note})


def _check_inputs(inputs: dict, cfg: dict) -> dict[str, pd.DataFrame]:
    missing = sorted(set(cfg["required_inputs"]) - set(k for k, v in inputs.items() if v is not None))
    if missing:
        raise ValueError(f"{BT_ID}: thiếu input bắt buộc {missing}")
    out = {}
    for name, cols in REQ_COLS.items():
        if name not in cfg["required_inputs"]:
            continue
        df = inputs[name]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{BT_ID}: input '{name}' phải là pandas.DataFrame")
        miss = [c for c in cols if c not in df.columns]
        if miss:
            raise ValueError(f"{BT_ID}: input '{name}' thiếu cột {miss}")
        df = df.copy()
        if "date" in df.columns:
            try:
                df["date"] = pd.to_datetime(df["date"])
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"{BT_ID}: cột date của '{name}' không chuyển được sang ngày: {e}") from e
        out[name] = df
    return out


def _currency(df: pd.DataFrame, cfg: dict, name: str) -> pd.Series:
    """Nội tệ theo kho (config); nếu input có cột currency thì phải khớp, lệch → ValueError."""
    cmap = cfg["currency_by_warehouse"]
    unk = sorted(set(df.warehouse) - set(cmap))
    if unk:
        raise ValueError(f"{BT_ID}: kho {unk} trong '{name}' không có trong currency_by_warehouse")
    cur = df.warehouse.map(cmap)
    if "currency" in df.columns:
        bad = df["currency"].notna() & (df["currency"] != cur)
        if bad.any():
            raise ValueError(f"{BT_ID}: cột currency của '{name}' lệch với currency_by_warehouse ({int(bad.sum())} dòng)")
    nofx = sorted(set(cur) - set(cfg["fx_eur"]))
    if nofx:
        raise ValueError(f"{BT_ID}: thiếu tỷ giá fx_eur cho {nofx}")
    return cur


def critical_ratio(d: pd.DataFrame, cost: pd.DataFrame, goodwill: float) -> pd.DataFrame:
    """Gắn tham số ngành, tính Cu, Co, CR (nội tệ, theo giá của dòng)."""
    d = d.drop(columns=[c for c in ["cost_ratio", "shelf_life_days", "waste_handling_cost_ratio", "Cu", "Co", "CR"] if c in d.columns])
    d = d.merge(cost, on="L1", how="left")
    d["Cu"] = d.final_price * (1 - d.cost_ratio + goodwill)
    d["Co"] = d.final_price * (d.cost_ratio + d.waste_handling_cost_ratio)
    d["CR"] = (d.Cu / (d.Cu + d.Co)).fillna(0.5)          # giá = 0 → 0/0 → trung vị
    return d


def qty_at(d: pd.DataFrame) -> np.ndarray:
    """Nhu cầu tại phân vị CR, nội suy tuyến tính giữa P20…P90 (ngoài khoảng → P20/P90)."""
    xs = np.array([int(c[1:]) / 100 for c in QC])
    return np.array([np.interp(cr, xs, row) for cr, row in zip(d.CR.values, d[QC].values)])


def score(d: pd.DataFrame, avg28: pd.Series, cfg: dict) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Chấm 3 chính sách bằng nhu cầu thật: thiệt hại = thiếu × Cu + thừa × Co (nội tệ/dòng → EUR khi cộng)."""
    pol = {POL[0]: d.unique_id.map(avg28).fillna(d.p50) * cfg["old_rule_multiplier"],
           POL[1]: d.p50,
           POL[2]: pd.Series(qty_at(d), index=d.index)}
    fx = d.currency.map(cfg["fx_eur"])
    rows, qs, by_wh = [], {}, []
    for name, q in pol.items():
        q = np.round(q.clip(lower=0))
        short = np.clip(d.est_demand - q, 0, None)
        over = np.clip(q - d.est_demand, 0, None)
        cost = short * d.Cu + over * d.Co                   # nội tệ từng dòng
        rows.append({"policy": name, "order_units": q.sum(), "short_units": short.sum(), "waste_units": over.sum(),
                     "fill_rate_%": (1 - short.sum() / d.est_demand.sum()) * 100,
                     "waste_%_of_order": over.sum() / max(q.sum(), 1) * 100,
                     "cost_eur": (cost * fx).sum()})
        w = pd.DataFrame({"warehouse": d.warehouse, "currency": d.currency, "q": q, "short": short, "over": over,
                          "dem": d.est_demand, "cost": cost, "cost_eur": cost * fx})
        g = w.groupby(["warehouse", "currency"], sort=True).agg(order_units=("q", "sum"), short_units=("short", "sum"),
                                                               waste_units=("over", "sum"), demand=("dem", "sum"),
                                                               cost=("cost", "sum"), cost_eur=("cost_eur", "sum")).reset_index()
        g["fill_rate_%"] = (1 - g.short_units / g.demand) * 100
        g.insert(2, "policy", name)
        by_wh.append(g.drop(columns="demand"))
        qs[name] = q
    c = pd.DataFrame(rows)
    c["vs_rule_%"] = (c.cost_eur / c.cost_eur.iloc[0] - 1) * 100
    return c.round(1), qs, pd.concat(by_wh, ignore_index=True)


# ---------------------------------------------------------------- mô hình
def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    cfg = _cfg(config)
    evaluate = cfg["mode"] == "evaluate"
    if not evaluate:
        cfg["required_inputs"] = FAST_INPUTS
        pol_frozen = (cfg.get("frozen") or {}).get("policy")
        if pol_frozen not in POL:
            raise ValueError(f"{BT_ID}: chế độ models cần tham số chốt policy ∈ {POL} – chạy `evaluate` trước "
                             "hoặc kiểm tra config/model_params/BT6.json")
    log: list[dict] = []
    x = _check_inputs(inputs, cfg)
    as_of, t0, H = cfg["as_of"], cfg["train_start"], int(cfg["horizon"])
    test_start = as_of - pd.Timedelta(days=H - 1)
    fc_dates = pd.date_range(as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H), freq="D")
    _log(log, "config", 0, 0, f"as_of={as_of:%Y-%m-%d}; train_start={t0:%Y-%m-%d}; horizon={H}; goodwill={cfg['goodwill']}; "
                              f"fx_eur={cfg['fx_eur']}; no_inventory_snapshot=True")

    # 1. cắt mốc chống rò rỉ
    ls, fc = x["lost_sales"], x["fc_sku"]
    bt4 = x["bt4_backtest"] if evaluate else fc.iloc[0:0].assign(actual=0.0)
    n = len(ls); ls = ls[(ls.date >= t0) & (ls.date <= as_of)]
    _log(log, "cut lost_sales [train_start, as_of]", n, len(ls))
    if evaluate:
        n = len(bt4); bt4 = bt4[(bt4.date >= test_start) & (bt4.date <= as_of)]
        _log(log, "cut bt4_backtest [as_of-13, as_of]", n, len(bt4))
    n = len(fc); fc = fc[fc.date.isin(fc_dates)]
    _log(log, "cut fc_sku (as_of, as_of+h]", n, len(fc))

    # 2. phạm vi kho
    whs = cfg["warehouses"]
    if whs is None:
        whs = sorted(set(bt4.warehouse) if evaluate else set(fc.warehouse))
    whs = list(whs)
    for name, df in [("bt4_backtest", bt4), ("fc_sku", fc), ("lost_sales", ls)] if evaluate else [("fc_sku", fc), ("lost_sales", ls)]:
        lack = sorted(set(whs) - set(df.warehouse))
        if lack:
            raise ValueError(f"{BT_ID}: input '{name}' thiếu kho {lack} trong khoảng ngày cần dùng")
    ls, bt4, fc = (df[df.warehouse.isin(whs)] for df in (ls, bt4, fc))
    if (evaluate and not len(bt4)) or not len(fc):
        raise ValueError(f"{BT_ID}: bt4_backtest hoặc fc_sku rỗng sau khi cắt mốc")

    # 3. chuẩn hoá: bỏ cột trùng tên, bỏ trùng khoá, tiền tệ
    bt4 = bt4.drop(columns=[c for c in ["final_price", "est_demand", "currency"] if c in bt4.columns])
    for name in ("bt4", "fc"):
        df = bt4 if name == "bt4" else fc
        dup = int(df.duplicated(["unique_id", "date"]).sum())
        if dup:
            _log(log, f"drop duplicate keys {name}", len(df), len(df) - dup, "giữ dòng đầu")
    bt4 = bt4.drop_duplicates(["unique_id", "date"]).reset_index(drop=True)
    fc = fc.drop_duplicates(["unique_id", "date"]).reset_index(drop=True)
    ls = ls.assign(currency=_currency(ls, cfg, "lost_sales"))
    fc = fc.assign(currency=_currency(fc, cfg, "fc_sku"))
    bt4 = bt4.assign(currency=_currency(bt4, cfg, "bt4_backtest"))
    _log(log, "null policy lost_sales.sales", len(ls), int(ls.sales.isna().sum()),
         "rows_out = số dòng sales NULL: bỏ qua khi tính TB 28 ngày (không điền 0)")

    cost = x["cost_params"].rename(columns={"L1_category_name_en": "L1"})[["L1", "cost_ratio", "shelf_life_days", "waste_handling_cost_ratio"]]
    miss_l1 = sorted((set(bt4.L1) | set(fc.L1)) - set(cost.L1))
    if miss_l1:
        tb = cost.mean(numeric_only=True).to_dict()
        cost = pd.concat([cost, pd.DataFrame([{"L1": l, **tb} for l in miss_l1])], ignore_index=True)
        _log(log, "cost_params missing L1", len(cost) - len(miss_l1), len(cost), f"CẢNH BÁO: {miss_l1} dùng tham số trung bình")

    if evaluate:
        # 4. kỳ kiểm tra
        gia_gan_nhat = ls.sort_values("date").groupby("unique_id").final_price.last()
        d0 = bt4.merge(ls[["unique_id", "date", "final_price", "est_demand"]], on=["unique_id", "date"], how="left")
        miss = 1 - d0.est_demand.notna().mean() if len(d0) else 0
        n_px = int(d0.final_price.isna().sum()); n_dem = int(d0.est_demand.isna().sum())
        d0["final_price"] = d0.final_price.fillna(d0.unique_id.map(gia_gan_nhat))
        d0["est_demand"] = d0.est_demand.fillna(d0.actual)
        bo = d0.final_price.isna() | d0.est_demand.isna()
        _log(log, "backtest join bt4+lost_sales", len(d0), int((~bo).sum()),
             f"giá thiếu bù giá gần nhất: {n_px}; est_demand thiếu → actual: {n_dem}; bỏ dòng vẫn thiếu: {int(bo.sum())}; "
             f"tỷ lệ không có BT3: {miss:.1%}" + (" CẢNH BÁO >5%" if miss > 0.05 else ""))
        d0 = d0[~bo].reset_index(drop=True)
        d = critical_ratio(d0, cost, cfg["goodwill"])
        W = int(cfg["old_rule_window_days"])
        hist = ls[(ls.date < test_start) & (ls.date >= test_start - pd.Timedelta(days=W))]
        avg28 = hist.groupby("unique_id").sales.mean()

        comp, QTY, by_wh = score(d, avg28, cfg)
        best = comp.sort_values("cost_eur", kind="stable").policy.iloc[0]
        comp["selected"] = comp.policy == best
        comp["cost"] = comp["cost_eur"]                          # alias tên hợp đồng QUY_UOC; đơn vị EUR
        comp["currency"] = "EUR"
        by_wh["selected"] = by_wh.policy == best
        _log(log, "policy selection (EUR, all warehouses)", len(comp), 1, f"best={best}")

        # 5. độ nhạy goodwill
        sens = []
        for gw in cfg["sensitivity_goodwill"]:
            dd = critical_ratio(d0, cost, gw)
            c, _, _ = score(dd, avg28, cfg)
            sens += [{"goodwill": gw, "CR_TB": round(dd.CR.mean(), 3), **r} for r in c[["policy", "cost_eur", "vs_rule_%"]].to_dict("records")]
        sens = pd.DataFrame(sens)
        sens["best"] = sens.groupby("goodwill").cost_eur.transform("min") == sens.cost_eur
    else:
        best = pol_frozen
        W = int(cfg["old_rule_window_days"])
        gia_gan_nhat = ls.sort_values("date").groupby("unique_id").final_price.last()
        _log(log, "policy frozen", 0, 1, f"best={best}")

    # 6. kế hoạch 14 ngày
    f = fc.copy()
    n_px = int(f.final_price.isna().sum())
    f["final_price"] = f.final_price.fillna(f.unique_id.map(gia_gan_nhat))
    f = critical_ratio(f, cost, cfg["goodwill"])
    avg28_fc = ls[ls.date > as_of - pd.Timedelta(days=W)].groupby("unique_id").sales.mean()
    if best == POL[2]:
        q = qty_at(f)
    elif best == POL[1]:
        q = f.p50.values
    else:
        q = (f.unique_id.map(avg28_fc).fillna(f.p50) * cfg["old_rule_multiplier"]).values
    q = np.asarray(q, float)
    n_nan = int(np.isnan(q).sum())
    f["order_qty"] = np.round(np.clip(np.nan_to_num(q, nan=0.0), 0, None))
    f["policy"] = POL_SHORT[best]
    _log(log, "replenishment plan", len(fc), len(f), f"policy={POL_SHORT[best]}; giá thiếu bù: {n_px}; order_qty NaN→0: {n_nan}")
    rep = f[["unique_id", "date", "warehouse", "L1", "final_price", "currency", "CR", "p50", "p90", "order_qty", "policy"]] \
        .sort_values(["unique_id", "date"]).reset_index(drop=True)

    out = {"replenishment": rep, "run_log": pd.DataFrame(log)}
    if evaluate:
        bt6_backtest = d[["unique_id", "date", "warehouse", "L1", "CR", "actual", "est_demand", "final_price", "currency"] + QC] \
            .assign(order_qty=QTY[best].values, policy=best).sort_values(["unique_id", "date"]).reset_index(drop=True)
        by_wh = by_wh.round(1)
        out.update({"bt6_backtest": bt6_backtest,
                    "bt6_policy_comparison": comp[["policy", "order_units", "short_units", "waste_units", "fill_rate_%",
                                                   "waste_%_of_order", "cost_eur", "cost", "currency", "vs_rule_%", "selected"]],
                    "bt6_policy_by_warehouse": by_wh, "bt6_sensitivity": sens})
        out["_params"] = {"policy": best, "goodwill": float(cfg["goodwill"])}
    validate_outputs(out, {**cfg, "warehouses": whs})
    return out


# ---------------------------------------------------------------- kiểm tra hợp đồng
def validate_outputs(outputs: dict[str, pd.DataFrame], config: dict) -> None:
    cfg = _cfg(config)
    as_of, H = cfg["as_of"], int(cfg["horizon"])
    spec = {
        "replenishment": (["unique_id", "date", "warehouse", "L1", "final_price", "currency", "p50", "order_qty", "policy"],
                          ["unique_id", "date"], ["order_qty", "p50", "final_price"], (as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H))),
        "bt6_backtest": (["unique_id", "date", "warehouse", "L1", "actual", "est_demand", "final_price", "currency", "order_qty", "policy"] + QC,
                         ["unique_id", "date"], ["order_qty", "est_demand"], (as_of - pd.Timedelta(days=H - 1), as_of)),
        "bt6_policy_comparison": (["policy", "cost_eur", "fill_rate_%", "vs_rule_%", "selected"], ["policy"], ["cost_eur"], None),
        "bt6_policy_by_warehouse": (["warehouse", "currency", "policy", "cost", "cost_eur", "fill_rate_%", "selected"],
                                    ["warehouse", "policy"], ["cost", "cost_eur"], None),
        "bt6_sensitivity": (["goodwill", "policy", "cost_eur", "vs_rule_%", "best"], ["goodwill", "policy"], ["cost_eur"], None),
        "run_log": (["step", "rows_in", "rows_out", "note"], [], [], None),
    }
    evaluate = cfg.get("mode", "evaluate") == "evaluate"
    for name in (OUTPUTS if evaluate else FAST_OUTPUTS):
        if name not in outputs or not isinstance(outputs[name], pd.DataFrame):
            raise ValueError(f"{BT_ID}: thiếu output '{name}'")
        df = outputs[name]
        cols, keys, nonneg, rng = spec[name]
        miss = [c for c in cols if c not in df.columns]
        if miss:
            raise ValueError(f"{BT_ID}: output '{name}' thiếu cột {miss}")
        if name != "run_log" and df.empty:
            raise ValueError(f"{BT_ID}: output '{name}' rỗng")
        if keys and df.duplicated(keys).any():
            raise ValueError(f"{BT_ID}: output '{name}' trùng khoá {keys}")
        nn = [c for c in cols if c != "note"]
        if df[nn].isna().any().any():
            raise ValueError(f"{BT_ID}: output '{name}' có NaN ở cột {list(df[nn].columns[df[nn].isna().any()])}")
        for c in nonneg:
            if (pd.to_numeric(df[c], errors="coerce") < -1e-9).any():
                raise ValueError(f"{BT_ID}: output '{name}' cột {c} có giá trị âm")
        if rng is not None:
            dt = pd.to_datetime(df["date"])
            if dt.min() < rng[0] or dt.max() > rng[1]:
                raise ValueError(f"{BT_ID}: output '{name}' ngày ngoài khoảng {rng[0]:%Y-%m-%d}→{rng[1]:%Y-%m-%d}")
    rep = outputs["replenishment"]
    bt = outputs.get("bt6_backtest", rep)
    if not (rep[QC[3]] <= rep["p90"] + 1e-9).all():
        raise ValueError(f"{BT_ID}: replenishment có p50 > p90")
    if set(rep.warehouse) != set(bt.warehouse):
        raise ValueError(f"{BT_ID}: replenishment và bt6_backtest khác tập kho")
    if cfg.get("warehouses") is not None and set(rep.warehouse) != set(cfg["warehouses"]):
        raise ValueError(f"{BT_ID}: output thiếu kho {sorted(set(cfg['warehouses']) - set(rep.warehouse))}")
    if evaluate and int(outputs["bt6_policy_comparison"]["selected"].sum()) != 1:
        raise ValueError(f"{BT_ID}: bt6_policy_comparison phải có đúng 1 chính sách selected")
