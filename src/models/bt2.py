"""BT2 – Xếp ca nhân viên kho (sáng/chiều) và số ca tài xế 14 ngày – bản tinh gọn để tích hợp pipeline.

Nguồn phương án: /home/claude/final8/bt2/BT2_final.ipynb (= original_notebook.ipynb).
Giữ nguyên: ngày đóng cửa (ô 2.1b), chuyển bt1_backtest rộng → dài + fold (2.1c), lưới kế hoạch + bù ngày thiếu (2.2),
tham số workforce_params + giả định riêng (3.1), số đơn → giờ công (4.2), quy tắc cũ (4.3), dự phòng Phục Sinh (4.4),
mẫu ca 5/2 (4.6), MIP cải tiến 19 kịch bản sai số (4.7), mô phỏng chi phí (4.9), sai số ngoài mẫu không nhìn trước (4.10, 7.1),
backtest trên các fold BT1 (7.2–7.11), tiêu chí chọn: chi phí thấp nhất trong các phương án có giờ thiếu = 0 (7.14),
độ nhạy phạt ×5/×10, năng suất 120/180 (8.x), ca tài xế (11.1), staff_plan (11.2, 12.1).
Phương án trong model.py: `rule` (quy tắc cũ, baseline) và `mip_new` (MIP cải tiến, final) + tham chiếu `oracle`.
Bỏ (chỉ có ở notebook): p50, p90, mip_v3, p50_hol, p90_hol, bảng giá trị dự báo theo mô hình BT1, biểu đồ, model card.

Hai chế độ (D06): mode="models" chỉ lập kế hoạch 14 ngày bằng phương án đã chốt (frozen["chosen_policy"], thường mip_new)
với 19 phân vị sai số BT1 đã chốt (frozen["error_percentiles"]) – không cần bt1_backtest, không backtest/độ nhạy.
mode="evaluate" chạy đủ như notebook và trả "_params".
"""
from __future__ import annotations

from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

BT_ID = "BT2"
REQUIRED_INPUTS = ["orders_daily", "calendar", "workforce_params", "bt1_backtest", "fc_orders"]
OPTIONAL_INPUTS: list[str] = []
UPSTREAM = {"bt1_backtest": ("BT1", "bt1_backtest"), "fc_orders": ("BT1", "fc_orders")}
OUTPUTS = ["staff_plan", "driver_plan", "bt2_policy_comparison", "bt2_policy_by_warehouse", "bt2_sensitivity",
           "bt2_solve_log", "run_log"]
FAST_INPUTS = ["orders_daily", "calendar", "workforce_params", "fc_orders"]
FAST_OUTPUTS = ["staff_plan", "driver_plan", "bt2_solve_log", "run_log"]

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",
    "train_start": "2020-12-05",
    "horizon": 14,
    "seed": 42,                        # không có ngẫu nhiên (CBC tất định khi 1 luồng và không chạm giới hạn thời gian)
    "n_jobs": 1,                       # số luồng CBC (notebook: 1)
    "warehouses": None,                # None = tất cả kho có trong orders_daily
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},   # ASSUMED – BT2 tính tiền bằng EUR (lương EUR) nên không quy đổi
    "required_inputs": REQUIRED_INPUTS,
    "policies": ["rule", "mip_new"],   # baseline + final; tiêu chí chọn áp trên tập này
    "short_tol": 0.5,                  # "giờ thiếu = 0" ⇔ ≤ 0,5 giờ
    "assumed_defaults": {"morning_share": 0.55, "overtime_cap": 0.25, "shortage_penalty": 3.0, "rule_buffer": 0.10},
    "solver_time_limit": 60,           # giây / lần giải MIP cải tiến (notebook: 60)
    "solver_threads": 1,               # CBC 1 luồng như notebook (n_jobs=-1 truyền vào CBC thành "-threads -1" → treo/chậm trên Windows)
    "solver_gap_rel": 1e-4,
    "percentiles": list(range(5, 100, 5)),   # 19 kịch bản sai số
    "min_past_errors": 30,
    "sensitivity": [{"scenario": "phạt ×5", "penalty": 5.0}, {"scenario": "phạt ×10", "penalty": 10.0},
                    {"scenario": "120 món/giờ", "picks_per_hour": 120.0}, {"scenario": "180 món/giờ", "picks_per_hour": 180.0}],
    "pre_easter_days": [-3, -2, -1],
    "mode": "evaluate",                # "models" | "evaluate"
    "frozen": None,                    # {"chosen_policy": "mip_new", "error_percentiles": [19 số]}
}

INPUT_COLUMNS = {
    "orders_daily": ["warehouse", "date", "orders"],
    "calendar": ["warehouse", "date", "holiday", "shops_closed"],
    "workforce_params": ["warehouse", "hourly_wage_eur", "items_per_order", "picks_per_hour", "shift_hours",
                         "overtime_multiplier", "orders_per_driver_shift"],
    "bt1_backtest": ["warehouse", "date", "cutoff", "y", "series"],
    "fc_orders": ["warehouse", "date", "series", "p50", "p90", "model"],
}
POLICY_NAME = {"rule": "Quy tắc cũ: tuần trước +10%", "p50": "P50", "p90": "P90",
               "mip_v3": "MIP (v3): P90 + trần làm thêm", "p50_hol": "P50 + dự phòng lễ", "p90_hol": "P90 + dự phòng lễ",
               "mip_new": "MIP cải tiến (kịch bản sai số + ca 5/2 + dự phòng lễ)",
               "oracle": "Tham chiếu: biết trước số đơn thật"}
ORDERS_USED = {"rule": "orders_rule", "mip_new": "orders_p50_hol"}


def _log(log, step, rows_in, rows_out, note):
    log.append({"step": step, "rows_in": rows_in, "rows_out": rows_out, "note": note})


