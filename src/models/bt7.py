"""BT7 – Giảm giá lô hàng sắp hết hạn (markdown) – bản tinh gọn để tích hợp pipeline, 7 kho.

Thuật toán giữ nguyên notebook final (final8/bt7/BT7_final.ipynb):
  Mô phỏng theo lô (hạn dùng theo ngành – cost_params), mỗi sáng nhận lô mới = order_qty của BT6.
  Không giảm giá → FIFO (lô cận hạn bán trước). Có giảm giá → khách giá thường mua hàng mới, lô cận hạn bán cho
  phần cầu còn lại + cầu tăng thêm = lift BT5 (lift_% đúng mức; mức khác → e^(θ·d) − 1; ngành không có → 0).
  Lô hết hạn cuối ngày bị huỷ, chi phí huỷ/đơn vị = giá × (cost_ratio + waste_handling_cost_ratio).
  Chính sách tối ưu: mỗi sáng chọn mức giảm ∈ {0, 10, 20, 30%} có lợi nhuận kỳ vọng HÔM NAY cao nhất trên 8 kịch bản
  P20…P90 (nhìn trước 1 bước, hoà → mức thấp hơn). So với: không giảm giá, giảm cố định 30%.
  Kỳ kiểm tra: as_of−13 → as_of, nhu cầu thật = est_demand (BT3, có sẵn trong bt6_backtest).
  Kế hoạch what-if: 14 ngày tới, nhập = replenishment (BT6), nhu cầu = P30 của BT4 (kịch bản bán chậm).
Vector hoá: vòng lặp theo ngày giữ nguyên, các SKU được xử lý đồng thời bằng numpy (ma trận tồn theo số ngày còn hạn);
cùng thứ tự phép tính như vòng lặp gốc → kết quả trùng khớp (tests/test_model.py so với bản vòng lặp tham chiếu).
7 kho: doanh thu/giá vốn/chi phí huỷ tính theo NỘI TỆ từng SKU, quy đổi EUR (fx_eur) trước khi cộng nhiều kho.
KHÔNG có inventory snapshot thật: tồn kho là tồn MÔ PHỎNG từ order_qty (tồn đầu kỳ = 0); không tạo tồn kho giả nào khác.
Hai chế độ (D06): mode="models" chỉ lập kế hoạch what-if 14 ngày (markdown_plan + markdown_summary) – không cần bt6_backtest;
mode="evaluate" thêm chấm 3 chính sách trên kỳ kiểm tra + độ nhạy và trả "_params".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BT_ID = "BT7"
REQUIRED_INPUTS = ["bt6_backtest", "replenishment", "fc_sku", "promo_effect", "cost_params"]
OPTIONAL_INPUTS: list[str] = []
UPSTREAM = {"bt6_backtest": ("BT6", "bt6_backtest"), "replenishment": ("BT6", "replenishment"),
            "fc_sku": ("BT4", "fc_sku"), "promo_effect": ("BT5", "promo_effect")}
OUTPUTS = ["markdown_plan", "markdown_summary", "bt7_policy_comparison", "bt7_policy_by_warehouse", "bt7_sensitivity", "run_log"]
FAST_INPUTS = ["replenishment", "fc_sku", "promo_effect", "cost_params"]
FAST_OUTPUTS = ["markdown_plan", "markdown_summary", "run_log"]

QC = [f"p{q}" for q in range(20, 100, 10)]
POLICY_NAMES = {"none": "Không giảm giá", "fixed30": "Giảm cố định 30% lô sắp hết hạn", "optimal": "Tối ưu mức giảm theo ngày (BT7)"}
KPI = ["revenue", "cogs", "waste_units", "waste_cost", "sold", "demand", "markdown_units"]
MONEY = ["revenue", "cogs", "waste_cost"]

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",
    "train_start": "2020-12-05",
    "horizon": 14,
    "seed": 42,                       # không có thành phần ngẫu nhiên; giữ cho thống nhất
    "warehouses": None,               # None = mọi kho có trong input
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},   # ASSUMED
    "currency_by_warehouse": {"Prague_1": "CZK", "Prague_2": "CZK", "Prague_3": "CZK", "Brno_1": "CZK",
                              "Budapest_1": "HUF", "Munich_1": "EUR", "Frankfurt_1": "EUR"},
    "levels": [0.0, 0.1, 0.2, 0.3],   # mức giảm được thử
    "fixed_level": 0.3,               # chính sách so sánh: giảm cố định
    "scenario_q": "p30",              # kịch bản bán chậm cho kế hoạch what-if
    "required_inputs": REQUIRED_INPUTS,
    "mode": "evaluate",               # "models" | "evaluate"
    "frozen": None,
}

REQ_COLS = {
    "bt6_backtest": ["unique_id", "date", "warehouse", "L1", "est_demand", "final_price", "order_qty"] + QC,
    "replenishment": ["unique_id", "date", "warehouse", "L1", "final_price", "p50", "order_qty", "policy"],
    "fc_sku": ["unique_id", "date", "warehouse", "L1"] + QC,
    "promo_effect": ["L1", "discount", "theta", "lift_%"],
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


def lift_table(eff: pd.DataFrame, l1s, levels) -> dict[str, dict[float, float]]:
    """Lift (tỷ lệ) theo ngành × mức giảm: đúng mức BT5 → lift_%/100; mức khác → e^(θ·lv) − 1; ngành không có → 0."""
    def one(l1, lv):
        if lv == 0:
            return 0.0
        e = eff[eff.L1 == l1]
        if e.empty:
            return 0.0
        hit = e[np.isclose(e.discount, lv)]
        if len(hit):
            return float(hit["lift_%"].iloc[0]) / 100
        return float(np.exp(e.theta.iloc[0] * lv) - 1)
    return {l1: {lv: one(l1, lv) for lv in levels} for l1 in l1s}


# ---------------------------------------------------------------- mô phỏng (vector hoá theo SKU)
def simulate_vec(df: pd.DataFrame, policy: str, demand_col: str, cost: pd.DataFrame, lift: dict, levels: list,
                 fixed_level: float = 0.3, shelf_shift: int = 0, keep_plan: bool = False):
    """Mô phỏng mọi SKU cùng lúc. Trả (bảng KPI theo SKU [nội tệ], kế hoạch ngày nếu keep_plan).
    Mỗi SKU đi qua các dòng của nó theo thứ tự ngày (như vòng lặp gốc: mỗi dòng = 1 bước, lô già thêm 1 ngày/bước)."""
    g = df.sort_values(["unique_id", "L1", "date"], kind="stable").reset_index(drop=True)
    sku = g.groupby(["unique_id", "L1"], sort=True).ngroup().to_numpy()
    step = g.groupby(["unique_id", "L1"], sort=True).cumcount().to_numpy()
    keys = g.groupby(["unique_id", "L1"], sort=True).agg(warehouse=("warehouse", "first"), currency=("currency", "first")).reset_index()
    S, K = len(keys), int(step.max()) + 1 if len(g) else 0
    cp = cost.loc[keys.L1]
    shelf = np.maximum(1, cp.shelf_life_days.astype(int).to_numpy() + shelf_shift)
    cr, hd = cp.cost_ratio.to_numpy(float), cp.waste_handling_cost_ratio.to_numpy(float)
    L = np.array([[lift[l1][lv] for lv in levels] for l1 in keys.L1], float).reshape(S, len(levels))
    lv_arr = np.array(levels, float)

    def mat(col, fill=np.nan):
        m = np.full((S, K), fill, float); m[sku, step] = g[col].to_numpy(float); return m
    OQ, PR, DM = mat("order_qty"), mat("final_price"), mat(demand_col)
    DSC = np.stack([mat(q) for q in QC], axis=2)              # (S, K, 8) kịch bản
    ACT = np.zeros((S, K), bool); ACT[sku, step] = True
    row_of = np.full((S, K), -1); row_of[sku, step] = np.arange(len(g))

    A = int(shelf.max()) if S else 1
    q = np.zeros((S, A + 1))                                   # q[:, a] = số lượng lô còn a ngày hạn
    tot = {k: np.zeros(S) for k in KPI}
    plan = []
    rows = np.arange(S)
    for k in range(K):
        act = ACT[:, k]
        oq = np.where(act, OQ[:, k], 0.0)
        new = act & (oq > 0)
        q[rows[new], shelf[new]] = oq[new]                     # nhận lô mới đầu ngày
        expiring = q[:, 1].copy()
        fresh = np.zeros(S)
        for a in range(2, A + 1):
            fresh = fresh + q[:, a]
        p = np.where(act, PR[:, k], 0.0); c = p * cr
        wuc = p * (cr + hd)
        if policy == "none":
            d = np.zeros(S)
        elif policy == "fixed30":
            d = np.where(expiring <= 0, 0.0, fixed_level)
        else:
            Dsc = np.where(act[:, None], DSC[:, k, :], 0.0)
            best_val = best_lv = None
            for j, lv in enumerate(levels):
                if lv == 0:
                    es = np.minimum(expiring[:, None], Dsc)
                    fs = np.minimum(fresh[:, None], Dsc - es)
                    wst = expiring[:, None] - es
                    ms = 0.0 * Dsc
                else:
                    fs = np.minimum(fresh[:, None], Dsc)
                    ms = np.minimum(expiring[:, None], np.maximum(Dsc - fs + Dsc * L[:, j:j + 1], 0.0))
                    wst = expiring[:, None] - ms
                    es = 0.0 * Dsc
                val = np.mean((p[:, None] - c[:, None]) * (fs + es) + (p[:, None] * (1 - lv) - c[:, None]) * ms
                              - wuc[:, None] * wst, axis=1)
                if best_val is None:
                    best_val, best_lv = val, np.full(S, lv)
                else:
                    upd = val > best_val + 1e-9
                    best_val, best_lv = np.where(upd, val, best_val), np.where(upd, lv, best_lv)
            d = np.where(expiring <= 0, 0.0, best_lv)
        D = np.where(act, DM[:, k], 0.0)
        jd = np.searchsorted(lv_arr, d)
        Ld = L[rows, np.clip(jd, 0, len(levels) - 1)]
        # nhánh không giảm giá (FIFO)
        es0 = np.minimum(expiring, D); fs0 = np.minimum(fresh, D - es0); w0 = expiring - es0
        # nhánh có giảm giá
        fs1 = np.minimum(fresh, D); ms1 = np.minimum(expiring, np.maximum(D - fs1 + D * Ld, 0.0)); w1 = expiring - ms1
        z = d == 0
        fs, ms, wst, es = np.where(z, fs0, fs1), np.where(z, 0.0 * D, ms1), np.where(z, w0, w1), np.where(z, es0, 0.0 * D)
        q[:, 1] = q[:, 1] - (ms + es)                          # trừ phần bán từ lô cận hạn
        left = fs.copy()
        for a in range(2, A + 1):                              # trừ phần bán từ hàng mới, lô cũ trước
            t = np.minimum(q[:, a], left); q[:, a] = q[:, a] - t; left = left - t
        aged = np.zeros_like(q)                                # qua ngày: lô hết hạn bị loại, lô còn lại giảm 1 ngày
        aged[:, 1:A] = np.where(q[:, 2:] > 1e-9, q[:, 2:], 0.0)
        q = np.where(act[:, None], aged, q)
        sold = fs + ms + es
        add = {"revenue": (fs + es) * p + ms * p * (1 - d), "cogs": sold * c, "waste_units": wst,
               "waste_cost": wst * wuc, "sold": sold, "demand": D + np.where(d > 0, D * Ld, 0.0), "markdown_units": ms}
        for kk in KPI:
            tot[kk] = tot[kk] + np.where(act, add[kk], 0.0)
        if keep_plan:
            idx = np.flatnonzero(act)
            r = row_of[idx, k]
            for i, ri in zip(idx, r):
                plan.append((g.unique_id.iat[ri], g.date.iat[ri], float(d[i]), round(float(fresh[i] + expiring[i]), 1),
                             round(float(expiring[i]), 1), round(float(sold[i]), 1), round(float(ms[i]), 1), round(float(wst[i]), 1)))
    kpi = keys.assign(**{k: tot[k] for k in KPI})
    plan_df = pd.DataFrame(plan, columns=["unique_id", "date", "discount", "stock", "expiring_today", "expected_sold",
                                          "sold_marked_down", "expected_waste"]) if keep_plan else None
    if plan_df is not None:                                    # cùng thứ tự vòng lặp gốc: theo SKU rồi theo ngày
        plan_df = plan_df.sort_values(["unique_id", "date"], kind="stable").reset_index(drop=True)
    return kpi, plan_df


def simulate_all(df, policies, demand_col, cost, lift, levels, fx, fixed_level=0.3, shelf_shift=0):
    """Chạy các chính sách; KPI tiền tệ nội tệ/SKU → EUR khi cộng. Trả (bảng so sánh EUR, bảng theo kho, kế hoạch optimal)."""
    rows, by_wh, plan = [], [], None
    for pol in policies:
        kpi, pl = simulate_vec(df, pol, demand_col, cost, lift, levels, fixed_level, shelf_shift, keep_plan=(pol == "optimal"))
        if pol == "optimal":
            plan = pl
        rate = kpi.currency.map(fx)
        for m in MONEY:
            kpi[m + "_eur"] = kpi[m] * rate
        kpi["gross_margin"] = kpi.revenue - kpi.cogs - kpi.waste_cost
        kpi["gross_margin_eur"] = kpi.revenue_eur - kpi.cogs_eur - kpi.waste_cost_eur
        agg_cols = ["waste_units", "sold", "demand", "markdown_units"] + [m + "_eur" for m in MONEY] + ["gross_margin_eur"]
        rows.append({"policy": pol, **kpi[agg_cols].sum().to_dict()})
        w = kpi.groupby(["warehouse", "currency"], sort=True)[MONEY + ["gross_margin"] + agg_cols].sum().reset_index()
        w.insert(2, "policy", pol)
        by_wh.append(w)

    def finish(t, base_key):
        t["waste_%_of_sold"] = t.waste_units / t.sold.clip(lower=1e-9) * 100
        t["fill_rate_%"] = t.sold / t.demand.clip(lower=1e-9) * 100
        base = t[t.policy == "none"].set_index(base_key)["gross_margin_eur"] if base_key else t.gross_margin_eur.iloc[0]
        if base_key:
            t["margin_vs_none_%"] = (t.gross_margin_eur / t.set_index(base_key).index.map(base).to_numpy() - 1) * 100
        else:
            t["margin_vs_none_%"] = (t.gross_margin_eur / base - 1) * 100
        t["policy"] = t.policy.map(POLICY_NAMES)
        return t.round(1)
    comp = finish(pd.DataFrame(rows), None)
    bw = pd.concat(by_wh, ignore_index=True)
    bw = finish(bw, ["warehouse"]) if "none" in policies else bw.assign(policy=bw.policy.map(POLICY_NAMES)).round(1)
    return comp, bw, plan


# ---------------------------------------------------------------- mô hình
def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    cfg = _cfg(config)
    evaluate = cfg["mode"] == "evaluate"
    if not evaluate:
        cfg["required_inputs"] = FAST_INPUTS
    log: list[dict] = []
    x = _check_inputs(inputs, cfg)
    as_of, t0, H = cfg["as_of"], cfg["train_start"], int(cfg["horizon"])
    levels, sq = [float(v) for v in cfg["levels"]], cfg["scenario_q"]
    if sq not in QC:
        raise ValueError(f"{BT_ID}: scenario_q phải thuộc {QC}")
    test_start = as_of - pd.Timedelta(days=H - 1)
    fc_dates = pd.date_range(as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H), freq="D")
    _log(log, "config", 0, 0, f"as_of={as_of:%Y-%m-%d}; horizon={H}; levels={levels}; scenario={sq}; fx_eur={cfg['fx_eur']}; "
                              "inventory=MÔ PHỎNG từ order_qty BT6, tồn đầu kỳ 0 (không có snapshot thật)")

    # 1. cắt mốc chống rò rỉ
    rep, fc = x["replenishment"], x["fc_sku"]
    b6 = x["bt6_backtest"] if evaluate else rep.iloc[0:0].assign(est_demand=0.0, **{q: 0.0 for q in QC})
    n = len(b6); b6 = b6[(b6.date >= max(test_start, t0)) & (b6.date <= as_of)]
    if evaluate:
        _log(log, "cut bt6_backtest [as_of-13, as_of]", n, len(b6))
    n = len(rep); rep = rep[rep.date.isin(fc_dates)]
    _log(log, "cut replenishment (as_of, as_of+h]", n, len(rep))
    n = len(fc); fc = fc[fc.date.isin(fc_dates)]
    _log(log, "cut fc_sku (as_of, as_of+h]", n, len(fc))

    # 2. phạm vi kho
    whs = cfg["warehouses"]
    if whs is None:
        whs = sorted(set(b6.warehouse) if evaluate else set(rep.warehouse))
    whs = list(whs)
    for name, df in ([("bt6_backtest", b6)] if evaluate else []) + [("replenishment", rep), ("fc_sku", fc)]:
        lack = sorted(set(whs) - set(df.warehouse))
        if lack:
            raise ValueError(f"{BT_ID}: input '{name}' thiếu kho {lack} trong khoảng ngày cần dùng")
    b6, rep, fc = (df[df.warehouse.isin(whs)] for df in (b6, rep, fc))

    # 3. làm sạch: trùng khoá, thiếu số liệu, tiền tệ
    b6 = b6.drop_duplicates(["unique_id", "date"]).reset_index(drop=True)
    rep = rep.drop_duplicates(["unique_id", "date"]).reset_index(drop=True)
    fc = fc.drop_duplicates(["unique_id", "date"]).reset_index(drop=True)
    n = len(b6); b6 = b6.dropna(subset=["est_demand", "final_price", "order_qty"] + QC).reset_index(drop=True)
    _log(log, "drop bt6_backtest rows with NaN", n, len(b6))
    b6 = b6.assign(currency=_currency(b6, cfg, "bt6_backtest"))
    rep = rep.assign(currency=_currency(rep, cfg, "replenishment"))
    for name, df in [("bt6_backtest", b6), ("replenishment", rep)]:
        multi = df.groupby("unique_id").warehouse.nunique()
        if (multi > 1).any():
            raise ValueError(f"{BT_ID}: unique_id thuộc nhiều kho trong '{name}': {list(multi[multi > 1].index[:5])}")
    if (evaluate and not len(b6)) or not len(rep) or not len(fc):
        raise ValueError(f"{BT_ID}: bt6_backtest / replenishment / fc_sku rỗng sau khi cắt mốc")

    cost = x["cost_params"].rename(columns={"L1_category_name_en": "L1"}).set_index("L1")[["cost_ratio", "shelf_life_days", "waste_handling_cost_ratio"]]
    miss_l1 = sorted((set(b6.L1) | set(rep.L1)) - set(cost.index))
    if miss_l1:
        for l1 in miss_l1:
            cost.loc[l1] = cost.mean(numeric_only=True)
        cost["shelf_life_days"] = cost.shelf_life_days.round().astype(int)
        _log(log, "cost_params missing L1", len(cost) - len(miss_l1), len(cost), f"CẢNH BÁO: {miss_l1} dùng tham số trung bình")
    eff = x["promo_effect"]
    LIFT = lift_table(eff, cost.index, levels)
    no_eff = sorted(set(cost.index) - set(eff.L1))
    _log(log, "lift from BT5", len(eff), len(LIFT), ("CẢNH BÁO lift=0 cho " + str(no_eff)) if no_eff else
         "; ".join(f"{l}: " + "/".join(f"{v:.3f}" for v in LIFT[l].values()) for l in LIFT))
    fx, fl = cfg["fx_eur"], float(cfg["fixed_level"])
    if not any(np.isclose(fl, lv) for lv in levels):
        raise ValueError(f"{BT_ID}: fixed_level {fl} phải thuộc levels {levels}")

    if evaluate:
        # 4. kỳ kiểm tra: 3 chính sách, nhu cầu thật
        comp, comp_wh, _ = simulate_all(b6, ["none", "fixed30", "optimal"], "est_demand", cost, LIFT, levels, fx, fl)
        comp["selected"] = comp.gross_margin_eur == comp.gross_margin_eur.max()
        comp_wh.insert(0, "period", "backtest")

        # 5. độ nhạy
        half = {l1: {lv: v * 0.5 for lv, v in d_.items()} for l1, d_ in LIFT.items()}
        sens = []
        for name, lift, sh in [("Gốc", LIFT, 0), ("Hạn dùng −1 ngày", LIFT, -1), ("Hạn dùng +1 ngày", LIFT, 1), ("Lift BT5 x 0,5", half, 0)]:
            c, _, _ = simulate_all(b6, ["none", "optimal"], "est_demand", cost, lift, levels, fx, fl, shelf_shift=sh)
            sens.append({"kịch bản": name, "huỷ_không_giảm": c.waste_units[0], "huỷ_tối_ưu": c.waste_units[1],
                         "lợi_nhuận_tăng_%": c["margin_vs_none_%"][1]})
        sens = pd.DataFrame(sens)

    # 6. kế hoạch what-if 14 ngày
    fut = rep[["unique_id", "date", "warehouse", "currency", "L1", "order_qty", "final_price"]].merge(
        fc[["unique_id", "date"] + QC], on=["unique_id", "date"])
    khop = len(fut) / len(rep)
    n = len(fut); fut = fut.dropna(subset=["order_qty", "final_price", sq] + QC).reset_index(drop=True)
    _log(log, "plan join replenishment+fc_sku", len(rep), len(fut),
         f"khớp {khop:.1%}" + (" CẢNH BÁO <95%" if khop < 0.95 else "") + f"; bỏ dòng NaN: {n - len(fut)}")
    if not len(fut):
        raise ValueError(f"{BT_ID}: replenishment và fc_sku không có SKU-ngày chung")
    fut["scenario_demand"] = fut[sq]
    summary, sum_wh, plan = simulate_all(fut, ["none", "fixed30", "optimal"], "scenario_demand", cost, LIFT, levels, fx, fl)
    summary["scenario"] = f"nhu cầu = {sq.upper()} của BT4"
    summary["selected"] = summary.gross_margin_eur == summary.gross_margin_eur.max()
    sum_wh.insert(0, "period", "plan_whatif")
    md = plan.merge(fut[["unique_id", "date", "warehouse", "currency", "L1", "order_qty", "final_price"]], on=["unique_id", "date"])
    md = md[["unique_id", "date", "warehouse", "L1", "discount", "stock", "expiring_today", "expected_waste", "expected_sold",
             "sold_marked_down", "order_qty", "final_price", "currency"]].sort_values(["unique_id", "date"]).reset_index(drop=True)
    _log(log, "markdown_plan", len(fut), len(md), f"SKU-ngày đề xuất giảm giá: {int((md.discount > 0).sum())}")

    for t in ((comp, summary) if evaluate else (summary,)):
        t["gross_margin"] = t["gross_margin_eur"]             # alias tên hợp đồng QUY_UOC; đơn vị EUR
        t["currency"] = "EUR"
    out = {"markdown_plan": md, "markdown_summary": summary, "run_log": pd.DataFrame(log)}
    if evaluate:
        out.update({"bt7_policy_comparison": comp, "bt7_policy_by_warehouse": pd.concat([comp_wh, sum_wh], ignore_index=True),
                    "bt7_sensitivity": sens})
        out["_params"] = {"policy": "optimal", "levels": levels, "scenario_q": sq}
    validate_outputs(out, {**cfg, "warehouses": whs})
    return out


# ---------------------------------------------------------------- kiểm tra hợp đồng
def validate_outputs(outputs: dict[str, pd.DataFrame], config: dict) -> None:
    cfg = _cfg(config)
    as_of, H = cfg["as_of"], int(cfg["horizon"])
    money = ["revenue_eur", "cogs_eur", "waste_cost_eur", "gross_margin_eur"]
    spec = {
        "markdown_plan": (["unique_id", "date", "warehouse", "L1", "discount", "stock", "expiring_today", "expected_waste",
                           "expected_sold", "order_qty", "final_price", "currency"], ["unique_id", "date"],
                          ["stock", "expiring_today", "expected_waste", "expected_sold", "order_qty"],
                          (as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H))),
        "markdown_summary": (["policy", "gross_margin", "gross_margin_eur", "currency", "waste_units", "scenario", "selected"] + money,
                             ["policy"], ["waste_units"], None),
        "bt7_policy_comparison": (["policy", "gross_margin", "gross_margin_eur", "waste_units", "fill_rate_%", "selected"] + money,
                                  ["policy"], ["waste_units"], None),
        "bt7_policy_by_warehouse": (["period", "warehouse", "currency", "policy", "gross_margin", "gross_margin_eur", "waste_units"],
                                    ["period", "warehouse", "policy"], ["waste_units"], None),
        "bt7_sensitivity": (["kịch bản", "huỷ_không_giảm", "huỷ_tối_ưu", "lợi_nhuận_tăng_%"], ["kịch bản"], [], None),
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
    md = outputs["markdown_plan"]
    if ((md.discount < 0) | (md.discount > 0.5)).any():
        raise ValueError(f"{BT_ID}: markdown_plan có discount ngoài [0; 0,5]")
    if cfg.get("warehouses") is not None and set(md.warehouse) != set(cfg["warehouses"]):
        raise ValueError(f"{BT_ID}: markdown_plan thiếu kho {sorted(set(cfg['warehouses']) - set(md.warehouse))}")
    for name in ("markdown_summary", "bt7_policy_comparison") if evaluate else ("markdown_summary",):
        if int(outputs[name]["selected"].sum()) < 1:
            raise ValueError(f"{BT_ID}: {name} không có chính sách selected")
