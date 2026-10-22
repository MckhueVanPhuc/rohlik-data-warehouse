"""BT4 – Dự báo nhu cầu SKU 14 ngày (16/03 → 29/03/2024) kèm phân vị P20…P90 – bản tinh gọn để tích hợp pipeline.

Thuật toán giữ nguyên notebook final `final8/bt4/BT4_final.ipynb` (phương án thành viên
`src/BT4_member_Integrated_Forecasting.ipynb`), áp phạm vi 7 kho:
  Sales/Prices/Promotions/Product/Calendar/Weights + lost_sales (BT3: nhãn est_demand) + order_index BT1
  → đặc trưng tại ngày gốc (active roster 7 ngày, lag/rolling est_demand, giá, giảm giá, availability, thiếu hàng)
  → panel direct-horizon 14 ngày → LightGBM regression_l1 (early stopping F1+F2) + 4 baseline
  → hiệu chỉnh hệ số (tìm F1, chấp nhận nếu F2 giảm ≥ 0,5%) → F3 (02→15/03) dự báo bằng mô hình học lại tới 01/03, chỉ báo cáo
  → P90 = P50 + offset theo horizon (thành viên) hoặc conformal tỷ số theo L1 (chọn theo pinball q=0,9 trên F1+F2);
    P20…P80 conformal tỷ số theo L1 → học lại toàn bộ ≤ 15/03 → dự báo 16–29/03 → validate.
SQL DuckDB của thành viên được viết lại bằng pandas (cùng định nghĩa cửa sổ). Không đọc/ghi file, không biến toàn cục trạng thái.

Hai chế độ (D06): mode="models" học 1 mô hình LightGBM_L1 trên mọi ngày gốc ≤ as_of với số cây, hệ số hiệu chỉnh,
cách tính P90 và bảng tỷ số phân vị đã chốt (frozen) → chỉ ra fc_sku; order_index lịch sử = quan sát (không cần bt1_backtest).
mode="evaluate" chạy đủ backtest F1–F3, baseline, hiệu chỉnh, conformal và trả "_params".
"""
from __future__ import annotations

import copy
import warnings
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

BT_ID = "BT4"
DISCOUNT_COLS = [f"type_{i}_discount" for i in range(7)]
CAL = ["holiday", "shops_closed", "school_holidays", "winter_school_holidays"]
QS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
PCOLS = [f"p{int(round(q * 100))}" for q in QS]
QCOLS = [f"q{int(round(q * 100))}" for q in QS]
FOLDS = ["F1", "F2", "F3"]
VALID_FOLDS = ["F1", "F2"]
TEST_FOLD = "F3"
MODEL_NAME = "LightGBM_L1_BT1_BT3"

REQUIRED_INPUTS = ["sku_sales_daily", "prices", "promotions", "product_master", "calendar", "sku_weights",
                   "lost_sales", "bt1_backtest", "fc_orders"]
OPTIONAL_INPUTS: list[str] = []
UPSTREAM = {"lost_sales": ("BT3", "lost_sales"), "bt1_backtest": ("BT1", "bt1_backtest"), "fc_orders": ("BT1", "fc_orders")}
OUTPUTS = ["fc_sku", "bt4_backtest", "bt4_quantile_ratios", "bt4_model_comparison", "run_log"]
FAST_INPUTS = ["sku_sales_daily", "prices", "promotions", "product_master", "calendar", "sku_weights", "lost_sales", "fc_orders"]
FAST_OUTPUTS = ["fc_sku", "run_log"]

REQUIRED_COLUMNS = {
    "sku_sales_daily": ["unique_id", "date", "warehouse", "sales", "total_orders"],
    "prices": ["unique_id", "date", "sell_price_main"],
    "promotions": ["unique_id", "date"] + DISCOUNT_COLS,
    "product_master": ["unique_id", "warehouse", "L1_category_name_en"],
    "calendar": ["warehouse", "date"] + CAL,
    "sku_weights": ["unique_id", "weight"],
    "lost_sales": ["unique_id", "date", "warehouse", "L1", "sales", "availability", "final_price", "est_demand", "lost_units"],
    "bt1_backtest": ["warehouse", "date", "cutoff", "y", "series"],
    "fc_orders": ["warehouse", "date", "series", "p50", "p90", "model"],
}
ACTUAL_DATED = ["sku_sales_daily", "prices", "promotions", "lost_sales", "bt1_backtest"]   # train_start ≤ date ≤ as_of
FORECAST_DATED = ["fc_orders"]                                                              # as_of < date ≤ as_of + horizon

ALL_WAREHOUSES = ["Brno_1", "Budapest_1", "Frankfurt_1", "Munich_1", "Prague_1", "Prague_2", "Prague_3"]

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",
    "train_start": "2020-12-05",
    "horizon": 14,
    "seed": 42,
    "n_jobs": 1,
    "warehouses": None,
    "expected_warehouses": ALL_WAREHOUSES,
    "currency_by_warehouse": {"Prague_1": "CZK", "Prague_2": "CZK", "Prague_3": "CZK", "Brno_1": "CZK",
                              "Budapest_1": "HUF", "Munich_1": "EUR", "Frankfurt_1": "EUR"},
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},
    "active_recency_days": 6,          # SKU active nếu có quan sát trong 7 ngày đến ngày gốc
    "min_history_days": 56,
    "n_estimators": 900,
    "early_stopping_rounds": 75,
    "lgb_params": {"objective": "regression_l1", "learning_rate": 0.04, "num_leaves": 63, "max_depth": -1,
                   "min_child_samples": 200, "subsample": 0.85, "colsample_bytree": 0.80, "reg_alpha": 0.05,
                   "reg_lambda": 1.0, "verbosity": -1, "deterministic": True, "force_row_wise": True},
    "calibration_grid": [0.85, 1.25, 0.005],
    "calibration_min_gain": 0.005,
    "stockout_threshold": 0.99,
    "price_source": "last_known_as_of",
    "required_inputs": REQUIRED_INPUTS,
    "mode": "evaluate",               # "models" | "evaluate"
    "frozen": None,                   # {"best_iter", "factor", "p90_method", "quantile_ratios": [...], "offsets": {...}, "g_off"}
}


def _merge_config(config):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    for k, v in (config or {}).items():
        cfg[k] = copy.deepcopy(v)
    return cfg


def _scope(cfg):
    return list(cfg["warehouses"]) if cfg.get("warehouses") else list(cfg["expected_warehouses"])


class _Log:
    def __init__(self):
        self.rows = []

    def add(self, step, rows_in, rows_out, note=""):
        self.rows.append({"step": step, "rows_in": int(rows_in), "rows_out": int(rows_out), "note": str(note)})

    def frame(self):
        return pd.DataFrame(self.rows, columns=["step", "rows_in", "rows_out", "note"])