def _prepare(inputs: dict, cfg: dict, log: list) -> dict:
    missing = sorted(set(cfg["required_inputs"]) - set(inputs))
    if missing:
        raise ValueError(f"{BT_ID}: thiếu input bắt buộc {missing}")
    t0, as_of = pd.Timestamp(cfg["train_start"]), pd.Timestamp(cfg["as_of"])
    fc_end = as_of + pd.Timedelta(days=int(cfg["horizon"]))
    d = {}
    names = REQUIRED_INPUTS if cfg.get("mode", "evaluate") == "evaluate" else FAST_INPUTS
    for name in names:
        df = inputs[name]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{BT_ID}: input '{name}' phải là DataFrame")
        miss = [c for c in INPUT_COLUMNS[name] if c not in df.columns]
        if miss:
            raise ValueError(f"{BT_ID}: input '{name}' thiếu cột {miss}")
        df = df.copy()
        for c in ("date", "cutoff", "data_until"):
            if c in df.columns:
                try:
                    df[c] = pd.to_datetime(df[c])
                except Exception as e:  # noqa: BLE001
                    raise ValueError(f"{BT_ID}: cột {c} của '{name}' không chuyển được sang ngày: {e}") from e
        if "date" in df.columns:
            if name == "calendar":
                lo, hi = t0, fc_end
            elif name == "fc_orders":
                lo, hi = as_of + pd.Timedelta(days=1), fc_end
            else:
                lo, hi = t0, as_of
            n0 = len(df)
            df = df[(df["date"] >= lo) & (df["date"] <= hi)].copy()
            _log(log, f"cut_{name}", n0, len(df), f"giữ {lo.date()} ≤ date ≤ {hi.date()}")
        d[name] = df
    for name, keys in {"orders_daily": ["warehouse", "date"], "calendar": ["warehouse", "date"],
                       "fc_orders": ["series", "warehouse", "date"], "bt1_backtest": ["series", "warehouse", "date", "cutoff"],
                       "workforce_params": ["warehouse"]}.items():
        if name in d and d[name].duplicated(keys).any():
            raise ValueError(f"{BT_ID}: input '{name}' trùng khoá {keys}")
    if "data_until" in d["fc_orders"].columns and (d["fc_orders"]["data_until"] > as_of).any():
        raise ValueError(f"{BT_ID}: fc_orders dùng dữ liệu sau as_of – hỏi lại BT1")
    if "bt1_backtest" in d and (d["bt1_backtest"].empty or (d["bt1_backtest"]["cutoff"] >= as_of).any()):
        raise ValueError(f"{BT_ID}: bt1_backtest rỗng hoặc có mốc cắt ≥ as_of")
    o = d["orders_daily"]
    n_null = int(o["orders"].isna().sum())
    d["orders_daily"] = o[o["orders"].notna()]
    _log(log, "null_orders", len(o), len(d["orders_daily"]), f"{n_null} dòng orders NULL bị bỏ (coi như kho không có đơn)")
    whs = cfg.get("warehouses")
    all_wh = sorted(d["orders_daily"]["warehouse"].unique())
    if whs is not None:
        lack = sorted(set(whs) - set(all_wh))
        if lack:
            raise ValueError(f"{BT_ID}: orders_daily không có kho {lack}")
        for k in d:
            d[k] = d[k][d[k]["warehouse"].isin(whs)].copy()
    whs = sorted(d["orders_daily"]["warehouse"].unique())
    if not whs:
        raise ValueError(f"{BT_ID}: orders_daily rỗng")
    for name in [n for n in ["fc_orders", "bt1_backtest", "workforce_params"] if n in d]:
        lack = sorted(set(whs) - set(d[name]["warehouse"]))
        if lack:
            raise ValueError(f"{BT_ID}: '{name}' thiếu kho {lack}")
    _log(log, "warehouses", len(all_wh), len(whs), ",".join(whs))
    # train.csv của notebook = orders_daily ⟕ calendar (holiday, shops_closed) theo warehouse+date
    train = d["orders_daily"].merge(d["calendar"][["warehouse", "date", "holiday", "shops_closed"]], on=["warehouse", "date"], how="left")
    n_nocal = int(train["holiday"].isna().sum())
    train[["holiday", "shops_closed"]] = train[["holiday", "shops_closed"]].fillna(0)
    _log(log, "join_orders_calendar", len(d["orders_daily"]), len(train),
         f"dựng lại train.csv = orders_daily ⟕ calendar(warehouse,date); {n_nocal} kho-ngày không có lịch → cờ = 0")
    d["train"] = train
    d["warehouses"] = whs
    return d


