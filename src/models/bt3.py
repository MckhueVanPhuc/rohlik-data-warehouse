"""BT3 – Ước lượng nhu cầu bị mất do hết hàng (lost sales / censored demand) – bản tinh gọn để tích hợp pipeline.

Thuật toán giữ nguyên notebook final `final8/bt3/BT3_final.ipynb` (phương án V2 của thành viên), áp phạm vi 7 kho:
  chuẩn hoá input (tương đương bronze → silver → gold.fct_sku_day, viết lại bằng pandas)
  → bổ sung dòng "hết hàng cả ngày" (khoảng trống ≤ 7 ngày, trừ ngày đóng cửa / ngày kho thu hẹp hoạt động)
  → đặc trưng "không nhiễm bẩn" (lịch sử chỉ tính trên ngày đủ hàng, lùi 1 ngày)
  → mô hình FINAL đã chọn trong notebook: M4_LightGBM_Tweedie (min WMAE inner-val) + baseline M1_Baseline_MA28
  → ước lượng est_demand cho ngày thiếu hàng (quy tắc an toàn + trần) → lost_units, lost_revenue (+ EUR)
  → tổng hợp kho × L1, kho × L1 × tháng → validate hợp đồng.
Các ứng viên thua (M2, M3, M5/CatBoost), EDA, SHAP, ablation, độ nhạy chỉ có trong original_notebook.ipynb.
Không đọc/ghi file, không DuckDB, không biến toàn cục trạng thái.

Hai chế độ (D06, đã duyệt dùng M4 LightGBM Tweedie cho bản tinh gọn):
  * mode="models"  : học M4 với số cây đã chốt (frozen["best_iter"]), không early-stopping, không baseline/đánh giá.
  * mode="evaluate": như trên + early-stopping trên inner-val, baseline M1, bảng so sánh; trả "_params".
"""
from __future__ import annotations

import copy
import warnings
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

BT_ID = "BT3"
DISCOUNT_COLS = [f"type_{i}_discount" for i in range(7)]
CAL_COLS = ["holiday", "shops_closed", "school_holidays", "winter_school_holidays"]
REQUIRED_INPUTS = ["sku_sales_daily", "prices", "promotions", "availability", "product_master", "calendar", "sku_weights"]
OPTIONAL_INPUTS: list[str] = []
UPSTREAM: dict[str, tuple[str, str]] = {}
OUTPUTS = ["lost_sales", "lost_sales_summary", "lost_sales_monthly", "bt3_model_comparison", "run_log"]
FAST_INPUTS = REQUIRED_INPUTS
FAST_OUTPUTS = ["lost_sales", "lost_sales_summary", "lost_sales_monthly", "run_log"]

# Cột bắt buộc của từng input logic (tên cột theo CSV gốc Kaggle = bảng Landing)
REQUIRED_COLUMNS = {
    "sku_sales_daily": ["unique_id", "date", "warehouse", "sales", "total_orders"],
    "prices": ["unique_id", "date", "sell_price_main"],
    "promotions": ["unique_id", "date"] + DISCOUNT_COLS,
    "availability": ["unique_id", "date", "availability"],
    "product_master": ["unique_id", "product_unique_id", "name", "L1_category_name_en", "L2_category_name_en",
                       "L3_category_name_en", "warehouse"],
    "calendar": ["warehouse", "date"] + CAL_COLS,
    "sku_weights": ["unique_id", "weight"],
}
ACTUAL_DATED = ["sku_sales_daily", "prices", "promotions", "availability"]   # số liệu thực tế: cắt train_start ≤ date ≤ as_of

ALL_WAREHOUSES = ["Brno_1", "Budapest_1", "Frankfurt_1", "Munich_1", "Prague_1", "Prague_2", "Prague_3"]
FINAL_MODEL = "M4_LightGBM_Tweedie"
BASELINE_MODEL = "M1_Baseline_MA28"

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",
    "train_start": "2020-12-05",
    "horizon": 14,
    "seed": 42,
    "n_jobs": 1,                       # số luồng LightGBM; >1 nhanh hơn nhưng có thể lệch kết quả ở mức sai số
    "warehouses": None,                # None = tất cả kho trong expected_warehouses (bắt buộc đủ)
    "expected_warehouses": ALL_WAREHOUSES,
    "currency_by_warehouse": {"Prague_1": "CZK", "Prague_2": "CZK", "Prague_3": "CZK", "Brno_1": "CZK",
                              "Budapest_1": "HUF", "Munich_1": "EUR", "Frankfurt_1": "EUR"},
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},   # ASSUMED – chỉ để cộng nhiều kho
    "full_avail_threshold": 0.99,      # availability ≥ 0.99 → ngày đủ hàng (sales = nhu cầu)
    "impute_full_day_stockouts": True,
    "max_full_stockout_gap": 7,        # khoảng trống ≤ 7 ngày giữa 2 dòng = hết hàng cả ngày
    "abnormal_day_ratio": 0.7,         # kho-ngày có số SKU < 70% trung vị 28 ngày → không bổ sung
    "exclude_closed_days_from_impute": True,
    "use_twin_index": True,
    "use_name_group": True,
    "val_days": 56,                    # Test = 8 tuần cuối (chỉ báo cáo)
    "inner_val_days": 28,              # inner-val: early-stopping (và tiêu chí chọn mô hình trong notebook)
    "demand_cap_mult": 3.0,            # trần: est ≤ max(3 × TB28 đủ hàng, P99 sales đủ hàng của SKU)
    "lgb_common": {"n_estimators": 2500, "learning_rate": 0.08, "num_leaves": 127, "min_child_samples": 100,
                   "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "reg_lambda": 1.0,
                   "verbose": -1, "deterministic": True, "force_row_wise": True},
    "lgb_final": {"objective": "tweedie", "tweedie_variance_power": 1.2},
    "early_stopping_rounds": 50,
    "required_inputs": REQUIRED_INPUTS,
    "mode": "evaluate",                # "models" | "evaluate"
    "frozen": None,                    # {"best_iter": int}
}