def calculate_metrics(y_true, y_pred, weights):
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    w = np.nan_to_num(np.asarray(weights, float), nan=1.0)
    ok = np.isfinite(y_true) & np.isfinite(y_pred) & (w >= 0)
    y_true, y_pred, w = y_true[ok], y_pred[ok], w[ok]
    err = y_pred - y_true
    wa = max(np.sum(w * np.abs(y_true)), 1e-9)
    return {"rows": int(len(y_true)), "WMAE": float(np.sum(w * np.abs(err)) / max(np.sum(w), 1e-9)),
            "WMAPE_%": float(100 * np.sum(w * np.abs(err)) / wa), "RMSE": float(np.sqrt(np.mean(err ** 2))) if len(err) else np.nan,
            "bias_%": float(100 * np.sum(w * err) / wa)}


def weighted_quantile(values, weights, quantile):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    ok = np.isfinite(values) & np.isfinite(weights) & (weights >= 0)
    values, weights = values[ok], weights[ok]
    if len(values) == 0:
        return np.nan
    if weights.sum() <= 0:
        return float(np.quantile(values, quantile))
    order = np.argsort(values, kind="mergesort")
    values, weights = values[order], weights[order]
    pos = np.searchsorted(np.cumsum(weights), quantile * weights.sum(), side="left")
    return float(values[min(pos, len(values) - 1)])


def pinball(y, qpred, q, w):
    d = np.asarray(y, float) - np.asarray(qpred, float)
    return float(np.sum(np.asarray(w, float) * np.maximum(q * d, (q - 1) * d)) / np.sum(w))


# ----------------------------------------------------------------------------------------------------------------
# 1. Kiểm tra input + cắt mốc
# ----------------------------------------------------------------------------------------------------------------
def _check_and_cut(inputs, cfg, log):
    required = list(cfg.get("required_inputs") or REQUIRED_INPUTS)
    missing = sorted(set(required) - set(inputs))
    if missing:
        raise ValueError(f"{BT_ID}: thiếu input bắt buộc: {missing}")
    as_of, start, H = pd.Timestamp(cfg["as_of"]), pd.Timestamp(cfg["train_start"]), int(cfg["horizon"])
    fc_end = as_of + pd.Timedelta(days=H)
    out = {}
    for name in [n for n in REQUIRED_INPUTS if n in required]:
        df = inputs[name]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{BT_ID}: input '{name}' phải là pandas.DataFrame")
        miss = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
        if miss:
            raise ValueError(f"{BT_ID}: input '{name}' thiếu cột {miss}")
        df = df.copy()
        n0 = len(df)
        for c in ["date", "cutoff"]:
            if c in df.columns:
                try:
                    df[c] = pd.to_datetime(df[c])
                except Exception as e:  # noqa: BLE001
                    raise ValueError(f"{BT_ID}: cột {c} của '{name}' không chuyển được sang ngày: {e}") from e
        if name in ACTUAL_DATED:
            m = (df["date"] >= start) & (df["date"] <= as_of)
            if "cutoff" in df.columns:
                m &= df["cutoff"] <= as_of
            df = df[m]
            note = f"giữ {start.date()} ≤ date ≤ {as_of.date()}" + (" và cutoff ≤ as_of" if "cutoff" in df.columns else "")
        elif name in FORECAST_DATED:
            df = df[(df["date"] > as_of) & (df["date"] <= fc_end)]
            note = f"giữ {as_of.date()} < date ≤ {fc_end.date()}"
        elif name == "calendar":
            df = df[(df["date"] >= start) & (df["date"] <= fc_end)]
            note = f"giữ {start.date()} ≤ date ≤ {fc_end.date()} (lịch biết trước)"
        else:
            note = "không có cột ngày"
        if "unique_id" in df.columns:
            df["unique_id"] = pd.to_numeric(df["unique_id"], errors="raise").astype("int64")
        if "warehouse" in df.columns:
            df["warehouse"] = df["warehouse"].astype(str).str.strip()
        log.add(f"cut_dates:{name}", n0, len(df), note)
        out[name] = df.reset_index(drop=True)
    scope = _scope(cfg)
    for name in ["sku_sales_daily", "lost_sales", "calendar"]:
        lack = sorted(set(scope) - set(out[name]["warehouse"]))
        if lack:
            raise ValueError(f"{BT_ID}: input '{name}' không có dữ liệu cho kho {lack} (phạm vi {scope})")
    for name in [n for n in ["sku_sales_daily", "prices", "promotions", "lost_sales", "product_master", "calendar", "bt1_backtest", "fc_orders"] if n in out]:
        if "warehouse" in out[name].columns:
            n0 = len(out[name])
            out[name] = out[name][out[name]["warehouse"].isin(scope)].reset_index(drop=True)
            if n0 != len(out[name]):
                log.add(f"scope:{name}", n0, len(out[name]), f"chỉ giữ kho {sorted(scope)}")
    return out