def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    import pulp
    from dateutil.easter import easter

    cfg = {**DEFAULT_CONFIG, **(config or {})}
    is_eval = cfg["mode"] == "evaluate"
    if not is_eval:
        cfg["required_inputs"] = FAST_INPUTS
    log: list = []
    _log(log, "config", None, None, f"as_of={cfg['as_of']}, horizon={cfg['horizon']}, policies={cfg['policies']}, "
                                    f"solver_time_limit={cfg['solver_time_limit']}s, gapRel={cfg['solver_gap_rel']}, threads={max(1, int(cfg.get('solver_threads', 1)))}; "
                                    "artifact_dir không dùng (tối ưu lại mỗi run)")
    d = _prepare(inputs, cfg, log)
    train, cal, WAREHOUSES = d["train"], d["calendar"], d["warehouses"]
    H = int(cfg["horizon"]); as_of = pd.Timestamp(cfg["as_of"])
    PLAN_START, PLAN_END = as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H)
    SHORT_TOL = float(cfg["short_tol"])
    POLICIES = [p for p in cfg["policies"]]
    frozen = cfg.get("frozen") or {}
    if not is_eval:
        if frozen.get("chosen_policy") not in ("rule", "mip_new") or len(frozen.get("error_percentiles") or []) != len(cfg["percentiles"]):
            raise ValueError(f"{BT_ID}: chế độ models cần tham số chốt chosen_policy + {len(cfg['percentiles'])} error_percentiles "
                             "– chạy `evaluate` trước hoặc kiểm tra config/model_params/BT2.json")
        POLICIES = [frozen["chosen_policy"]]
    for p in POLICIES:
        if p not in ("rule", "mip_new"):
            raise ValueError(f"{BT_ID}: model.py chỉ hỗ trợ phương án rule, mip_new (phương án khác ở original_notebook)")

    # ---- 2.1 + 2.1b ngày đóng cửa ----
    fc = d["fc_orders"]
    fc_orders = fc[fc["series"] == "orders"].copy()
    if fc_orders.empty:
        raise ValueError(f"{BT_ID}: fc_orders không có series 'orders'")
    BT1_MODEL = fc_orders["model"].mode().iloc[0]
    hist_cal = cal[cal["date"] <= as_of]
    hist_cl = hist_cal.merge(train[["warehouse", "date", "orders"]], on=["warehouse", "date"], how="left")
    closed_share = hist_cl[hist_cl["shops_closed"] == 1].groupby("warehouse")["orders"].apply(lambda s: s.isna().mean())
    CLOSE_WHEN_SHOPS_CLOSED = sorted(closed_share[closed_share >= 0.8].index)
    cal_closed = cal[(cal["shops_closed"] == 1) & cal["warehouse"].isin(CLOSE_WHEN_SHOPS_CLOSED)][["warehouse", "date"]].assign(cal_closed=1)

    def closed_flag(df, p50_col):
        k = df[["warehouse", "date"]].merge(cal_closed, on=["warehouse", "date"], how="left")
        return ((df[p50_col].fillna(0).values <= 0) | (k["cal_closed"].fillna(0).values == 1)).astype(int)
    _log(log, "closed_rule", None, None, f"kho đóng khi shops_closed=1: {CLOSE_WHEN_SHOPS_CLOSED}; mô hình BT1 (orders) = {BT1_MODEL}")

    if is_eval:
        # ---- 2.1c bt1_backtest rộng → dài ----
        b = d["bt1_backtest"][d["bt1_backtest"]["series"] == "orders"].copy()
        MODELS = [c[:-4] for c in b.columns if c.endswith("-p90") and c[:-4] in b.columns]
        if BT1_MODEL not in MODELS:
            raise ValueError(f"{BT_ID}: mô hình {BT1_MODEL} của fc_orders không có trong bt1_backtest")
        FOLD_NAME = {c: f"F{i + 1}" for i, c in enumerate(sorted(b["cutoff"].unique()))}
        folds = b.groupby("cutoff")["date"].agg(test_start="min", test_end="max").reset_index()
        folds["fold"] = folds["cutoff"].map(FOLD_NAME)
        b["closed"] = closed_flag(b, BT1_MODEL)
        parts = [b[["warehouse", "date", "cutoff", "closed", "y"]].assign(series="orders", model=m, p50=b[m].clip(lower=0), p90=b[f"{m}-p90"])
                 for m in MODELS]
        bt = pd.concat(parts, ignore_index=True).rename(columns={"y": "y_actual"})
        bt["fold"] = bt["cutoff"].map(FOLD_NAME)
        bt["p90"] = np.fmax(bt["p90"], bt["p50"])
        _log(log, "bt1_backtest_long", len(b), len(bt), f"mô hình: {MODELS}; fold: " +
             ", ".join(f"{r.fold} cutoff {r.cutoff.date()} ({r.test_start.date()}→{r.test_end.date()})" for r in folds.itertuples()))
        if folds["test_end"].max() != as_of:
            _log(log, "warning_last_fold", None, None, f"⚠ fold cuối của bt1_backtest kết thúc {folds['test_end'].max().date()} ≠ as_of")

    # ---- 2.2 lưới kế hoạch ----
    grid = pd.MultiIndex.from_product([WAREHOUSES, pd.date_range(PLAN_START, PLAN_END)], names=["warehouse", "date"]).to_frame(index=False)
    grid = grid.merge(fc_orders[["warehouse", "date", "p50", "p90"]], on=["warehouse", "date"], how="left")
    grid["note"] = ""
    miss = grid["p50"].isna()
    for i in grid.index[miss]:
        w, dd = grid.at[i, "warehouse"], grid.at[i, "date"]
        src = fc_orders[(fc_orders["warehouse"] == w) & (fc_orders["date"] == dd - pd.Timedelta(days=7))]
        if len(src) != 1:
            raise ValueError(f"{BT_ID}: fc_orders thiếu {w} {dd.date()} và không bù được bằng cùng thứ tuần trước")
        grid.loc[i, ["p50", "p90"]] = src[["p50", "p90"]].values[0]
        grid.at[i, "note"] = f"BT1 thiếu ngày này: dùng dự báo {(dd - pd.Timedelta(days=7)):%d/%m} (cùng thứ)"
    _log(log, "plan_grid", len(fc_orders), len(grid), f"{int(miss.sum())} kho-ngày thiếu dự báo được bù bằng cùng thứ tuần trước")
    grid["closed"] = closed_flag(grid, "p50")
    grid.loc[grid["closed"] == 1, ["p50", "p90"]] = np.nan
    grid["p90"] = np.fmax(grid["p90"], grid["p50"])
    is_open = grid["closed"] == 0
    # ---- 2.3 kiểm tra ----
    if not grid.loc[is_open, ["p50", "p90"]].notna().all().all() or not (grid.loc[is_open, "p50"] > 0).all():
        raise ValueError(f"{BT_ID}: có ngày mở cửa không có dự báo hoặc P50 = 0")
    if is_eval:
        chk = bt[(bt["model"] == BT1_MODEL) & (bt["closed"] == 0)].merge(train[["warehouse", "date", "orders"]], on=["warehouse", "date"], how="left")
        if not np.allclose(chk["y_actual"], chk["orders"].fillna(0)):
            raise ValueError(f"{BT_ID}: số thật trong bt1_backtest không khớp orders_daily – BT1 và BT2 phải dùng cùng snapshot")

    # ---- 3.1 tham số ----
    P = d["workforce_params"].set_index("warehouse")
    COT = ["items_per_order", "picks_per_hour", "shift_hours", "overtime_multiplier", "orders_per_driver_shift"]
    for c in COT:
        if P[c].isna().any() or P[c].nunique() != 1:
            raise ValueError(f"{BT_ID}: workforce_params.{c} phải có cùng một giá trị cho mọi kho (giả định của notebook)")
    PARAMS = {c: float(P[c].iloc[0]) for c in COT}
    for k, v in cfg["assumed_defaults"].items():
        PARAMS[k] = float(P[k].iloc[0]) if k in P.columns else float(v)
    WAGE = P["hourly_wage_eur"].astype(float).to_dict()
    if any(pd.isna(WAGE.get(w)) for w in WAREHOUSES):
        raise ValueError(f"{BT_ID}: thiếu lương giờ cho kho")
    _log(log, "params", len(P), len(PARAMS), f"ASSUMED: lương {WAGE}; tham số {PARAMS}")

    HOURS_PER_ORDER = PARAMS["items_per_order"] / PARAMS["picks_per_hour"]
    SHIFTS = {"morning": PARAMS["morning_share"], "afternoon": 1 - PARAMS["morning_share"]}
    SHIFT_TABLE = pd.DataFrame({"shift": list(SHIFTS), "share": list(SHIFTS.values())})
    HS = PARAMS["shift_hours"]; OT_CAP = PARAMS["overtime_cap"]; OT_MULT = PARAMS["overtime_multiplier"]
    PENALTY = PARAMS["shortage_penalty"]
    GOOD_FRIDAY = {y: pd.Timestamp(easter(y)) - pd.Timedelta(days=2) for y in range(pd.Timestamp(cfg["train_start"]).year, PLAN_END.year + 1)}
    PRE_EASTER_DAYS = set(int(k) for k in cfg["pre_easter_days"])
    PERCENTILES = np.asarray(cfg["percentiles"], dtype=float)
    SOLVE_LOG: list = []

    # ---- 4.2 số đơn → người ----
    def staff_from_orders(x, orders_col, out_col, g=None):
        g = HOURS_PER_ORDER if g is None else g
        k = x.merge(SHIFT_TABLE, how="cross")
        hours = k[orders_col] * g * k["share"]
        if not hours[k["closed"] == 0].notna().all():
            raise ValueError(f"{BT_ID}: thiếu số đơn ở cột {orders_col}")
        k[out_col] = np.where(k["closed"] == 1, 0, np.ceil(hours / HS)).astype(int)
        return k[["warehouse", "date", "shift", "closed", out_col]]

    # ---- 4.3 quy tắc cũ ----
    def last_same_weekday(data, cutoff):
        x = data[(data["date"] <= cutoff) & data["orders"].notna()][["warehouse", "date", "orders"]].copy()
        x["weekday"] = x["date"].dt.dayofweek
        x = x.sort_values("date").groupby(["warehouse", "weekday"]).tail(1)
        return x.rename(columns={"orders": "last_week"})[["warehouse", "weekday", "last_week"]]

    # ---- 4.4 dự phòng Phục Sinh ----
    def baseline_level(w, day, cutoff):
        prev = [day - pd.Timedelta(days=7 * k) for k in range(1, 5)]
        x = train[(train["warehouse"] == w) & train["date"].isin(prev) & (train["date"] <= cutoff) & train["orders"].notna() &
                  (train["holiday"] == 0) & (train["shops_closed"] == 0)]
        return x["orders"].median() if len(x) >= 3 else np.nan

    def easter_uplift(w, k, year):
        ratios = []
        for y in (year - 2, year - 1):
            if y not in GOOD_FRIDAY:
                continue
            day = GOOD_FRIDAY[y] + pd.Timedelta(days=k)
            actual = train.loc[(train["warehouse"] == w) & (train["date"] == day), "orders"]
            base = baseline_level(w, day, day - pd.Timedelta(days=1))
            if len(actual) and pd.notna(actual.iloc[0]) and pd.notna(base):
                ratios.append(actual.iloc[0] / base)
        return float(np.mean(ratios)) if ratios else np.nan

    def add_easter_buffer(x, cutoff):
        x = x.copy()
        x["orders_hol"] = np.nan
        for i, r in x.iterrows():
            year = r["date"].year
            if year not in GOOD_FRIDAY or r["closed"] == 1:
                continue
            k = (r["date"] - GOOD_FRIDAY[year]).days
            if k in PRE_EASTER_DAYS:
                up = max(1.0, easter_uplift(r["warehouse"], k, year))
                x.at[i, "orders_hol"] = baseline_level(r["warehouse"], r["date"], cutoff) * up
        x["orders_p50_hol"] = np.fmax(x["orders_p50"], x["orders_hol"])
        x["orders_p90_hol"] = np.fmax(x["orders_p90"], x["orders_hol"])
        return x

    # ---- 4.6 mẫu ca 5/2 ----
    def shift_patterns(open_days):
        op = sorted(open_days)
        off = len(op) - 5
        if off <= 0:
            return [set(op)]
        if off == 1:
            return [set(op) - {dd} for dd in op]
        return [set(op) - {op[i], op[(i + 1) % len(op)]} for i in range(len(op))]

    # ---- 4.7 MIP cải tiến ----
    def mip_improved(xk, errors, penalty, g=None, tag="", e_values=None):
        g = HOURS_PER_ORDER if g is None else g
        xk = xk.sort_values("date").reset_index(drop=True)
        w = xk["warehouse"].iloc[0]; wage = WAGE[w]
        e = np.asarray(e_values, float) if e_values is not None else np.percentile(errors, PERCENTILES)
        prob = pulp.LpProblem("mip_improved", pulp.LpMinimize)
        on, objective = {}, []
        for s, share in SHIFTS.items():
            for bb in range(int(np.ceil(len(xk) / 7))):
                block = xk.iloc[7 * bb: 7 * bb + 7]
                pos_open = [i - 7 * bb for i in block.index if block.at[i, "closed"] == 0]
                pats = shift_patterns(pos_open)
                y = [pulp.LpVariable(f"y_{s}_{bb}_{p}", lowBound=0, cat="Integer") for p in range(len(pats))]
                objective.append(pulp.lpSum(y) * min(5, len(pos_open)) * HS * wage)
                for i in block.index:
                    on[(s, i)] = pulp.lpSum(y[p] for p, m in enumerate(pats) if (i - 7 * bb) in m)
            for i in xk.index:
                if xk.at[i, "closed"] == 1:
                    continue
                for q, eq in enumerate(e):
                    need = xk.at[i, "orders_p50_hol"] * (1 + eq) * g * share
                    ot = pulp.LpVariable(f"ot_{s}_{i}_{q}", lowBound=0)
                    sh = pulp.LpVariable(f"sh_{s}_{i}_{q}", lowBound=0)
                    prob += ot <= OT_CAP * HS * on[(s, i)]
                    prob += HS * on[(s, i)] + ot + sh >= need
                    objective.append((OT_MULT * wage * ot + penalty * wage * sh) / len(e))
        prob += pulp.lpSum(objective)
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=cfg["solver_time_limit"], gapRel=cfg["solver_gap_rel"], threads=max(1, int(cfg.get("solver_threads", 1))))
        prob.solve(solver)
        if pulp.LpStatus[prob.status] != "Optimal":
            raise RuntimeError(f"{BT_ID}: MIP cải tiến không tìm được nghiệm cho {w} ({tag}): {pulp.LpStatus[prob.status]}")
        SOLVE_LOG.append({"run": tag, "warehouse": w, "status": pulp.LpStatus[prob.status], "proven": prob.sol_status == 1,
                          "objective": float(pulp.value(prob.objective))})
        return pd.DataFrame([{"warehouse": w, "date": xk.at[i, "date"], "shift": s,
                              "mip_new": 0 if xk.at[i, "closed"] == 1 else int(round(pulp.value(on[(s, i)])))}
                             for s in SHIFTS for i in xk.index])

    def plan_rule(x, g=None):
        return staff_from_orders(x, "orders_rule", "rule", g)

    def plan_mip_new(x, errors, penalty=PENALTY, g=None, tag="", e_values=None):
        res = pd.concat([mip_improved(xk, errors, penalty, g, tag, e_values) for _, xk in x.groupby("warehouse")], ignore_index=True)
        return res.merge(x[["warehouse", "date", "closed"]], on=["warehouse", "date"])[["warehouse", "date", "shift", "closed", "mip_new"]]

    def plan_oracle(x, g=None):
        g = HOURS_PER_ORDER if g is None else g
        k = x.merge(SHIFT_TABLE, how="cross")
        k["oracle"] = np.where(k["closed"] == 1, 0, np.ceil(k["orders_actual"].fillna(0) * g * k["share"] / HS)).astype(int)
        return k[["warehouse", "date", "shift", "closed", "oracle"]]

    # ---- 4.9 mô phỏng chi phí ----
    def simulate_cost(people, hours_needed, wage, penalty):
        people = np.asarray(people, dtype=float); hours_needed = np.asarray(hours_needed, dtype=float); wage = np.asarray(wage, dtype=float)
        regular_h = people * HS
        excess = np.maximum(hours_needed - regular_h, 0)
        overtime_h = np.minimum(excess, OT_CAP * regular_h)
        short_h = excess - overtime_h
        idle_h = np.maximum(regular_h - hours_needed, 0)
        cost = regular_h * wage + overtime_h * OT_MULT * wage + short_h * penalty * wage
        return {"regular_h": regular_h, "overtime_h": overtime_h, "idle_h": idle_h, "short_h": short_h, "cost": cost}

    def evaluate(plan, actual, penalty=PENALTY, g=None):
        g = HOURS_PER_ORDER if g is None else g
        x = plan.merge(actual[["warehouse", "date", "orders_actual"]], on=["warehouse", "date"], how="left")
        x["hours_actual"] = x["orders_actual"].fillna(0) * g * x["shift"].map(SHIFTS)
        x["wage"] = x["warehouse"].map(WAGE)
        out = []
        for c in [c for c in plan.columns if c in POLICY_NAME]:
            res = simulate_cost(x[c], x["hours_actual"], x["wage"], penalty)
            out.append(x[["warehouse", "date", "shift", "closed", "orders_actual", "hours_actual"]].assign(policy=c, staff=x[c], **res))
        return pd.concat(out, ignore_index=True)

    def summarise(detail, by=("policy",)):
        gp = detail.groupby(list(by)).agg(regular_h=("regular_h", "sum"), overtime_h=("overtime_h", "sum"), idle_h=("idle_h", "sum"),
                                          short_h=("short_h", "sum"), cost=("cost", "sum"),
                                          short_shifts=("short_h", lambda s: (s > 0.01).sum()), n_shifts=("short_h", "size"))
        orders = detail[detail["shift"] == "morning"].groupby(list(by))["orders_actual"].sum()
        gp["eur_per_order"] = gp["cost"] / orders
        gp["pct_short_shifts"] = gp["short_shifts"] / gp["n_shifts"] * 100
        return gp.drop(columns=["short_shifts", "n_shifts"])

    if is_eval:
        # ---- 4.10 + 7.1 sai số ngoài mẫu ----
        MAIN_FOLDS = folds["fold"].tolist()
        lgb = bt[(bt["series"] == "orders") & (bt["model"] == BT1_MODEL)].copy()
        lgb["e"] = np.where(lgb["closed"] == 0, (lgb["y_actual"] - lgb["p50"]) / lgb["p50"], np.nan)

        def errors_before(f):
            cut = folds.set_index("fold").at[f, "cutoff"]
            past = folds.loc[folds["test_end"] <= cut, "fold"].tolist()
            e = lgb[lgb["fold"].isin(past) & (lgb["closed"] == 0)]["e"].dropna().values
            if len(e) >= int(cfg["min_past_errors"]):
                return e
            g = lgb[(lgb["fold"] == f) & (lgb["closed"] == 0)]
            sigma = float(np.median(g["p90"] / g["p50"] - 1)) / NormalDist().inv_cdf(0.9)
            return np.array([NormalDist(0, sigma).inv_cdf(q) for q in np.linspace(0.005, 0.995, 199)])
        ERRORS_ALL = lgb[lgb["fold"].isin(MAIN_FOLDS) & (lgb["closed"] == 0)]["e"].dropna().values
        ERRORS_BY_FOLD = {f: errors_before(f) for f in folds["fold"]}
        _log(log, "bt1_errors", len(lgb), len(ERRORS_ALL), "kịch bản sai số theo fold: " +
             ", ".join(f"{f}={len(v)}{' (xấp xỉ chuẩn)' if len(v) == 199 else ''}" for f, v in ERRORS_BY_FOLD.items()))

    # ---- 6.1 nhu cầu kỳ kế hoạch + 6.4/6.10 kế hoạch ----
    grid["weekday"] = grid["date"].dt.dayofweek
    grid = grid.merge(last_same_weekday(train, as_of), on=["warehouse", "weekday"], how="left")
    grid["orders_rule"] = grid["last_week"] * (1 + PARAMS["rule_buffer"])
    grid = grid.rename(columns={"p50": "orders_p50", "p90": "orders_p90"})
    grid = add_easter_buffer(grid, as_of)
    _log(log, "easter_buffer", len(grid), int(grid["orders_hol"].notna().sum()), "kho-ngày có dự phòng 3 ngày trước Good Friday")
    k_ = grid.merge(SHIFT_TABLE, how="cross")
    plan = k_[["warehouse", "date", "shift", "closed"]].copy()
    plan["hours_p50"] = np.where(k_["closed"] == 0, k_["orders_p50"] * HOURS_PER_ORDER * k_["share"], 0.0)
    plan["hours_p90"] = np.where(k_["closed"] == 0, k_["orders_p90"] * HOURS_PER_ORDER * k_["share"], 0.0)
    plans = {}
    if "rule" in POLICIES:
        plans["rule"] = plan_rule(grid)
    if "mip_new" in POLICIES:
        plans["mip_new"] = (plan_mip_new(grid, ERRORS_ALL, tag="plan") if is_eval else
                            plan_mip_new(grid, None, tag="plan", e_values=frozen["error_percentiles"]))
    for p in POLICIES:
        plan = plan.merge(plans[p].drop(columns="closed"), on=["warehouse", "date", "shift"])
    plan["wage"] = plan["warehouse"].map(WAGE)

    if is_eval:
        # ---- 7.2 nhu cầu tại từng fold ----
        BT_DEMAND = {}
        for _, fd in folds.iterrows():
            f, cutoff = fd["fold"], fd["cutoff"]
            x = lgb[lgb["fold"] == f][["warehouse", "date", "closed", "y_actual", "p50", "p90"]].rename(
                columns={"p50": "orders_p50", "p90": "orders_p90", "y_actual": "orders_actual"})
            x["weekday"] = x["date"].dt.dayofweek
            x = x.merge(last_same_weekday(train, cutoff), on=["warehouse", "weekday"], how="left")
            x["orders_rule"] = x["last_week"] * (1 + PARAMS["rule_buffer"])
            BT_DEMAND[f] = add_easter_buffer(x, cutoff)

        BT_PLANNER = {}
        if "rule" in POLICIES:
            BT_PLANNER["rule"] = lambda x, f, g, pen, tag: plan_rule(x, g)
        if "mip_new" in POLICIES:
            BT_PLANNER["mip_new"] = lambda x, f, g, pen, tag: plan_mip_new(x, ERRORS_BY_FOLD[f], pen, g, tag=f"{tag}:{f}")
        BT_PLANNER["oracle"] = lambda x, f, g, pen, tag: plan_oracle(x, g)

        def backtest_policy(planner, g=None, penalty=PENALTY, tag="backtest"):
            res = []
            for f in MAIN_FOLDS:
                x = BT_DEMAND[f]
                res.append(evaluate(planner(x, f, g, penalty, tag), x, penalty, g).assign(fold=f))
            return pd.concat(res, ignore_index=True)

        bt_all = pd.concat([backtest_policy(pl) for pl in BT_PLANNER.values()], ignore_index=True)
        main = summarise(bt_all)
        if "rule" in main.index:
            main["vs_rule_pct"] = (main["cost"] / main.loc["rule", "cost"] - 1) * 100

        # ---- 7.14 chọn phương án ----
        candidates = main.loc[POLICIES]
        feasible = candidates[candidates["short_h"] <= SHORT_TOL]
        pool = feasible if len(feasible) else candidates[candidates["short_h"] == candidates["short_h"].min()]
        CHOSEN = pool["cost"].idxmin()
        _log(log, "policy_selection", len(candidates), len(feasible),
             f"khả thi (giờ thiếu ≤ {SHORT_TOL}): {list(feasible.index)}; chọn {CHOSEN}"
             + ("" if len(feasible) else " ⚠ không phương án nào có giờ thiếu = 0 → chọn phương án ít thiếu nhất"))

        # ---- 8.x độ nhạy ----
        ORDER = POLICIES + ["oracle"]
        SCEN = {f"phạt ×{PENALTY:g} (gốc)": main[["cost", "short_h"]]}
        for sc in cfg["sensitivity"]:
            pen = float(sc.get("penalty", PENALTY))
            g = PARAMS["items_per_order"] / float(sc["picks_per_hour"]) if "picks_per_hour" in sc else None
            dd = pd.concat([backtest_policy(pl, g, pen, tag=f"sens {sc['scenario']}") for pl in BT_PLANNER.values()], ignore_index=True)
            SCEN[sc["scenario"]] = summarise(dd)[["cost", "short_h"]]
        rows = []
        for sc, t in SCEN.items():
            sub = t.loc[POLICIES]
            ok = sub[sub["short_h"] <= SHORT_TOL]
            best = (ok if len(ok) else sub[sub["short_h"] == sub["short_h"].min()])["cost"].idxmin()
            rank = sub["cost"].rank(method="min")
            for k in [c for c in ORDER if c in t.index]:
                rows.append({"scenario": sc, "policy_key": k, "policy": POLICY_NAME[k], "cost_eur": round(float(t.at[k, "cost"]), 0),
                             "short_h": round(float(t.at[k, "short_h"]), 1), "rank_cost": (int(rank[k]) if k in rank.index else pd.NA),
                             "selected_under_rule": k == best})
        sens = pd.DataFrame(rows)
        sens["rank_cost"] = sens["rank_cost"].astype("Int64")
    else:
        CHOSEN = POLICIES[0]
        _log(log, "policy_frozen", None, None, f"phương án đã chốt: {CHOSEN}")

    # ---- 11.1 tài xế + 11.2 / 12.1 kế hoạch ----
    drivers = grid[["warehouse", "date", "closed", "orders_p50", "orders_p90", "orders_p90_hol"]].copy()
    drivers["orders_per_driver_shift"] = PARAMS["orders_per_driver_shift"]
    drivers["drivers_needed"] = np.where(drivers["closed"] == 1, 0,
                                         np.ceil(drivers["orders_p90_hol"].fillna(0) / PARAMS["orders_per_driver_shift"])).astype(int)
    driver_plan = drivers.assign(orders_p50=drivers["orders_p50"].fillna(0).round(0), orders_p90=drivers["orders_p90"].fillna(0).round(0),
                                 orders_p90_used=drivers["orders_p90_hol"].fillna(0).round(0))[
        ["warehouse", "date", "orders_p50", "orders_p90", "orders_per_driver_shift", "drivers_needed", "orders_p90_used", "closed"]]
    staff_plan = plan[["warehouse", "date", "shift", "closed", CHOSEN, "wage"]].rename(columns={CHOSEN: "staff"}).assign(policy=CHOSEN)
    staff_plan["staff"] = np.where(staff_plan["closed"] == 1, 0, staff_plan["staff"]).astype(int)
    staff_plan["cost_eur"] = np.where(staff_plan["closed"] == 1, 0.0, staff_plan["staff"] * HS * staff_plan["wage"]).round(2)
    om = grid.set_index(["warehouse", "date"])[ORDERS_USED[CHOSEN]].round(0)
    staff_plan["orders_used"] = staff_plan.set_index(["warehouse", "date"]).index.map(om).fillna(0).values
    staff_plan["policy_name"] = POLICY_NAME[CHOSEN]
    staff_plan = staff_plan.rename(columns={"wage": "hourly_wage_eur"})[
        ["warehouse", "date", "shift", "staff", "policy", "cost_eur", "policy_name", "closed", "hourly_wage_eur", "orders_used"]]
    staff_plan = staff_plan.sort_values(["warehouse", "date", "shift"]).reset_index(drop=True)
    driver_plan = driver_plan.sort_values(["warehouse", "date"]).reset_index(drop=True)
    _log(log, "plan", len(grid), len(staff_plan), f"{int(staff_plan['staff'].sum())} người-ca, lương kế hoạch {staff_plan['cost_eur'].sum():,.0f} EUR; "
                                                  f"{int(driver_plan['drivers_needed'].sum())} ca tài xế")

    if is_eval:
        # ---- 12.2 file đánh giá ----
        LEVEL_MAIN = f"Backtest {'+'.join(MAIN_FOLDS)} (chọn: chi phí thấp nhất với giờ thiếu = 0)"
        comp = main.loc[[c for c in ORDER if c in main.index]].copy()
        comp.insert(0, "policy", [POLICY_NAME[c] for c in comp.index]); comp.insert(0, "policy_key", comp.index)
        comp.insert(0, "evaluation", LEVEL_MAIN)
        comp = comp.reset_index(drop=True).rename(columns={"cost": "cost_eur", "vs_rule_pct": "vs_rule_%"})
        comp["role"] = comp["policy_key"].map({"rule": "baseline", "mip_new": "final", "oracle": "reference"})
        comp["selected"] = comp["policy_key"] == CHOSEN
        comp = comp.round(2)
        byw = summarise(bt_all, ("warehouse", "policy")).reset_index().rename(columns={"policy": "policy_key", "cost": "cost_eur"})
        byw.insert(2, "policy", byw["policy_key"].map(POLICY_NAME))
        byw["selected"] = byw["policy_key"] == CHOSEN
        byw = byw.round(2)
    solve_log = pd.DataFrame(SOLVE_LOG, columns=["run", "warehouse", "status", "proven", "objective"])
    n_unproven = int((~solve_log["proven"].astype(bool)).sum()) if len(solve_log) else 0
    _log(log, "solver", None, len(solve_log), f"{len(solve_log) - n_unproven}/{len(solve_log)} lần giải MIP cải tiến đạt tối ưu chứng minh "
                                             f"(còn lại = nghiệm khả thi tốt nhất khi hết {cfg['solver_time_limit']} s)")

    run_log = pd.DataFrame(log, columns=["step", "rows_in", "rows_out", "note"])
    run_log["rows_in"] = run_log["rows_in"].astype("Int64"); run_log["rows_out"] = run_log["rows_out"].astype("Int64")
    outputs = {"staff_plan": staff_plan, "driver_plan": driver_plan, "bt2_solve_log": solve_log, "run_log": run_log}
    if is_eval:
        outputs.update({"bt2_policy_comparison": comp, "bt2_policy_by_warehouse": byw, "bt2_sensitivity": sens})
        outputs["_params"] = {"chosen_policy": CHOSEN,
                              "error_percentiles": [round(float(v), 8) for v in np.percentile(ERRORS_ALL, PERCENTILES)]}
    validate_outputs(outputs, cfg)
    return outputs