# ----------------------------------------------------------------------------------------------------------------
# Tiện ích chung
# ----------------------------------------------------------------------------------------------------------------
def _merge_config(config: dict | None) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    for k, v in (config or {}).items():
        cfg[k] = copy.deepcopy(v)
    return cfg


def _scope_warehouses(cfg: dict) -> list[str]:
    return list(cfg["warehouses"]) if cfg.get("warehouses") else list(cfg["expected_warehouses"])


class _Log:
    def __init__(self):
        self.rows = []

    def add(self, step, rows_in, rows_out, note=""):
        self.rows.append({"step": step, "rows_in": int(rows_in), "rows_out": int(rows_out), "note": str(note)})

    def frame(self):
        return pd.DataFrame(self.rows, columns=["step", "rows_in", "rows_out", "note"])


def wmae(y, p, w):
    y, p, w = np.asarray(y, float), np.asarray(p, float), np.asarray(w, float)
    return float(np.sum(w * np.abs(y - p)) / np.sum(w))


def wmape_pct(y, p, w):
    y, p, w = np.asarray(y, float), np.asarray(p, float), np.asarray(w, float)
    return float(np.sum(w * np.abs(y - p)) / max(np.sum(w * y), 1e-9) * 100)


def rmse(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.sqrt(np.mean((y - p) ** 2)))


def bias_pct(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.sum(p - y) / max(np.sum(y), 1e-9) * 100)


def bias_w_pct(y, p, w):
    y, p, w = np.asarray(y, float), np.asarray(p, float), np.asarray(w, float)
    return float(np.sum(w * (p - y)) / max(np.sum(w * y), 1e-9) * 100)


# ----------------------------------------------------------------------------------------------------------------
# 1. Kiểm tra + chuẩn hoá input, cắt mốc chống rò rỉ
# ----------------------------------------------------------------------------------------------------------------
def _check_and_cut(inputs: dict, cfg: dict, log: _Log) -> dict[str, pd.DataFrame]:
    required = list(cfg.get("required_inputs") or REQUIRED_INPUTS)
    missing = sorted(set(required) - set(inputs))
    if missing:
        raise ValueError(f"{BT_ID}: thiếu input bắt buộc: {missing}")
    as_of, start = pd.Timestamp(cfg["as_of"]), pd.Timestamp(cfg["train_start"])
    cal_end = as_of + pd.Timedelta(days=int(cfg["horizon"]))
    out = {}
    for name in REQUIRED_INPUTS:
        df = inputs[name]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{BT_ID}: input '{name}' phải là pandas.DataFrame")
        miss_cols = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
        if miss_cols:
            raise ValueError(f"{BT_ID}: input '{name}' thiếu cột {miss_cols}")
        df = df.copy()
        n0 = len(df)
        if "date" in df.columns:
            try:
                df["date"] = pd.to_datetime(df["date"])
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"{BT_ID}: cột date của '{name}' không chuyển được sang ngày: {e}") from e
            hi = cal_end if name == "calendar" else as_of
            df = df[(df["date"] >= start) & (df["date"] <= hi)]
            log.add(f"cut_dates:{name}", n0, len(df), f"giữ {start.date()} ≤ date ≤ {hi.date()}")
        else:
            log.add(f"load:{name}", n0, len(df), "không có cột ngày")
        if "unique_id" in df.columns:
            df["unique_id"] = pd.to_numeric(df["unique_id"], errors="raise").astype("int64")
        if "warehouse" in df.columns:
            df["warehouse"] = df["warehouse"].astype(str).str.strip()
        out[name] = df.reset_index(drop=True)
    # phạm vi kho
    scope = _scope_warehouses(cfg)
    have = set(out["sku_sales_daily"]["warehouse"].unique())
    lack = sorted(set(scope) - have)
    if lack:
        raise ValueError(f"{BT_ID}: input sku_sales_daily không có dữ liệu cho kho {lack} (phạm vi yêu cầu {scope})")
    n0 = len(out["sku_sales_daily"])
    out["sku_sales_daily"] = out["sku_sales_daily"][out["sku_sales_daily"]["warehouse"].isin(scope)].reset_index(drop=True)
    log.add("scope_warehouses", n0, len(out["sku_sales_daily"]), f"kho: {sorted(scope)}")
    return out