# ----------------------------------------------------------------------------------------------------------------
# 2. Đặc trưng tại ngày gốc (tương đương SQL DuckDB ô 6.2 của thành viên)
# ----------------------------------------------------------------------------------------------------------------
def _origin_features(hist: pd.DataFrame, origins: list, recency: int) -> pd.DataFrame:
    keys = ["unique_id", "warehouse"]
    traffic = hist.drop_duplicates(["warehouse", "date"])[["warehouse", "date", "total_orders_observed", "order_index_feature"]]
    parts = []
    for o in origins:
        act = hist[(hist["date"] >= o - pd.Timedelta(days=recency)) & (hist["date"] <= o)]
        if act.empty:
            continue
        last = act.groupby(keys)["date"].max().rename("last_observed_date").reset_index()
        anchor = last.merge(hist, left_on=keys + ["last_observed_date"], right_on=keys + ["date"], how="inner")
        a = pd.DataFrame({"unique_id": anchor["unique_id"], "warehouse": anchor["warehouse"], "origin_date": o,
                          "last_observed_date": anchor["last_observed_date"],
                          "days_since_last_observation": (o - anchor["last_observed_date"]).dt.days,
                          "L1": anchor["L1"], "currency": anchor["currency"], "weight": anchor["weight"],
                          "origin_final_price": anchor["final_price"], "origin_main_price": anchor["sell_price_main"],
                          "origin_max_discount": anchor["max_discount"], "last_availability": anchor["availability"],
                          "last_demand": anchor["target_demand"], "last_sales": anchor["target_sales"]})
        t = traffic[traffic["date"] == o].rename(columns={"total_orders_observed": "origin_total_orders_observed",
                                                          "order_index_feature": "origin_order_index"}).drop(columns="date")
        a = a.merge(t, on="warehouse", how="left")
        win = hist[(hist["date"] >= o - pd.Timedelta(days=56)) & (hist["date"] <= o)]
        win = win.merge(a[keys], on=keys, how="inner")
        lag = (o - win["date"]).dt.days.to_numpy()
        dmd, av, lu = win["target_demand"].astype(float), win["availability"].astype(float), win["lost_units"].astype(float)
        f = pd.DataFrame({"unique_id": win["unique_id"].values, "warehouse": win["warehouse"].values})
        for k in [0, 1, 7, 14, 28, 56]:
            f[f"demand_lag_{k}"] = np.where(lag == k, dmd, np.nan)
        f["demand_mean_7"] = np.where(lag <= 6, dmd, np.nan)
        f["demand_mean_14"] = np.where(lag <= 13, dmd, np.nan)
        f["demand_mean_28"] = np.where(lag <= 27, dmd, np.nan)
        f["demand_std_28"] = f["demand_mean_28"]
        f["demand_mean_56"] = np.where(lag <= 55, dmd, np.nan)
        f["demand_same_dow_mean_8"] = np.where((lag >= 7) & (lag <= 56) & (lag % 7 == 0), dmd, np.nan)
        f["availability_mean_28"] = np.where(lag <= 27, av, np.nan)
        f["stockout_rate_28"] = np.where(lag <= 27, np.where(av < 0.99, 1.0, 0.0), np.nan)
        f["lost_units_56"] = np.where(lag <= 55, lu, 0.0)
        f["observed_days_28"] = np.where(lag <= 27, dmd, np.nan)
        agg = f.groupby(keys).agg(
            **{f"demand_lag_{k}": (f"demand_lag_{k}", "max") for k in [0, 1, 7, 14, 28, 56]},
            demand_mean_7=("demand_mean_7", "mean"), demand_mean_14=("demand_mean_14", "mean"),
            demand_mean_28=("demand_mean_28", "mean"), demand_std_28=("demand_std_28", "std"),
            demand_mean_56=("demand_mean_56", "mean"), demand_same_dow_mean_8=("demand_same_dow_mean_8", "mean"),
            availability_mean_28=("availability_mean_28", "mean"), stockout_rate_28=("stockout_rate_28", "mean"),
            lost_units_56=("lost_units_56", "sum"), observed_days_28=("observed_days_28", "count")).reset_index()
        parts.append(a.merge(agg, on=keys, how="left"))
    of = pd.concat(parts, ignore_index=True)
    num = of.columns.difference(["unique_id", "warehouse", "origin_date", "last_observed_date", "L1", "currency"])
    of[num] = of[num].apply(pd.to_numeric, errors="coerce").astype("float32")
    return of


def _add_target_calendar(df):
    df["target_dow"] = df["target_date"].dt.dayofweek.astype("int8")
    df["target_day"] = df["target_date"].dt.day.astype("int8")
    df["target_month"] = df["target_date"].dt.month.astype("int8")
    df["target_weekofyear"] = df["target_date"].dt.isocalendar().week.astype("int16").values
    df["target_dow_sin"] = np.sin(2 * np.pi * df["target_dow"] / 7).astype("float32")
    df["target_dow_cos"] = np.cos(2 * np.pi * df["target_dow"] / 7).astype("float32")
    for c in CAL:
        df[f"target_{c}"] = pd.to_numeric(df[f"target_{c}"], errors="coerce").fillna(0).astype("int8")
    return df


# Danh sách của notebook final (bỏ "currency" theo E6 – trùng thông tin với warehouse); cột không có trong panel tự bị bỏ như bản thành viên
FEATURE_CANDIDATES = ["unique_id", "warehouse", "L1", "horizon", "target_dow", "target_day", "target_month",
                      "target_weekofyear", "target_dow_sin", "target_dow_cos", "target_holiday", "target_closed",
                      "target_order_index", "origin_order_index", "origin_total_orders_observed",
                      "origin_final_price", "origin_main_price", "origin_max_discount", "origin_availability",
                      "demand_lag_0", "sales_lag_0", "demand_lag_1", "demand_lag_7", "demand_lag_14", "demand_lag_28", "demand_lag_56",
                      "demand_mean_7", "demand_mean_14", "demand_mean_28", "demand_std_28", "demand_mean_56", "demand_same_dow_mean_8",
                      "availability_mean_28", "stockout_rate_28", "lost_units_56", "observed_days_28", "days_since_last_observation"]