def validate_outputs(outputs: dict[str, pd.DataFrame], config: dict) -> None:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    is_eval = cfg.get("mode", "evaluate") == "evaluate"
    for name in (OUTPUTS if is_eval else FAST_OUTPUTS):
        if name not in outputs or not isinstance(outputs[name], pd.DataFrame):
            raise ValueError(f"{BT_ID}: thiếu output '{name}'")
    as_of = pd.Timestamp(cfg["as_of"]); H = int(cfg["horizon"])
    lo, hi = as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H)
    spec = {
        "staff_plan": (["warehouse", "date", "shift", "staff", "policy", "cost_eur"], ["warehouse", "date", "shift"], ["staff", "cost_eur"]),
        "driver_plan": (["warehouse", "date", "orders_p50", "orders_p90", "orders_per_driver_shift", "drivers_needed"], ["warehouse", "date"],
                        ["orders_p50", "orders_p90", "orders_per_driver_shift", "drivers_needed"]),
        "bt2_policy_comparison": (["evaluation", "policy", "cost_eur", "short_h", "selected"], ["evaluation", "policy"], ["cost_eur", "short_h"]),
        "bt2_policy_by_warehouse": (["warehouse", "policy", "cost_eur", "short_h", "selected"], ["warehouse", "policy"], ["cost_eur", "short_h"]),
        "bt2_sensitivity": (["scenario", "policy", "cost_eur", "short_h", "selected_under_rule"], ["scenario", "policy"], ["cost_eur", "short_h"]),
        "run_log": (["step", "rows_in", "rows_out", "note"], [], []),
    }
    for name, (cols, keys, nonneg) in spec.items():
        if name not in outputs:
            continue
        df = outputs[name]
        miss = [c for c in cols if c not in df.columns]
        if miss:
            raise ValueError(f"{BT_ID}: output '{name}' thiếu cột {miss}")
        if keys and df.duplicated(keys).any():
            raise ValueError(f"{BT_ID}: output '{name}' trùng khoá {keys}")
        if name != "run_log" and df[cols].isna().any().any():
            raise ValueError(f"{BT_ID}: output '{name}' có NaN ở cột hợp đồng")
        for c in nonneg:
            if (pd.to_numeric(df[c]) < -1e-9).any():
                raise ValueError(f"{BT_ID}: output '{name}'.{c} có giá trị âm")
    sp, dp = outputs["staff_plan"], outputs["driver_plan"]
    for name, df in (("staff_plan", sp), ("driver_plan", dp)):
        dts = pd.to_datetime(df["date"])
        if dts.min() != lo or dts.max() != hi:
            raise ValueError(f"{BT_ID}: {name} sai khoảng ngày kế hoạch")
    n_wh = dp["warehouse"].nunique()
    if cfg.get("warehouses") is not None and set(dp["warehouse"]) != set(cfg["warehouses"]):
        raise ValueError(f"{BT_ID}: driver_plan thiếu kho")
    if len(dp) != n_wh * H or len(sp) != n_wh * H * 2 or set(sp["warehouse"]) != set(dp["warehouse"]):
        raise ValueError(f"{BT_ID}: staff_plan phải đủ kho × {H} ngày × 2 ca, driver_plan đủ kho × {H} ngày")
    if not np.allclose(sp["staff"], np.round(sp["staff"])) or not np.allclose(dp["drivers_needed"], np.round(dp["drivers_needed"])):
        raise ValueError(f"{BT_ID}: staff/drivers_needed phải là số nguyên")
    if "closed" in sp.columns and not sp.loc[sp["closed"] == 1, ["staff", "cost_eur"]].eq(0).all().all():
        raise ValueError(f"{BT_ID}: ngày đóng cửa phải có staff = 0, cost_eur = 0")
    if "closed" in dp.columns and not dp.loc[dp["closed"] == 1, "drivers_needed"].eq(0).all():
        raise ValueError(f"{BT_ID}: ngày đóng cửa phải có 0 tài xế")
    if (dp["orders_p90"] + 1e-9 < dp["orders_p50"]).any() or (dp["orders_per_driver_shift"] <= 0).any():
        raise ValueError(f"{BT_ID}: driver_plan orders_p90 < orders_p50 hoặc orders_per_driver_shift ≤ 0")
    if not is_eval:
        if sp["policy"].nunique() != 1:
            raise ValueError(f"{BT_ID}: staff_plan phải dùng đúng 1 phương án")
        return
    cmp_df = outputs["bt2_policy_comparison"]
    if int(cmp_df["selected"].sum()) != 1 or sp["policy"].nunique() != 1 or \
            sp["policy"].iloc[0] != cmp_df.loc[cmp_df["selected"], "policy_key"].iloc[0]:
        raise ValueError(f"{BT_ID}: phải có đúng 1 phương án selected và staff_plan dùng đúng phương án đó")