def _build_gold(d: dict, cfg: dict, log: _Log) -> pd.DataFrame:
    """Tương đương silver + gold.fct_sku_day của notebook (pandas thay DuckDB).
    JOIN: sku_sales_daily s INNER JOIN prices (unique_id, date) [giá > 0] LEFT JOIN promotions (unique_id, date)
          LEFT JOIN availability (unique_id, date) LEFT JOIN dim_product (unique_id) LEFT JOIN calendar (warehouse, date)."""
    s = d["sku_sales_daily"].drop_duplicates(["unique_id", "date"], keep="last")
    n0 = len(s)
    s = s[s["sales"].notna() & (s["sales"] >= 0)].copy()
    log.add("drop_sales_null_or_negative", n0, len(s), "sales NULL/âm → loại khỏi học/đánh giá (không điền 0)")
    s["sales"] = s["sales"].astype(float)
    s["total_orders"] = pd.to_numeric(s["total_orders"], errors="coerce").astype(float)

    p = d["prices"].drop_duplicates(["unique_id", "date"], keep="last")
    p = p[p["sell_price_main"].notna() & (p["sell_price_main"] > 0)][["unique_id", "date", "sell_price_main"]]
    pr = d["promotions"].drop_duplicates(["unique_id", "date"], keep="last")[["unique_id", "date"] + DISCOUNT_COLS].copy()
    n_neg = int((pr[DISCOUNT_COLS] < 0).sum().sum())
    pr[DISCOUNT_COLS] = pr[DISCOUNT_COLS].astype(float).fillna(0.0).clip(0, 1)
    log.add("clip_discounts", len(pr), len(pr), f"{n_neg} giá trị discount âm → kẹp 0; NULL → 0; kẹp [0,1]")
    a = d["availability"].drop_duplicates(["unique_id", "date"], keep="last")[["unique_id", "date", "availability"]].copy()
    n_an = int(a["availability"].isna().sum())
    a["availability"] = a["availability"].astype(float).fillna(1.0).clip(0, 1)
    log.add("availability_clean", len(a), len(a), f"{n_an} availability NULL → 1.0; kẹp [0,1]")

    pm = d["product_master"].drop_duplicates("unique_id", keep="last").copy()
    w = d["sku_weights"].drop_duplicates("unique_id", keep="last")[["unique_id", "weight"]]
    pm = pm.merge(w, on="unique_id", how="left")
    m2 = pm.groupby("L2_category_name_en")["weight"].median()
    m1 = pm.groupby("L1_category_name_en")["weight"].median()
    pm["weight_imputed"] = pm["weight"].isna()
    pm["weight"] = (pm["weight"].fillna(pm["L2_category_name_en"].map(m2)).fillna(pm["L1_category_name_en"].map(m1))
                    .fillna(pm["weight"].median()))
    log.add("weights_impute", len(pm), len(pm), f"{int(pm['weight_imputed'].sum())} SKU thiếu weight → trung vị L2 → L1 → toàn bộ")
    pm = pm.rename(columns={"L1_category_name_en": "L1", "L2_category_name_en": "L2", "L3_category_name_en": "L3"})

    cal = d["calendar"].drop_duplicates(["warehouse", "date"], keep="last")[["warehouse", "date"] + CAL_COLS].copy()
    cal[CAL_COLS] = cal[CAL_COLS].fillna(0).astype(int)

    n0 = len(s)
    g = s.merge(p, on=["unique_id", "date"], how="inner")
    log.add("join_prices_inner", n0, len(g), "bỏ dòng không có giá > 0")
    g = (g.merge(pr, on=["unique_id", "date"], how="left")
          .merge(a, on=["unique_id", "date"], how="left")
          .merge(pm[["unique_id", "product_unique_id", "name", "L1", "L2", "L3", "weight"]], on="unique_id", how="left")
          .merge(cal, on=["warehouse", "date"], how="left"))
    if len(g) != len(s.merge(p, on=["unique_id", "date"], how="inner")):
        raise ValueError(f"{BT_ID}: JOIN làm nhân dòng – kiểm tra khoá các bảng input")
    # load_fct_sku_day của notebook
    g["availability"] = g["availability"].fillna(1.0).clip(0, 1)
    g[DISCOUNT_COLS] = g[DISCOUNT_COLS].fillna(0).clip(0, 1)
    for c in CAL_COLS:
        g[c] = g[c].fillna(0).astype(int)
    for c in ["L1", "L2", "L3"]:
        g[c] = g[c].astype(object).where(g[c].notna(), "Unknown").astype(str)
    g["weight"] = g["weight"].fillna(g.groupby("L2")["weight"].transform("median")).fillna(g["weight"].median())
    g["max_discount"] = g[DISCOUNT_COLS].max(axis=1)
    g["final_price"] = g["sell_price_main"] * (1 - g["max_discount"])
    g["product_unique_id"] = pd.to_numeric(g["product_unique_id"], errors="coerce").fillna(-1).astype("int64")
    g["name_group"] = g["name"].astype(object).where(g["name"].notna(), "Unknown").astype(str).str.split("_").str[0]
    g.loc[g["name"].isna(), "name_group"] = "Unknown"
    g = g.drop(columns=["name"]).sort_values(["unique_id", "date"]).reset_index(drop=True)
    g = _compact(g)
    return g, cal


def _as_str_categorical(s: pd.Series, levels: list[str]) -> pd.Categorical:
    """= pd.Categorical(s.astype(str), categories=levels) nhưng không tạo hàng triệu chuỗi (tiết kiệm RAM)."""
    lookup = {lv: i for i, lv in enumerate(levels)}
    if isinstance(s.dtype, pd.CategoricalDtype):
        cats = s.cat.categories
        cmap = np.array([lookup.get(str(c), -1) for c in cats] + [lookup.get("nan", -1)], dtype=np.int32)
        codes = s.cat.codes.to_numpy()
        codes = cmap[np.where(codes < 0, len(cats), codes)]
    else:
        uniq, inv = np.unique(s.to_numpy(), return_inverse=True)
        cmap = np.array([lookup.get(str(u), -1) for u in uniq], dtype=np.int32)
        codes = cmap[inv]
    return pd.Categorical.from_codes(codes, categories=levels)


def _compact(df: pd.DataFrame) -> pd.DataFrame:
    """Giảm RAM (7 kho ≈ 3,5 triệu dòng): cột chữ → category, cờ lịch → int8. Không đổi giá trị."""
    for c in ["warehouse", "L1", "L2", "L3", "name_group", "stockout_type"]:
        if c in df.columns and df[c].dtype != "category":
            df[c] = df[c].astype("category")
    for c in CAL_COLS:
        if c in df.columns and df[c].notna().all():
            df[c] = df[c].astype("int8")
    return df