# ----------------------------------------------------------------------------------------------------------------
# 3. run_model
# ----------------------------------------------------------------------------------------------------------------
def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    evaluate = cfg["mode"] == "evaluate"
    if not evaluate:
        cfg["required_inputs"] = FAST_INPUTS
        frozen = cfg.get("frozen") or {}
        need = ["best_iter", "factor", "p90_method", "quantile_ratios"]
        if any(frozen.get(k) in (None, [], {}) for k in need):
            raise ValueError(f"{BT_ID}: chế độ models cần tham số chốt {need} – chạy `evaluate` trước "
                             "hoặc kiểm tra config/model_params/BT4.json")
    log = _Log()
    d = _check_and_cut(inputs, cfg, log)
    as_of, H, seed = pd.Timestamp(cfg["as_of"]), int(cfg["horizon"]), int(cfg["seed"])
    test_start = as_of - pd.Timedelta(days=H - 1)
    fc_dates = pd.date_range(as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H), freq="D")
    fold_origin = {f: test_start - pd.Timedelta(days=1 + H * k) for f, k in zip(FOLDS, [2, 1, 0])}
    scope, cur_map = _scope(cfg), cfg["currency_by_warehouse"]
    keys = ["unique_id", "warehouse", "date"]

    # 2.1 Sales history = sku_sales_daily LEFT JOIN prices LEFT JOIN promotions theo (unique_id, date)
    s = d["sku_sales_daily"].drop_duplicates(["unique_id", "date"], keep="last")
    s = (s.merge(d["prices"].drop_duplicates(["unique_id", "date"], keep="last")[["unique_id", "date", "sell_price_main"]], on=["unique_id", "date"], how="left")
          .merge(d["promotions"].drop_duplicates(["unique_id", "date"], keep="last")[["unique_id", "date"] + DISCOUNT_COLS], on=["unique_id", "date"], how="left"))
    n_neg = int((s[DISCOUNT_COLS] < 0).sum().sum())
    s[DISCOUNT_COLS] = s[DISCOUNT_COLS].astype(float).fillna(0).clip(0, 1)
    s["max_discount"] = s[DISCOUNT_COLS].max(axis=1)
    log.add("sales_history", len(d["sku_sales_daily"]), len(s), f"JOIN prices/promotions; {n_neg} discount âm → 0")
    if s.duplicated(keys).any():
        raise ValueError(f"{BT_ID}: sku_sales_daily trùng khoá unique_id+warehouse+date")
    inv = d["product_master"].rename(columns={"L1_category_name_en": "L1_inv"})[["unique_id", "warehouse", "L1_inv"]].drop_duplicates(["unique_id", "warehouse"])
    cal = d["calendar"].drop_duplicates(["warehouse", "date"], keep="last")[["warehouse", "date"] + CAL].copy()
    cal[CAL] = cal[CAL].fillna(0).astype("int8")
    cal_hist, cal_fc = cal[cal["date"] <= as_of], cal[cal["date"].isin(fc_dates)]
    lack = [w for w in scope if cal_fc.loc[cal_fc["warehouse"] == w, "date"].nunique() != H]
    if lack:
        raise ValueError(f"{BT_ID}: calendar thiếu ngày {fc_dates[0].date()}→{fc_dates[-1].date()} cho kho {lack}")
    wts = d["sku_weights"].drop_duplicates("unique_id")[["unique_id", "weight"]]

    # 2.3 total_orders quan sát theo kho–ngày = giá trị được nhiều SKU đồng thuận nhất (NULL bỏ qua), ngày thiếu → ffill
    tc = s.dropna(subset=["total_orders"]).groupby(["warehouse", "date", "total_orders"]).size().rename("support").reset_index()
    tc = tc.sort_values(["warehouse", "date", "support", "total_orders"], ascending=[True, True, False, False])
    mode = tc.drop_duplicates(["warehouse", "date"]).rename(columns={"total_orders": "total_orders_observed"})
    traffic = s.groupby(["warehouse", "date"])["total_orders"].count().rename("nn").reset_index().merge(mode, on=["warehouse", "date"], how="left")
    traffic = traffic.sort_values(["warehouse", "date"])
    traffic["total_orders_observed"] = traffic.groupby("warehouse")["total_orders_observed"].ffill()

    # 3. lost_sales (BT3) làm khung
    b3 = d["lost_sales"].copy()
    for c in b3.select_dtypes("category").columns:   # BT3 trả cột category khi chạy cùng lượt
        b3[c] = b3[c].astype(object)
    for c in ["sales", "availability", "final_price", "est_demand", "lost_units"]:
        b3[c] = pd.to_numeric(b3[c], errors="coerce")
    if b3.duplicated(keys).any() or b3["est_demand"].isna().any() or (b3["est_demand"] < 0).any():
        raise ValueError(f"{BT_ID}: lost_sales (BT3) sai hợp đồng: trùng khoá / est_demand thiếu hoặc âm")
    if "currency" not in b3.columns:
        b3["currency"] = b3["warehouse"].map(cur_map)
    cmp_ = s[keys + ["sales"]].merge(b3[keys], on=keys, how="outer", indicator=True)
    log.add("bt3_vs_sales_keys", len(s), len(b3),
            f"khớp {int((cmp_['_merge'] == 'both').sum())} | chỉ BT3 (hết hàng cả ngày) {int((cmp_['_merge'] == 'right_only').sum())} | "
            f"chỉ Sales (sales NULL bị BT3 loại) {int((cmp_['_merge'] == 'left_only').sum())}")
    u = (b3.merge(s[keys + ["sell_price_main", "max_discount"]], on=keys, how="left", validate="one_to_one")
           .merge(wts, on="unique_id", how="left", validate="many_to_one")
           .merge(cal_hist, on=["warehouse", "date"], how="left", validate="many_to_one")
           .merge(traffic[["warehouse", "date", "total_orders_observed"]], on=["warehouse", "date"], how="left", validate="many_to_one")
           .merge(inv, on=["unique_id", "warehouse"], how="left", validate="many_to_one"))
    u["L1"] = u["L1"].astype(object).fillna(u["L1_inv"].astype(object)).fillna("Unknown").astype(str)
    u = u.drop(columns=["L1_inv"]).sort_values(["unique_id", "date"]).reset_index(drop=True)
    u["sell_price_main"] = u.groupby("unique_id")["sell_price_main"].ffill()
    u["sell_price_main"] = u["sell_price_main"].fillna(u["final_price"])
    implied = (1 - u["final_price"] / u["sell_price_main"]).clip(0, 1)
    u["max_discount"] = u["max_discount"].fillna(implied).fillna(0)
    n_nw = int(u["weight"].isna().sum())
    u["weight"] = u["weight"].fillna(1.0)
    u[CAL] = u[CAL].fillna(0).astype("int8")
    u["target_sales"] = u["sales"].fillna(0).astype("float32")
    u["target_demand"] = u["est_demand"].astype("float32")
    log.add("unified_history", len(b3), len(u), f"{n_nw} dòng thiếu weight → 1.0")

    # 4. order_index BT1: quan sát (huấn luyện) / backtest BT1 (F1–F3) / fc_orders (16–29/03)
    fco = d["fc_orders"]
    oi_fc = fco[(fco["series"].astype(str).str.lower() == "order_index") & fco["date"].isin(fc_dates)].copy()
    fold_parts, src_by_wh = [], {}
    if not evaluate:
        for w in scope:
            f_w = oi_fc[oi_fc["warehouse"] == w]
            if f_w["date"].nunique() != H or f_w.duplicated("date").any():
                raise ValueError(f"{BT_ID}: fc_orders thiếu/trùng ngày order_index {fc_dates[0].date()}→{fc_dates[-1].date()} kho {w}")
            src_by_wh[w] = (str(f_w["model"].iloc[0]), "observed")
        log.add("bt1_order_index", len(oi_fc), len(oi_fc), "models: lịch sử dùng order_index quan sát; kỳ dự báo dùng fc_orders BT1")
    else:
        bt = d["bt1_backtest"]
        oi_bt = bt[bt["series"].astype(str).str.lower() == "order_index"].copy()
        meta = {"warehouse", "date", "cutoff", "y", "series", "fold", "closed", "co_nghi_van"}
        model_cols = [c for c in oi_bt.columns if c not in meta and "-p90" not in c and "-lo-" not in c and "-hi-" not in c
                      and pd.api.types.is_numeric_dtype(oi_bt[c])]
        for w in scope:
            f_w = oi_fc[oi_fc["warehouse"] == w]
            if f_w["date"].nunique() != H or f_w.duplicated("date").any():
                raise ValueError(f"{BT_ID}: fc_orders thiếu/trùng ngày order_index {fc_dates[0].date()}→{fc_dates[-1].date()} kho {w}")
            bt1_model = str(f_w["model"].iloc[0])
            b_w = oi_bt[oi_bt["warehouse"] == w]
            if bt1_model in model_cols:
                col = bt1_model
            else:
                cands = [m for m in model_cols if b_w[m].notna().any()]
                if not cands:
                    raise ValueError(f"{BT_ID}: bt1_backtest không có cột mô hình cho kho {w}")
                mae = {m: (b_w[m] - b_w["y"]).abs().mean() for m in cands}
                col = min(mae, key=mae.get)
                log.add(f"bt1_model_fallback:{w}", len(b_w), len(b_w), f"bt1_backtest không có cột '{bt1_model}' → dùng '{col}' (MAE nhỏ nhất)")
            p90c = f"{col}-p90" if f"{col}-p90" in b_w.columns else col
            src_by_wh[w] = (bt1_model, col)
            for f in FOLDS:
                o = fold_origin[f]
                x = b_w[(b_w["date"] > o) & (b_w["date"] <= o + pd.Timedelta(days=H)) & (b_w["cutoff"] <= o)].dropna(subset=[col])
                if x.empty:
                    raise ValueError(f"{BT_ID}: BT1 không có dự báo order_index kho {w} cửa sổ {f} với cutoff ≤ {o.date()}")
                x = x[x["cutoff"] == x["cutoff"].max()].copy()
                if x["date"].nunique() != H or x.duplicated("date").any():
                    raise ValueError(f"{BT_ID}: BT1 không phủ đủ 14 ngày cửa sổ {f} kho {w}")
                x["fold"], x["order_index_p50"] = f, x[col].astype(float)
                x["order_index_p90"] = np.maximum(x[p90c].astype(float), x["order_index_p50"])
                fold_parts.append(x[["fold", "warehouse", "date", "cutoff", "order_index_p50", "order_index_p90"]])
        bt1_folds = pd.concat(fold_parts, ignore_index=True)
        log.add("bt1_order_index", len(oi_bt), len(bt1_folds),
                "; ".join(f"{w}: fc={m}, backtest_col={c}" for w, (m, c) in src_by_wh.items()))
    u["order_index_feature"] = u["total_orders_observed"].astype("float32")
    if evaluate:
        mp = u[["warehouse", "date"]].merge(bt1_folds[["warehouse", "date", "order_index_p50"]], on=["warehouse", "date"], how="left")["order_index_p50"]
        u.loc[mp.notna().values, "order_index_feature"] = mp[mp.notna()].astype("float32").values

    # 6. ngày gốc + đặc trưng
    hist = u[["unique_id", "warehouse", "date", "L1", "currency", "weight", "target_sales", "target_demand", "availability", "lost_units",
              "final_price", "sell_price_main", "max_discount", "total_orders_observed", "order_index_feature"] + CAL].copy()
    earliest = hist["date"].min() + pd.Timedelta(days=int(cfg["min_history_days"]))
    origins, o = [], as_of
    while o >= earliest:
        origins.append(o)
        o -= pd.Timedelta(days=H)
    origins = sorted(origins)
    if evaluate and not set(fold_origin.values()).issubset(origins):
        raise ValueError(f"{BT_ID}: lịch sử quá ngắn – ngày gốc F1–F3 không nằm trên lịch 14 ngày")
    of = _origin_features(hist, origins, int(cfg["active_recency_days"]))
    log.add("origin_features", len(hist), len(of), f"{len(origins)} ngày gốc {origins[0].date()}→{origins[-1].date()}")
    to_fold = {v: k for k, v in fold_origin.items()}

    # 7. panel direct-horizon: ngày gốc < as_of × ngày mục tiêu (o, o+14] có trong lịch sử
    tgt = hist[["unique_id", "warehouse", "date", "order_index_feature", "target_sales", "target_demand", "availability"] + CAL].rename(
        columns={"date": "target_date", "order_index_feature": "target_order_index", "availability": "target_availability",
                 **{c: f"target_{c}" for c in CAL}})
    pf = of[of["origin_date"] < as_of].drop(columns=["last_observed_date"])
    panel = pf.merge(tgt, on=["unique_id", "warehouse"], how="inner")
    panel["horizon"] = (panel["target_date"] - panel["origin_date"]).dt.days
    panel = panel[(panel["horizon"] >= 1) & (panel["horizon"] <= H)].reset_index(drop=True)
    panel["horizon"] = panel["horizon"].astype("int8")
    panel = _add_target_calendar(panel)
    panel["origin_role"] = panel["origin_date"].map(to_fold).fillna("TRAIN_ORIGIN")
    panel["target_closed"] = panel["target_shops_closed"].astype("int8")
    panel["target_order_index"] = pd.to_numeric(panel["target_order_index"], errors="coerce").fillna(0.0)
    panel.loc[panel["target_closed"] == 1, "target_order_index"] = 0.0
    panel = panel.sort_values(["origin_date", "unique_id", "warehouse", "target_date"]).reset_index(drop=True)
    for f in (FOLDS if evaluate else []):
        if panel.loc[panel["origin_role"] == f, "horizon"].nunique() != H:
            raise ValueError(f"{BT_ID}: cửa sổ {f} thiếu horizon")
    log.add("direct_panel", len(of), len(panel), f"ngày gốc < {as_of.date()} × ngày mục tiêu (gốc, gốc+{H}] có trong lịch sử")

    # 7.2 lưới tương lai
    snap = of[of["origin_date"] == as_of].drop(columns=["last_observed_date"])
    if snap.empty:
        raise ValueError(f"{BT_ID}: không có SKU active tại {as_of.date()}")
    fut_o = oi_fc.rename(columns={"date": "target_date", "p50": "target_order_index", "p90": "target_order_index_p90"})[
        ["warehouse", "target_date", "target_order_index", "target_order_index_p90"]].copy()
    fut_o["bt1_closed"] = (fut_o["target_order_index"] <= 0).astype("int8")
    grid = snap.merge(fut_o, on="warehouse", how="inner")
    grid = grid.merge(cal_fc.rename(columns={"date": "target_date", **{c: f"target_{c}" for c in CAL}}), on=["warehouse", "target_date"],
                      how="left", validate="many_to_one")
    grid["horizon"] = (grid["target_date"] - grid["origin_date"]).dt.days.astype("int8")
    grid = _add_target_calendar(grid)
    grid["target_closed"] = ((grid["bt1_closed"] == 1) | (grid["target_shops_closed"] == 1)).astype("int8")
    grid.loc[grid["target_closed"] == 1, ["target_order_index", "target_order_index_p90"]] = 0.0
    if len(grid) != len(snap) * H or grid.duplicated(["unique_id", "warehouse", "target_date"]).any():
        raise ValueError(f"{BT_ID}: lưới tương lai phải = số SKU active × {H} ngày, không trùng khoá")
    grid = grid.sort_values(["unique_id", "warehouse", "target_date"]).reset_index(drop=True)

    if evaluate:
        # 8.1 baseline
        eval_cols = ["unique_id", "warehouse", "L1", "origin_role", "origin_date", "target_date", "horizon", "target_demand", "target_sales",
                     "target_availability", "weight", "target_closed", "demand_lag_0", "demand_mean_14", "demand_mean_28", "demand_same_dow_mean_8"]
        vp = panel.loc[panel["origin_role"].isin(FOLDS), eval_cols].copy()
        gfb = float(panel.loc[panel["origin_role"] == "TRAIN_ORIGIN", "target_demand"].median())
        vp["pred_last"] = vp["demand_lag_0"]
        vp["pred_mean_28"] = vp["demand_mean_28"]
        vp["pred_same_dow"] = vp["demand_same_dow_mean_8"]
        vp["pred_blend"] = 0.60 * vp["demand_same_dow_mean_8"] + 0.25 * vp["demand_mean_28"] + 0.15 * vp["demand_lag_0"]
        baselines = ["pred_last", "pred_mean_28", "pred_same_dow", "pred_blend"]
        for p in baselines:
            for fb in ["demand_mean_28", "demand_mean_14", "demand_lag_0"]:
                vp[p] = vp[p].fillna(vp[fb])
            vp[p] = vp[p].fillna(gfb).clip(lower=0)
            vp.loc[vp["target_closed"] == 1, p] = 0.0

        def metric_table(frame, col):
            res = {}
            for f in FOLDS + ["VALID"]:
                m = frame["origin_role"].isin(VALID_FOLDS) if f == "VALID" else frame["origin_role"] == f
                res[f] = calculate_metrics(frame.loc[m, "target_demand"], frame.loc[m, col], frame.loc[m, "weight"])
            return res

        bmean = {p: np.mean([metric_table(vp, p)[f]["WMAE"] for f in VALID_FOLDS]) for p in baselines}
        best_baseline = min(bmean, key=bmean.get)

    # 8.2–8.3 LightGBM
    feats = [c for c in FEATURE_CANDIDATES if c in panel.columns]
    cats = [c for c in ["unique_id", "warehouse", "L1"] if c in feats]
    levels = {c: sorted(panel[c].astype(str).unique()) for c in cats}

    def mm(frame):
        X = frame[feats].copy()
        for c in feats:
            if c in cats:
                X[c] = pd.Categorical(X[c].astype(str), categories=levels[c])
            else:
                X[c] = pd.to_numeric(X[c], errors="coerce").astype("float32")
        return X

    params = {**cfg["lgb_params"], "random_state": seed, "n_jobs": int(cfg["n_jobs"])}
    f1_start = fold_origin["F1"] + pd.Timedelta(days=1)
    tr = (panel["target_date"] < f1_start) & panel["target_demand"].notna()
    es = panel["origin_role"].isin(VALID_FOLDS)
    te = panel["origin_role"] == TEST_FOLD
    wfun = lambda m: panel.loc[m, "weight"].fillna(1.0).clip(lower=0).astype("float32")  # noqa: E731

    def fit(n_est, mask, eval_mask=None):
        mdl = lgb.LGBMRegressor(n_estimators=n_est, **params)
        kw = {}
        if eval_mask is not None:
            kw = dict(eval_set=[(mm(panel[eval_mask]), panel.loc[eval_mask, "target_demand"].astype("float32"))],
                      eval_sample_weight=[wfun(eval_mask)], eval_metric="l1",
                      callbacks=[lgb.early_stopping(int(cfg["early_stopping_rounds"]), verbose=False), lgb.log_evaluation(0)])
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*eval_set.*")
            warnings.simplefilter("ignore", category=FutureWarning)
            mdl.fit(mm(panel[mask]), panel.loc[mask, "target_demand"].astype("float32"), sample_weight=wfun(mask),
                    categorical_feature=cats, **kw)
        return mdl

    def build_q(frame, method):
        p50 = frame["p50"].to_numpy(float)
        l1 = frame["L1"].astype(str).where(frame["L1"].astype(str).isin(rl.index), "_ALL_")
        Q = np.column_stack([(p50 + 1) * rl.loc[l1, qc].to_numpy(float) - 1 for qc in QCOLS])
        i50 = PCOLS.index("p50")
        Q[:, i50] = p50
        if method == "offset_horizon":
            Q[:, -1] = p50 + frame["horizon"].astype(int).map(off).fillna(g_off).to_numpy(float)
        Q[:, :i50] = np.minimum(Q[:, :i50], p50[:, None])
        Q[:, i50 + 1:] = np.maximum(Q[:, i50 + 1:], p50[:, None])
        Q = np.clip(np.maximum.accumulate(Q, axis=1), 0, None)
        Q[frame["target_closed"].to_numpy() == 1] = 0.0
        return Q

    if evaluate:
        lgbm = fit(int(cfg["n_estimators"]), tr, es)
        best_iter = int(lgbm.best_iteration_ or cfg["n_estimators"])
        pred_valid = np.clip(lgbm.predict(mm(panel[es]), num_iteration=best_iter), 0, None)
        f3_tr = (panel["target_date"] <= fold_origin[TEST_FOLD]) & panel["target_demand"].notna()
        lgbm_f3 = fit(best_iter, f3_tr)
        pred_test = np.clip(lgbm_f3.predict(mm(panel[te])), 0, None)
        log.add("lightgbm_backtest", int(tr.sum()), int(es.sum() + te.sum()),
                f"train target < {f1_start.date()}; early stopping F1+F2 → best_iter={best_iter}; F3 dự báo bằng mô hình học lại ≤ {fold_origin[TEST_FOLD].date()}")
        cal_df = pd.concat([panel.loc[es, eval_cols].assign(prediction=pred_valid), panel.loc[te, eval_cols].assign(prediction=pred_test)], ignore_index=True)
        cal_df.loc[cal_df["target_closed"] == 1, "prediction"] = 0.0

        # 8.4 hiệu chỉnh hệ số
        f1, f2 = cal_df[cal_df["origin_role"] == "F1"], cal_df[cal_df["origin_role"] == "F2"]
        lo, hi, step = cfg["calibration_grid"]
        factors = np.round(np.arange(lo, hi + 1e-3, step), 3)
        wf1 = {k: calculate_metrics(f1["target_demand"], f1["prediction"] * k, f1["weight"])["WMAE"] for k in factors}
        k_best = float(min(wf1, key=wf1.get))
        f2_raw = calculate_metrics(f2["target_demand"], f2["prediction"], f2["weight"])["WMAE"]
        f2_cal = calculate_metrics(f2["target_demand"], f2["prediction"] * k_best, f2["weight"])["WMAE"]
        factor = k_best if f2_cal < f2_raw * (1 - cfg["calibration_min_gain"]) else 1.0
        log.add("calibration", len(f1), len(f2), f"hệ số tốt nhất F1={k_best}; F2 {f2_raw:.4f}→{f2_cal:.4f}; áp dụng {factor}")
        cal_df["p50"] = np.clip(cal_df["prediction"] * factor, 0, None)
        cal_df.loc[cal_df["target_closed"] == 1, "p50"] = 0.0

        # 9. phân vị
        cb = cal_df[cal_df["origin_role"].isin(VALID_FOLDS) & (cal_df["target_closed"] == 0)].copy()
        cb["residual"] = cb["target_demand"] - cb["p50"]
        g_off = max(weighted_quantile(cb["residual"], cb["weight"], 0.9), 0.0)
        off = {int(h): max(np.nan_to_num(weighted_quantile(x["residual"], x["weight"], 0.9), nan=g_off), 0.0) for h, x in cb.groupby("horizon")}
        cb["ratio"] = (cb["target_demand"] + 1) / (cb["p50"] + 1)
        rr = [{"L1": l1, **{qc: weighted_quantile(x["ratio"], x["weight"], q) for qc, q in zip(QCOLS, QS)}, "rows": len(x)} for l1, x in cb.groupby("L1")]
        rr.append({"L1": "_ALL_", **{qc: weighted_quantile(cb["ratio"], cb["weight"], q) for qc, q in zip(QCOLS, QS)}, "rows": len(cb)})
        qr = pd.DataFrame(rr)
        qr[QCOLS] = np.maximum.accumulate(qr[QCOLS].to_numpy(), axis=1)
        qr["source"] = f"conformal ratio (y+1)/(p50+1), weighted, F1+F2, {len(scope)} kho"
        rl = qr.set_index("L1")

        vr = cal_df[cal_df["origin_role"].isin(VALID_FOLDS)]
        pin = {m: pinball(vr["target_demand"], build_q(vr, m)[:, -1], 0.9, vr["weight"]) for m in ["offset_horizon", "ratio_L1"]}
        p90_method = min(pin, key=pin.get)
        log.add("quantiles", len(cb), len(qr), f"pinball q90 F1+F2: {pin}; chọn {p90_method}")
        cal_df[PCOLS] = build_q(cal_df, p90_method)
        op = cal_df[(cal_df["origin_role"] == TEST_FOLD) & (cal_df["target_closed"] == 0)]
        w_, y_ = op["weight"].to_numpy(float), op["target_demand"].to_numpy(float)
        cov_band = 100 * np.average((y_ >= op["p20"]) & (y_ <= op["p90"]), weights=w_) if len(op) else np.nan
        cov_p90 = 100 * np.average(y_ <= op["p90"], weights=w_) if len(op) else np.nan
    else:
        best_iter = int(frozen["best_iter"])
        factor = float(frozen["factor"])
        p90_method = str(frozen["p90_method"])
        qr = pd.DataFrame(frozen["quantile_ratios"])
        off = {int(k): float(v) for k, v in (frozen.get("offsets") or {}).items()}
        g_off = float(frozen.get("g_off") or 0.0)
        log.add("frozen_params", 0, len(qr), f"best_iter={best_iter}; hệ số={factor}; p90={p90_method}; nguồn={frozen.get('_source', 'params')}")
    rl = qr.set_index("L1")

    # 10. mô hình cuối + dự báo
    final_mask = (panel["target_date"] <= as_of) & panel["target_demand"].notna()
    final_model = fit(best_iter, final_mask)
    Xf = mm(grid)
    fc = grid[["unique_id", "warehouse", "L1", "currency", "target_date", "horizon", "target_closed", "target_order_index"]].copy()
    fc["p50"] = np.clip(final_model.predict(Xf) * factor, 0, None)
    fc.loc[fc["target_closed"] == 1, "p50"] = 0.0
    fc[PCOLS] = build_q(fc, p90_method)
    fc["p_point"] = fc["p50"]
    lp = u[u["date"] <= as_of].dropna(subset=["final_price"]).sort_values(["unique_id", "date"]).groupby("unique_id").tail(1).set_index("unique_id")
    fc["final_price"] = fc["unique_id"].map(lp["final_price"])
    fc["sell_price_main"] = fc["unique_id"].map(lp["sell_price_main"])
    fc["final_price"] = fc["final_price"].fillna(fc["sell_price_main"])
    fc["price_source"] = cfg["price_source"]
    fc["order_index_source"] = fc["warehouse"].map({w: f"BT1:{m}" for w, (m, _) in src_by_wh.items()})
    fc["model"] = MODEL_NAME
    fc["cold_start_unique_id"] = Xf["unique_id"].isna().astype("int8").values if "unique_id" in cats else 0
    fc = fc.rename(columns={"target_date": "date"})
    fc = fc[["unique_id", "date", "warehouse", "L1", "final_price", "currency", "p_point"] + PCOLS +
            ["model", "price_source", "order_index_source", "sell_price_main", "horizon", "target_closed", "target_order_index", "cold_start_unique_id"]]
    fc = fc.sort_values(["unique_id", "date"]).reset_index(drop=True)
    log.add("final_forecast", int(final_mask.sum()), len(fc), f"{fc['unique_id'].nunique()} SKU × {H} ngày; best_iter={best_iter}; hệ số={factor}")

    if evaluate:
        # 11. bảng bàn giao
        b = cal_df[cal_df["origin_role"] == TEST_FOLD]
        bt4_backtest = pd.DataFrame({"unique_id": b["unique_id"], "date": b["target_date"], "warehouse": b["warehouse"], "L1": b["L1"],
                                     "actual": b["target_demand"].astype(float), "sales": b["target_sales"].astype(float),
                                     "availability": b["target_availability"].astype(float), "weight": b["weight"].astype(float),
                                     "horizon": b["horizon"], "target_closed": b["target_closed"], "p_point": b["p50"], "model": MODEL_NAME})
        bt4_backtest[PCOLS] = b[PCOLS].to_numpy()
        bt4_backtest = bt4_backtest.sort_values(["unique_id", "date"]).reset_index(drop=True)

        def comp_row(frame, col, name):
            m = metric_table(frame, col)
            t = frame[frame["origin_role"] == TEST_FOLD]
            full = t["target_availability"] >= cfg["stockout_threshold"]
            return {"model": name, "WMAE_F1": m["F1"]["WMAE"], "WMAE_F2": m["F2"]["WMAE"], "WMAE_valid_mean": (m["F1"]["WMAE"] + m["F2"]["WMAE"]) / 2,
                    "WMAE_F3": m["F3"]["WMAE"], "WMAPE_F3_%": m["F3"]["WMAPE_%"], "bias_F3_%": m["F3"]["bias_%"], "RMSE_F3": m["F3"]["RMSE"],
                    "WMAE_F3_full_availability": calculate_metrics(t.loc[full, "target_demand"], t.loc[full, col], t.loc[full, "weight"])["WMAE"]}

        rows = [comp_row(vp, p, "Baseline_" + p.replace("pred_", "")) for p in baselines]
        rows.append(comp_row(cal_df.assign(raw=cal_df["prediction"]), "raw", "LightGBM_L1_raw"))
        rows.append(comp_row(cal_df, "p50", MODEL_NAME))
        comp = pd.DataFrame(rows)
        comp["selected"] = comp["model"] == MODEL_NAME
        comp["best_baseline_F1F2"] = comp["model"] == "Baseline_" + best_baseline.replace("pred_", "")
        comp["best_iter"] = np.where(comp["model"].str.startswith("LightGBM"), best_iter, 0)
        comp["calibration_factor"] = np.where(comp["selected"], factor, 1.0)
        comp["p90_method"] = np.where(comp["selected"], p90_method, "none")
        comp["coverage_P20_P90_F3_%"] = np.where(comp["selected"], cov_band, 0.0)
        comp["coverage_P90_F3_%"] = np.where(comp["selected"], cov_p90, 0.0)
        comp["order_index_source"] = "; ".join(f"{w}=BT1:{m}" for w, (m, _) in src_by_wh.items())

    outputs = {"fc_sku": fc, "run_log": log.frame()}
    if evaluate:
        outputs.update({"bt4_backtest": bt4_backtest, "bt4_quantile_ratios": qr, "bt4_model_comparison": comp})
        outputs["_params"] = {"best_iter": int(best_iter), "factor": float(factor), "p90_method": p90_method,
                              "quantile_ratios": [{k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else str(v))
                                                   for k, v in r.items()} for r in qr[["L1"] + QCOLS].to_dict("records")],
                              "offsets": {str(k): float(v) for k, v in off.items()}, "g_off": float(g_off)}
    validate_outputs(outputs, cfg)
    return outputs