# ----------------------------------------------------------------------------------------------------------------
# 2. Bổ sung dòng hết hàng cả ngày (notebook ô 2.6)
# ----------------------------------------------------------------------------------------------------------------
def _add_full_day_stockouts(df: pd.DataFrame, cal: pd.DataFrame, cfg: dict, log: _Log) -> pd.DataFrame:
    thr, max_gap, ratio = cfg["full_avail_threshold"], int(cfg["max_full_stockout_gap"]), cfg["abnormal_day_ratio"]
    df = df.sort_values(["unique_id", "date"]).reset_index(drop=True)
    df["stockout_type"] = np.where(df["availability"] < thr, "partial_day", "none")
    gap = df.groupby("unique_id")["date"].diff().dt.days
    m = gap.between(2, max_gap + 1)
    if not m.any():
        df["gap_len"] = 0
        log.add("impute_full_day", len(df), len(df), "không có khoảng trống")
        return df
    ends = df.loc[m, ["unique_id", "date"]].assign(n=(gap[m] - 1).astype(int))
    rep = ends.loc[ends.index.repeat(ends["n"])].copy()
    rep["k"] = rep.groupby(level=0).cumcount() + 1
    rep["date"] = rep["date"] - pd.to_timedelta(rep["n"] - rep["k"] + 1, unit="D")
    new = rep[["unique_id", "date", "n"]].rename(columns={"n": "gap_len"}).reset_index(drop=True)
    cnt = df.groupby(["warehouse", "date"]).size().rename("n").reset_index().sort_values(["warehouse", "date"])
    cnt["med28"] = cnt.groupby("warehouse")["n"].transform(lambda x: x.rolling(28, min_periods=7, center=True).median())
    abn = cnt.loc[cnt["n"] < ratio * cnt["med28"], ["warehouse", "date"]].assign(abnormal=1)
    sku_wh = df.drop_duplicates("unique_id").set_index("unique_id")["warehouse"]
    new["warehouse"] = new["unique_id"].map(sku_wh)
    new = new.merge(abn, on=["warehouse", "date"], how="left")
    new = new[new["abnormal"].isna()].drop(columns="abnormal")
    n_cand = len(new)
    n_closed = 0
    if cfg["exclude_closed_days_from_impute"]:
        closed = cal.loc[cal["shops_closed"] == 1, ["warehouse", "date"]].drop_duplicates().assign(_closed=1)
        new = new.merge(closed, on=["warehouse", "date"], how="left")
        on_closed = new["_closed"].fillna(0) == 1
        n_closed = int(on_closed.sum())
        new = new[~on_closed].drop(columns="_closed")
    log.add("impute_full_day", n_cand, len(new),
            f"khoảng trống ≤ {max_gap} ngày → sales=0, availability=0; loại {n_closed} dòng ngày đóng cửa (ứng viên {n_cand})")
    new = new.assign(sales=0.0, availability=0.0, stockout_type="full_day_imputed")
    out = pd.concat([df, new], ignore_index=True).sort_values(["unique_id", "date"]).reset_index(drop=True)
    del df, new
    out = _compact(out)
    static = ["L1", "L2", "L3", "weight", "product_unique_id", "name_group", "sell_price_main"] + DISCOUNT_COLS
    out[static] = out.groupby("unique_id")[static].ffill()
    out["max_discount"] = out[DISCOUNT_COLS].max(axis=1)
    out["final_price"] = out["sell_price_main"] * (1 - out["max_discount"])
    obs = out["stockout_type"] != "full_day_imputed"
    wd = (out[obs].groupby(["warehouse", "date"]).agg(total_orders_wd=("total_orders", "median"), holiday_wd=("holiday", "max"),
                                                       shops_closed_wd=("shops_closed", "max"), school_wd=("school_holidays", "max"),
                                                       winter_wd=("winter_school_holidays", "max")).reset_index())
    look = out[["warehouse", "date"]].merge(wd, on=["warehouse", "date"], how="left")
    for c, cw in [("total_orders", "total_orders_wd"), ("holiday", "holiday_wd"), ("shops_closed", "shops_closed_wd"),
                  ("school_holidays", "school_wd"), ("winter_school_holidays", "winter_wd")]:
        out[c] = out[c].fillna(pd.Series(look[cw].values, index=out.index))
    out[CAL_COLS] = out[CAL_COLS].fillna(0).astype(int)
    n0 = len(out)
    out = out.dropna(subset=["total_orders", "final_price"]).reset_index(drop=True)
    log.add("drop_no_context", n0, len(out), "bỏ dòng thiếu total_orders/final_price sau khi điền bối cảnh kho-ngày")
    out["gap_len"] = out["gap_len"].fillna(0).astype(int)
    return out


# ----------------------------------------------------------------------------------------------------------------
# 3. Đặc trưng (notebook Section 4)
# ----------------------------------------------------------------------------------------------------------------
def _calendar_flags(cal: pd.DataFrame) -> pd.DataFrame:
    out = []
    for w, g in cal.groupby("warehouse"):
        g = g.drop_duplicates("date").set_index("date").sort_index()
        g = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="D")).fillna(0)
        coh = ((g["holiday"] == 1) | (g["shops_closed"] == 1)).astype(int)
        out.append(pd.DataFrame({"warehouse": w, "date": g.index,
                                 "is_pre_closed_or_holiday": (coh.shift(-1, fill_value=0).values * (1 - coh.values)).astype("int8"),
                                 "is_post_closed": g["shops_closed"].shift(1, fill_value=0).astype("int8").values}))
    return pd.concat(out, ignore_index=True)


def _roll(s_sub, keys, window, fn, min_periods=1):
    r = s_sub.groupby(keys).rolling(window, min_periods=min_periods)
    r = getattr(r, fn)()
    return r.reset_index(level=list(range(len(keys))), drop=True)


def _prev_ffill(df, values, keys):
    tmp = pd.Series(np.nan, index=df.index)
    tmp.loc[values.index] = values.values
    g = [df[k] for k in keys]
    return tmp.groupby(g).shift(1).groupby(g).ffill()


def _loo_index(r, df, grp_cols, min_n):
    has_r = r.notna().astype("int32")
    g = [df[c] for c in grp_cols]
    S = r.fillna(0).groupby(g).transform("sum")
    N = has_r.groupby(g).transform("sum")
    loo_S, loo_N = S - r.fillna(0), N - has_r
    return np.where(loo_N >= min_n, loo_S / loo_N.clip(lower=1), np.nan).astype("float32")