# ----------------------------------------------------------------------------------------------------------------
# 4. Kiểm tra hợp đồng đầu ra
# ----------------------------------------------------------------------------------------------------------------
CONTRACT = {
    "fc_sku": {"cols": ["unique_id", "date", "warehouse", "L1", "final_price", "currency", "p_point"] + PCOLS +
                       ["model", "price_source", "order_index_source"], "keys": ["unique_id", "date"], "nonneg": ["final_price", "p_point"] + PCOLS},
    "bt4_backtest": {"cols": ["unique_id", "date", "warehouse", "L1", "actual", "p_point", "model"] + PCOLS,
                     "keys": ["unique_id", "date"], "nonneg": ["actual", "p_point"] + PCOLS},
    "bt4_quantile_ratios": {"cols": ["L1"] + QCOLS, "keys": ["L1"], "nonneg": QCOLS},
    "bt4_model_comparison": {"cols": ["model", "WMAE_valid_mean", "WMAE_F3", "selected"], "keys": ["model"], "nonneg": ["WMAE_valid_mean", "WMAE_F3"]},
    "run_log": {"cols": ["step", "rows_in", "rows_out", "note"], "keys": [], "nonneg": []},
}


def validate_outputs(outputs: dict[str, pd.DataFrame], config: dict) -> None:
    cfg = _merge_config(config)
    errs = []
    need = OUTPUTS if cfg["mode"] == "evaluate" else FAST_OUTPUTS
    for name, c in CONTRACT.items():
        if name not in need:
            continue
        if name not in outputs or not isinstance(outputs[name], pd.DataFrame):
            errs.append(f"thiếu output '{name}'")
            continue
        df = outputs[name]
        miss = [x for x in c["cols"] if x not in df.columns]
        if miss:
            errs.append(f"{name}: thiếu cột {miss}")
            continue
        if name != "run_log" and len(df) == 0:
            errs.append(f"{name}: rỗng")
        if c["keys"] and df.duplicated(c["keys"]).any():
            errs.append(f"{name}: trùng khoá {c['keys']}")
        if df[c["cols"]].isna().any().any():
            errs.append(f"{name}: NaN ở cột {list(df[c['cols']].columns[df[c['cols']].isna().any()])}")
        for col in c["nonneg"]:
            if (pd.to_numeric(df[col], errors="coerce") < -1e-9).any():
                errs.append(f"{name}: {col} có giá trị âm")
        if set(PCOLS) <= set(df.columns) and (np.diff(df[PCOLS].to_numpy(float), axis=1) < -1e-9).any():
            errs.append(f"{name}: vi phạm p20 ≤ … ≤ p90")
    if not errs:
        as_of, H = pd.Timestamp(cfg["as_of"]), int(cfg["horizon"])
        fc = outputs["fc_sku"]
        fd = pd.to_datetime(fc["date"])
        if set(fd) != set(pd.date_range(as_of + pd.Timedelta(days=1), periods=H)):
            errs.append(f"fc_sku: ngày phải đủ {H} ngày sau as_of")
        if "bt4_backtest" in need:
            bd = pd.to_datetime(outputs["bt4_backtest"]["date"])
            if bd.min() < as_of - pd.Timedelta(days=H - 1) or bd.max() > as_of:
                errs.append("bt4_backtest: ngày ngoài kỳ kiểm tra")
        if not np.allclose(fc["p_point"], fc["p50"]):
            errs.append("fc_sku: p_point ≠ p50")
        exp = set(_scope(cfg))
        for name in [n for n in ["fc_sku", "bt4_backtest"] if n in need]:
            got = set(outputs[name]["warehouse"].astype(str))
            if got != exp:
                errs.append(f"{name}: kho {sorted(got)} ≠ phạm vi {sorted(exp)}")
        if "bt4_model_comparison" in need and int(outputs["bt4_model_comparison"]["selected"].astype(bool).sum()) != 1:
            errs.append("bt4_model_comparison: phải có đúng 1 mô hình selected")
    if errs:
        raise ValueError(f"{BT_ID} output sai hợp đồng: " + "; ".join(errs))