def _build_features(df_in: pd.DataFrame, cal_flags: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    thr = cfg["full_avail_threshold"]
    df = df_in.sort_values(["unique_id", "date"]).reset_index(drop=True).copy()
    uid = df["unique_id"]
    df["is_uncensored"] = (df["availability"] >= thr).astype("int8")
    df["uncensored_sales"] = np.where(df["is_uncensored"] == 1, df["sales"], np.nan)
    df["dayofweek"] = df["date"].dt.dayofweek.astype("int8")
    unc = df.loc[df["is_uncensored"] == 1, ["unique_id", "dayofweek", "sales"]]
    # 1. lịch sử chỉ trên ngày đủ hàng (đến t−1)
    df["lag1_uncensored"] = _prev_ffill(df, unc["sales"], ["unique_id"]).astype("float32")
    for w, fn, name, mp in [(7, "mean", "rmean7_uncensored", 1), (28, "mean", "rmean28_uncensored", 1), (28, "std", "rstd28_uncensored", 2)]:
        df[name] = _prev_ffill(df, _roll(unc["sales"], [unc["unique_id"]], w, fn, mp), ["unique_id"]).astype("float32")
    last_unc = df["uncensored_sales"].groupby(uid).ffill()
    right = pd.DataFrame({"unique_id": uid, "date": df["date"], "v": last_unc}).sort_values("date")
    for k in (7, 14):
        left = pd.DataFrame({"unique_id": uid, "key": df["date"] - pd.Timedelta(days=k), "idx": df.index}).sort_values("key")
        m = pd.merge_asof(left, right, left_on="key", right_on="date", by="unique_id", direction="backward")
        df[f"lag{k}_uncensored"] = m.set_index("idx")["v"].reindex(df.index).astype("float32").values
    df["same_dow_mean_4w_uncensored"] = _prev_ffill(
        df, _roll(unc["sales"], [unc["unique_id"], unc["dayofweek"]], 4, "mean", 1), ["unique_id", "dayofweek"]).astype("float32")
    cens = 1 - df["is_uncensored"].astype("int32")
    block = df["is_uncensored"].astype("int32").groupby(uid).cumsum()
    run = cens.groupby([uid, block]).cumsum()
    df["consecutive_stockout_days"] = run.groupby(uid).shift(1).fillna(0).astype("float32")
    last_unc_date = pd.Series(np.where(df["is_uncensored"] == 1, df["date"].values.astype("datetime64[ns]"), np.datetime64("NaT")), index=df.index)
    prev_date = last_unc_date.groupby(uid).shift(1).groupby(uid).ffill()
    df["days_since_uncensored"] = (df["date"] - pd.to_datetime(prev_date)).dt.days.astype("float32")
    # 2. giá & khuyến mãi (giá quy EUR để các kho cùng thang)
    df["final_price_eur"] = (df["final_price"] * df["fx_eur"]).astype("float32")
    df["sell_price_main_eur"] = (df["sell_price_main"] * df["fx_eur"]).astype("float32")
    prev_price = df["final_price"].groupby(uid).shift(1)
    rmean28_price = prev_price.groupby(uid).rolling(28, min_periods=1).mean().reset_index(level=0, drop=True)
    df["price_rel_28d"] = (df["final_price"] / (rmean28_price + 1e-5)).astype("float32")
    prev_disc = df["max_discount"].groupby(uid).shift(1)
    rmean7_disc = prev_disc.groupby(uid).rolling(7, min_periods=1).mean().reset_index(level=0, drop=True)
    df["discount_jump"] = (df["max_discount"] - rmean7_disc.fillna(0)).astype("float32")
    df["active_promo_types"] = (df[DISCOUNT_COLS] > 0).sum(axis=1).astype("int8")
    # 3. áp lực cầu kho & ngành
    wh = (df.groupby(["warehouse", "date"])["total_orders"].median().rename("order_index").reset_index().sort_values(["warehouse", "date"]))
    wh["warehouse_rmean28_orders"] = (wh.groupby("warehouse")["order_index"].shift(1)
                                      .groupby(wh["warehouse"]).rolling(28, min_periods=7).mean().reset_index(level=0, drop=True))
    mm = df[["warehouse", "date"]].merge(wh[["warehouse", "date", "warehouse_rmean28_orders"]], on=["warehouse", "date"], how="left")
    df["warehouse_rmean28_orders"] = mm["warehouse_rmean28_orders"].values
    df["orders_rel_28d"] = (df["total_orders"] / (df["warehouse_rmean28_orders"] + 1e-5)).astype("float32")
    r = (df["uncensored_sales"] / df["rmean28_uncensored"]).where(df["rmean28_uncensored"] > 0).clip(0, 5)
    df["cat_L2_uncensored_index"] = _loo_index(r, df, ["warehouse", "L2", "date"], 3)
    df["wh_uncensored_index"] = _loo_index(r, df, ["warehouse", "date"], 3)
    if cfg["use_twin_index"]:
        df["twin_uncensored_index"] = _loo_index(r.where(df["product_unique_id"] >= 0), df, ["product_unique_id", "date"], 1)
    # 4. thời gian & lịch
    df["day"], df["month"] = df["date"].dt.day.astype("int8"), df["date"].dt.month.astype("int8")
    df["weekofyear"] = df["date"].dt.isocalendar().week.astype("int8").values
    df["sin_dow"] = np.sin(2 * np.pi * df["dayofweek"] / 7).astype("float32")
    df["cos_dow"] = np.cos(2 * np.pi * df["dayofweek"] / 7).astype("float32")
    mm = df[["warehouse", "date"]].merge(cal_flags, on=["warehouse", "date"], how="left")
    for c in ["is_pre_closed_or_holiday", "is_post_closed"]:
        df[c] = mm[c].fillna(0).astype("int8").values
    return df


FEATURES_NUM_ALL = [
    "lag1_uncensored", "lag7_uncensored", "lag14_uncensored", "rmean7_uncensored", "rmean28_uncensored",
    "rstd28_uncensored", "same_dow_mean_4w_uncensored", "consecutive_stockout_days", "days_since_uncensored",
    "final_price_eur", "sell_price_main_eur", "max_discount", *DISCOUNT_COLS, "price_rel_28d", "discount_jump", "active_promo_types",
    "total_orders", "orders_rel_28d", "cat_L2_uncensored_index", "wh_uncensored_index",
    "dayofweek", "day", "month", "weekofyear", "sin_dow", "cos_dow",
    "holiday", "shops_closed", "school_holidays", "winter_school_holidays", "is_pre_closed_or_holiday", "is_post_closed",
]


# ----------------------------------------------------------------------------------------------------------------
# 4. run_model
# ----------------------------------------------------------------------------------------------------------------
def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    log = _Log()
    d = _check_and_cut(inputs, cfg, log)
    as_of, start = pd.Timestamp(cfg["as_of"]), pd.Timestamp(cfg["train_start"])
    thr, seed = cfg["full_avail_threshold"], int(cfg["seed"])
    cur_map, fx = cfg["currency_by_warehouse"], cfg["fx_eur"]

    gold, cal = _build_gold(d, cfg, log)
    if cfg["impute_full_day_stockouts"]:
        df = _add_full_day_stockouts(gold, cal, cfg, log)
    else:
        df = gold.assign(stockout_type=np.where(gold["availability"] < thr, "partial_day", "none"), gap_len=0)
    unknown_wh = sorted(set(df["warehouse"]) - set(cur_map))
    if unknown_wh:
        raise ValueError(f"{BT_ID}: chưa khai báo tiền tệ cho kho {unknown_wh} (config currency_by_warehouse)")
    df["currency"] = df["warehouse"].map(cur_map)
    df["fx_eur"] = df["currency"].map(fx).astype("float32")

    del d
    feat = _build_features(df, _calendar_flags(cal), cfg)
    del df, gold                                   # giải phóng RAM trước khi huấn luyện (7 kho ≈ 3,6 triệu dòng)
    scope = _scope_warehouses(cfg)
    feat = feat[(feat["date"] >= start) & feat["warehouse"].isin(scope)].reset_index(drop=True)
    feats_num = list(FEATURES_NUM_ALL) + (["twin_uncensored_index"] if cfg["use_twin_index"] else [])
    const = [f for f in feats_num if feat[f].nunique(dropna=False) <= 1]
    feats_num = [f for f in feats_num if f not in const]
    feats_cat = ["unique_id", "warehouse", "L1", "L2", "L3"] + (["name_group"] if cfg["use_name_group"] else [])
    features = feats_num + feats_cat
    log.add("features", len(feat), len(feat), f"{len(features)} đặc trưng; loại hằng số: {const}")

    # 5. chia tập theo thời gian (chỉ ngày đủ hàng có nhãn thật)
    val_start = as_of - pd.Timedelta(days=int(cfg["val_days"]) - 1)
    inner_start = val_start - pd.Timedelta(days=int(cfg["inner_val_days"]))
    test14_start = as_of - pd.Timedelta(days=int(cfg["horizon"]) - 1)
    is_unc = feat["is_uncensored"] == 1
    m_train = (feat["date"] < val_start) & is_unc
    keep = list(dict.fromkeys(features + ["date", "sales", "weight", "rmean28_uncensored"]))
    test_df = feat.loc[(feat["date"] >= val_start) & is_unc, keep].reset_index(drop=True)
    train_inner = feat.loc[m_train & (feat["date"] < inner_start), keep].reset_index(drop=True)
    inner_val = feat.loc[m_train & (feat["date"] >= inner_start), keep].reset_index(drop=True)
    for nm, part in [("train_inner", train_inner), ("inner_val", inner_val), ("test_8w", test_df)]:
        if len(part) == 0:
            raise ValueError(f"{BT_ID}: tập {nm} rỗng – dữ liệu không đủ dài cho as_of {as_of.date()}")
    if cfg["mode"] != "evaluate":
        test_df = test_df.iloc[0:0]                 # chế độ models không chấm điểm → giải phóng RAM
    log.add("split", int(is_unc.sum()), len(train_inner),
            f"train_inner < {inner_start.date()} | inner_val {inner_start.date()}→{(val_start - pd.Timedelta(days=1)).date()} "
            f"({len(inner_val)}) | test {val_start.date()}→{as_of.date()} ({len(test_df)}) | censored {int((~is_unc).sum())}")

    # baseline M1 – fallback phân cấp SKU → (kho, L2) → (kho, L1) → toàn bộ (thống kê từ Train)
    train_df = feat.loc[m_train, ["unique_id", "warehouse", "L1", "L2", "sales"]]
    fb_sku = train_df.groupby("unique_id")["sales"].median()
    fb_l2 = train_df.groupby(["warehouse", "L2"], observed=True)["sales"].median()
    fb_l1 = train_df.groupby(["warehouse", "L1"], observed=True)["sales"].median()
    fb_all = float(train_df["sales"].median())
    del train_df

    def m1_predict(x):
        out = x["unique_id"].map(fb_sku).astype(float)
        k2 = pd.MultiIndex.from_arrays([x["warehouse"], x["L2"]])
        k1 = pd.MultiIndex.from_arrays([x["warehouse"], x["L1"]])
        out = out.fillna(pd.Series(fb_l2.reindex(k2).values, index=x.index)).fillna(pd.Series(fb_l1.reindex(k1).values, index=x.index))
        return x["rmean28_uncensored"].astype(float).fillna(out.fillna(fb_all)).clip(lower=0).values

    cat_levels = {c: sorted(feat[c].astype(str).unique()) for c in feats_cat}

    def prep(x):
        X = x[features].copy()
        for c in feats_cat:
            X[c] = _as_str_categorical(X[c], cat_levels[c])
        return X

    params = {**cfg["lgb_common"], **cfg["lgb_final"], "random_state": seed, "n_jobs": int(cfg["n_jobs"])}
    evaluate = cfg["mode"] == "evaluate"
    if not evaluate:
        best_iter = int((cfg.get("frozen") or {}).get("best_iter") or 0)
        if best_iter < 1:
            raise ValueError(f"{BT_ID}: chế độ models cần tham số chốt best_iter – chạy `evaluate` trước "
                             "hoặc kiểm tra config/model_params/BT3.json")
        model = lgb.LGBMRegressor(**{**params, "n_estimators": best_iter})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            model.fit(prep(train_inner), train_inner["sales"], sample_weight=train_inner["weight"])
        log.add("fit_final_model", len(train_inner), len(train_inner), f"{FINAL_MODEL} n_estimators={best_iter} (đã chốt)")
        comp = None
    else:
        model = lgb.LGBMRegressor(**params)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            warnings.filterwarnings("ignore", message=".*eval_set.*")
            model.fit(prep(train_inner), train_inner["sales"], sample_weight=train_inner["weight"],
                      eval_set=[(prep(inner_val), inner_val["sales"])], eval_sample_weight=[inner_val["weight"]], eval_metric="l1",
                      callbacks=[lgb.early_stopping(int(cfg["early_stopping_rounds"]), first_metric_only=True, verbose=False),
                                 lgb.log_evaluation(0)])
        best_iter = max(int(model.best_iteration_ or params["n_estimators"]), 50)
        log.add("fit_final_model", len(train_inner), len(inner_val), f"{FINAL_MODEL} best_iter={best_iter}; params={params}")

        pred_inner = {BASELINE_MODEL: m1_predict(inner_val),
                      FINAL_MODEL: np.clip(model.predict(prep(inner_val), num_iteration=best_iter), 0, None)}
        pred_test = {BASELINE_MODEL: m1_predict(test_df), FINAL_MODEL: np.clip(model.predict(prep(test_df)), 0, None)}
        y_iv, w_iv, y_te, w_te = inner_val["sales"].values, inner_val["weight"].values, test_df["sales"].values, test_df["weight"].values
        m14 = (test_df["date"] >= test14_start).values
        rows = []
        for name in [BASELINE_MODEL, FINAL_MODEL]:
            p = pred_test[name]
            rows.append({"model": name, "WMAE": wmae(y_te, p, w_te), "WMAE_test14": wmae(y_te[m14], p[m14], w_te[m14]),
                         "WMAE_innerval": wmae(y_iv, pred_inner[name], w_iv), "WMAPE_pct": wmape_pct(y_te, p, w_te), "RMSE": rmse(y_te, p),
                         "Bias_pct": bias_pct(y_te, p), "Bias_w_pct": bias_w_pct(y_te, p, w_te),
                         "best_iter": best_iter if name == FINAL_MODEL else 0})
        comp = pd.DataFrame(rows)
        comp["bias_%"] = comp["Bias_pct"]
        comp["selected"] = comp["model"] == FINAL_MODEL
        comp["role"] = np.where(comp["selected"], "final (đã chọn trong notebook theo min WMAE inner-val trong M1–M5)", "baseline")
        comp["selection_rule"] = ("final cố định = M4_LightGBM_Tweedie (chọn trong original_notebook theo min WMAE inner-val "
                                  f"{inner_start.date()}..{(val_start - pd.Timedelta(days=1)).date()}); WMAE = Test 8 tuần "
                                  f"{val_start.date()}..{as_of.date()} chỉ báo cáo")
        comp["scope"] = f"{len(scope)} kho {start.date()}..{as_of.date()}"

    # 6. ước lượng nhu cầu cho ngày thiếu hàng + quy tắc an toàn
    cens = feat["is_uncensored"] == 0
    pred_cens = (np.clip(model.predict(prep(feat.loc[cens]), num_iteration=best_iter), 0, None)
                 if cens.any() else np.array([]))
    q99 = feat.loc[~cens].groupby("unique_id")["sales"].quantile(0.99)
    cap = np.maximum(cfg["demand_cap_mult"] * feat["rmean28_uncensored"].astype(float), feat["unique_id"].map(q99)).fillna(np.inf).values
    pred_full = np.full(len(feat), np.nan)
    pred_full[cens.values] = pred_cens
    capped = np.minimum(pred_full, cap)
    est = np.where(cens.values, np.maximum(feat["sales"].values, capped), feat["sales"].values)
    n_capped = int(np.sum(cens.values & (pred_full > cap)))
    log.add("estimate_censored", int(cens.sum()), int(cens.sum()), f"{n_capped} dòng bị kẹp trần {cfg['demand_cap_mult']}×TB28 / P99")

    lost = feat[["unique_id", "date", "warehouse", "L1", "sales", "availability", "final_price", "currency", "stockout_type"]].copy()
    lost["est_demand"] = est
    lost["lost_units"] = np.maximum(0, lost["est_demand"] - lost["sales"])
    lost["lost_revenue"] = lost["lost_units"] * lost["final_price"]
    lost["lost_revenue_eur"] = lost["lost_revenue"] * lost["currency"].map(fx)
    lost["model"] = FINAL_MODEL
    lost = lost[["unique_id", "date", "warehouse", "L1", "sales", "availability", "final_price", "currency", "est_demand",
                 "lost_units", "lost_revenue", "lost_revenue_eur", "stockout_type", "model"]]
    lost = lost.sort_values(["unique_id", "date"]).reset_index(drop=True)

    # 7. tổng hợp (nội tệ của kho + EUR quy đổi)
    g = lost.assign(rev=lost["sales"] * lost["final_price"], so=(lost["availability"] < thr).astype(float),
                    lr_partial=np.where(lost["stockout_type"] == "partial_day", lost["lost_revenue"], 0.0),
                    lr_full=np.where(lost["stockout_type"] == "full_day_imputed", lost["lost_revenue"], 0.0),
                    is_full=(lost["stockout_type"] == "full_day_imputed").astype(int))
    summ = (g.groupby(["warehouse", "L1"]).agg(stockout_days_share=("so", "mean"), revenue=("rev", "sum"), lost_revenue=("lost_revenue", "sum"),
                                               lost_revenue_partial_day=("lr_partial", "sum"), lost_revenue_full_day_imputed=("lr_full", "sum"),
                                               sku_days=("so", "size"), full_day_imputed_days=("is_full", "sum")).reset_index())
    pct = lambda a, b: np.where(b > 0, a / np.where(b > 0, b, 1) * 100, 0.0)  # noqa: E731
    summ["lost_%_of_revenue"] = pct(summ["lost_revenue"], summ["revenue"])
    summ["lost_%_partial_day"] = pct(summ["lost_revenue_partial_day"], summ["revenue"])
    summ["lost_%_full_day_imputed"] = pct(summ["lost_revenue_full_day_imputed"], summ["revenue"])
    summ["currency"] = summ["warehouse"].map(cur_map)
    summ["revenue_eur"] = summ["revenue"] * summ["currency"].map(fx)
    summ["lost_revenue_eur"] = summ["lost_revenue"] * summ["currency"].map(fx)
    first = ["warehouse", "L1", "stockout_days_share", "revenue", "lost_revenue", "lost_%_of_revenue", "currency", "revenue_eur", "lost_revenue_eur"]
    summ = summ[first + [c for c in summ.columns if c not in first]]

    mon = (g.assign(month=g["date"].dt.to_period("M").dt.to_timestamp())
            .groupby(["warehouse", "L1", "month"]).agg(revenue=("rev", "sum"), lost_revenue=("lost_revenue", "sum"),
                                                       lost_revenue_full_day_imputed=("lr_full", "sum")).reset_index())
    mon["currency"] = mon["warehouse"].map(cur_map)
    mon["revenue_eur"] = mon["revenue"] * mon["currency"].map(fx)
    mon["lost_revenue_eur"] = mon["lost_revenue"] * mon["currency"].map(fx)

    log.add("outputs", len(feat), len(lost), f"lost_sales {len(lost)} | summary {len(summ)} | monthly {len(mon)}")
    outputs = {"lost_sales": lost, "lost_sales_summary": summ, "lost_sales_monthly": mon, "run_log": log.frame()}
    if evaluate:
        outputs["bt3_model_comparison"] = comp
        outputs["_params"] = {"best_iter": int(best_iter), "final_model": FINAL_MODEL}
    validate_outputs(outputs, cfg)
    return outputs


# ----------------------------------------------------------------------------------------------------------------
# 5. Kiểm tra hợp đồng đầu ra
# ----------------------------------------------------------------------------------------------------------------
CONTRACT = {
    "lost_sales": {"cols": ["unique_id", "date", "warehouse", "L1", "sales", "availability", "final_price", "currency", "est_demand",
                            "lost_units", "lost_revenue", "lost_revenue_eur"], "keys": ["unique_id", "date"],
                   "nonneg": ["sales", "availability", "final_price", "est_demand", "lost_units", "lost_revenue", "lost_revenue_eur"]},
    "lost_sales_summary": {"cols": ["warehouse", "L1", "stockout_days_share", "revenue", "lost_revenue", "lost_%_of_revenue",
                                    "revenue_eur", "lost_revenue_eur"], "keys": ["warehouse", "L1"],
                           "nonneg": ["stockout_days_share", "revenue", "lost_revenue", "lost_%_of_revenue", "revenue_eur", "lost_revenue_eur"]},
    "lost_sales_monthly": {"cols": ["warehouse", "L1", "month", "revenue", "lost_revenue", "revenue_eur", "lost_revenue_eur"],
                           "keys": ["warehouse", "L1", "month"], "nonneg": ["revenue", "lost_revenue", "revenue_eur", "lost_revenue_eur"]},
    "bt3_model_comparison": {"cols": ["model", "WMAE", "WMAE_innerval", "selected"], "keys": ["model"], "nonneg": ["WMAE"]},
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
            errs.append(f"{name}: trùng khoá {c['keys']} ({int(df.duplicated(c['keys']).sum())} dòng)")
        if df[c["cols"]].isna().any().any():
            errs.append(f"{name}: NaN ở cột {list(df[c['cols']].columns[df[c['cols']].isna().any()])}")
        for col in c["nonneg"]:
            if (pd.to_numeric(df[col], errors="coerce") < -1e-9).any():
                errs.append(f"{name}: {col} có giá trị âm")
    if not errs:
        as_of, start = pd.Timestamp(cfg["as_of"]), pd.Timestamp(cfg["train_start"])
        ls = outputs["lost_sales"]
        dt = pd.to_datetime(ls["date"])
        if dt.min() < start or dt.max() > as_of:
            errs.append(f"lost_sales: ngày {dt.min().date()}→{dt.max().date()} ngoài {start.date()}→{as_of.date()}")
        if (ls["est_demand"] < ls["sales"] - 1e-6).any():
            errs.append("lost_sales: est_demand < sales")
        if not np.allclose(ls["lost_units"], ls["est_demand"] - ls["sales"], atol=1e-6):
            errs.append("lost_sales: lost_units ≠ est_demand − sales")
        if not np.allclose(ls.loc[ls["availability"] >= cfg["full_avail_threshold"], "lost_units"], 0):
            errs.append("lost_sales: ngày đủ hàng có lost_units > 0")
        exp = set(_scope_warehouses(cfg))
        for name in ["lost_sales", "lost_sales_summary", "lost_sales_monthly"]:
            got = set(outputs[name]["warehouse"].astype(str))
            if got != exp:
                errs.append(f"{name}: kho {sorted(got)} ≠ phạm vi {sorted(exp)}")
        if not (pd.to_datetime(outputs["lost_sales_monthly"]["month"]).dt.day == 1).all():
            errs.append("lost_sales_monthly: month phải là ngày đầu tháng")
        if not outputs["lost_sales_summary"]["stockout_days_share"].between(0, 1).all():
            errs.append("lost_sales_summary: stockout_days_share ngoài [0,1]")
        if "bt3_model_comparison" in outputs and int(outputs["bt3_model_comparison"]["selected"].astype(bool).sum()) != 1:
            errs.append("bt3_model_comparison: phải có đúng 1 mô hình selected")
    if errs:
        raise ValueError(f"{BT_ID} output sai hợp đồng: " + "; ".join(errs))
