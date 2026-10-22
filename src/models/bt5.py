"""BT5 – Đo hiệu ứng nhân quả của giảm giá lên doanh số (Rohlik Decision Hub) – bản TINH GỌN để tích hợp pipeline.

Phương pháp final (Nam duyệt 22/10/2026, khớp số BT7 đã dùng): E2 – FE SKU + biến kiểm soát
  log(1+sales) ~ θ_L1·T + W + thứ + tháng | SKU, W = log TB 28 ngày, log lag14, log giá, log order_index t−14, xu hướng, lịch;
  sai số chuẩn gom theo SKU (CRV1).
  lift_% bàn giao = ước lượng THEO MỨC (biến giả mức giảm (5,15], (15,25], (25,35]% … cùng đặc tả), ô không có
  dữ liệu → dạng e^{θd} + cảnh báo (đúng hàm build_promo_effect của notebook, mục 8.1; bỏ bootstrap cụm SKU).
Phương pháp so sánh (chỉ khi evaluate): M1a – FE SKU + (kho × ngày).
Hai chế độ (D06): mode="models" chỉ ước lượng E2 → promo_effect + promo_type_effect (do_tin_cay lấy từ tham số chốt);
mode="evaluate" thêm M1a, placebo (xáo T trong SKU, tiêu chí đã sửa: KTC giả chứa 0 và |lift giả| ≤ max(1 điểm %,
10% lift thật) ở mọi ngành, đạt ≥ 80% số hoán vị), độ nhạy ngày đủ hàng; trả "_params".
Bỏ so với notebook (chỉ có ở original_notebook.ipynb): EDA, SMD/IPW, E1/M1b/M2 PPML/E3 DML/M4 DR-Learner, placebo nhiều
hoán vị, benchmark bán-tổng hợp, event study, RV, chẩn đoán PPML, đổi mẫu, bootstrap cụm SKU, biểu đồ, model card.

Giao diện: run_model(*, inputs, config, artifact_dir) -> dict[str, DataFrame]; không đọc/ghi file, không trạng thái toàn cục.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyfixest as pf

BT_ID = "BT5"
REQUIRED_INPUTS = ["sku_sales_daily", "prices", "promotions", "product_master", "calendar"]
OPTIONAL_INPUTS = ["availability"]          # chỉ dùng cho dòng độ nhạy "ngày đủ hàng" trong bt5_method_comparison
UPSTREAM: dict[str, tuple[str, str]] = {}  # BT5 không phụ thuộc BT khác
OUTPUTS = ["promo_effect", "promo_type_effect", "bt5_method_comparison", "run_log"]
FAST_INPUTS = REQUIRED_INPUTS
FAST_OUTPUTS = ["promo_effect", "promo_type_effect", "run_log"]

TYPE_COLS = [f"type_{i}_discount" for i in range(7)]
CAL_COLS = ["holiday", "shops_closed", "winter_school_holidays", "school_holidays"]
CTRL_FE = ["log_roll28", "log_lag14", "lag14_missing", "log_price"]            # W của M1a (lịch nằm trong FE kho×ngày)
CTRL_E2 = CTRL_FE + ["log_orders", "trend"] + CAL_COLS                         # W của E2 (không có FE ngày)
FINAL_METHOD = "E2 FE SKU + kiểm soát"
COMPARE_METHOD = "M1a FE SKU + kho×ngày"

REQUIRED_COLUMNS = {
    "sku_sales_daily": ["unique_id", "date", "warehouse", "sales", "total_orders"],
    "prices": ["unique_id", "date", "sell_price_main"],
    "promotions": ["unique_id", "date"] + TYPE_COLS,
    "product_master": ["unique_id", "L1_category_name_en", "L3_category_name_en", "warehouse"],
    "calendar": ["warehouse", "date"] + CAL_COLS,
    "availability": ["unique_id", "date", "availability"],
}

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",
    "train_start": "2020-12-05",
    "horizon": 14,                  # không dùng để dự báo (BT5 là ước lượng); chỉ để cắt calendar ≤ as_of + horizon
    "seed": 42,
    "warehouses": None,             # None = mọi kho có trong sku_sales_daily
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},   # ASSUMED; BT5 không cộng tiền nên không dùng
    "discount_levels": [0.1, 0.2, 0.3],
    "level_edges": [0.0, 0.05, 0.15, 0.25, 0.35, 1.0],   # mức: (0,5%] | (5,15%] | (15,25%] | (25,35%] | >35%
    "level_codes": ["d05", "d10", "d20", "d30", "d35p"],
    "level_of": {"d10": 0.1, "d20": 0.2, "d30": 0.3},
    "roll_days": 28, "roll_min_periods": 7, "lag_days": 14,
    "alpha": 0.05,
    "min_support_share": 0.01,      # ô (L1, mức) có < 1% SKU-ngày của ngành → cảnh báo "ít dữ liệu"
    "min_promo_rows": 300,          # loại KM cần ≥ 300 dòng có giảm giá mới ước lượng θ
    "placebo_perms": 3,             # số hoán vị T trong SKU khi evaluate
    "placebo_tol": 1.0,             # |lift 20% giả| ≤ max(1 điểm %, placebo_rel_max × |lift thật|) ở mọi ngành
    "placebo_rel_max": 0.10,
    "placebo_pass_rate": 0.8,       # phương pháp đạt nếu ≥ 80% số hoán vị đạt
    "availability_full": 0.99,      # ngưỡng "ngày đủ hàng" cho dòng độ nhạy
    "n_jobs": 1,                    # không dùng (pyfixest chạy 1 luồng ở đây); giữ cho giao diện chung
    "required_inputs": list(REQUIRED_INPUTS),
    "mode": "evaluate",             # "models" | "evaluate"
    "frozen": None,                 # {"do_tin_cay": "cao"/"thấp", "placebo_pass_rate": float}
}

PE_COLS = ["L1", "discount", "theta", "lift_%", "ci_low_%", "ci_high_%"]


# ---------------------------------------------------------------- tiện ích
def _log(log: list, step: str, rows_in, rows_out, note: str) -> None:
    log.append({"step": step, "rows_in": int(rows_in), "rows_out": int(rows_out), "note": note})


def _to_date(df: pd.DataFrame, name: str) -> pd.DataFrame:
    try:
        df["date"] = pd.to_datetime(df["date"])
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"{name}: cột 'date' không chuyển được sang ngày ({e})") from e
    return df


def _cut(df, name, lo, hi, log):
    n0 = len(df)
    out = df[(df["date"] >= lo) & (df["date"] <= hi)].copy()
    _log(log, f"cut_{name}", n0, len(out), f"giữ {lo.date()} ≤ date ≤ {hi.date()} (chống rò rỉ)")
    return out


def _dedupe(df, keys, name, log):
    n0 = len(df)
    out = df.sort_values(keys).drop_duplicates(keys, keep="last")
    if len(out) < n0:
        _log(log, f"dedupe_{name}", n0, len(out), f"khử trùng khoá {keys}, giữ bản ghi cuối")
    return out


def lift_pct(theta, d):
    return (np.exp(np.asarray(theta, float) * np.asarray(d, float)) - 1) * 100


def _theta_by_l1(fit, l1_list, alpha):
    coef, ci = fit.coef(), fit.confint(alpha=alpha)
    rows = []
    for l1 in l1_list:
        k = f"L1::{l1}:T"
        if k in coef.index and np.isfinite(coef[k]):
            rows.append({"L1": l1, "theta": coef[k], "lo": ci.loc[k].iloc[0], "hi": ci.loc[k].iloc[1]})
    return pd.DataFrame(rows, columns=["L1", "theta", "lo", "hi"])


def _lift_table(theta_df, levels):
    rows = []
    for _, r in theta_df.iterrows():
        for lvl in levels:
            rows.append({"L1": r["L1"], "discount": lvl, "theta": r["theta"], "lift_%": float(lift_pct(r["theta"], lvl)),
                         "ci_low_%": float(lift_pct(r["lo"], lvl)), "ci_high_%": float(lift_pct(r["hi"], lvl))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- đặc tả mô hình
def _spec(method: str):
    """(hàm pyfixest, biến kết quả, phần kiểm soát + FE) – 7 kho: FE ngày của M1a là kho × ngày."""
    if method.startswith("M1a"):
        return pf.feols, "Y", f"{' + '.join(CTRL_FE)} | unique_id + warehouse^date"
    if method.startswith("E2"):
        return pf.feols, "Y", f"{' + '.join(CTRL_E2)} + C(dow) + C(month) | unique_id"
    raise ValueError(method)


def _fit_theta(d, method, l1_list, alpha):
    est, y, rhs = _spec(method)
    fit = est(f"{y} ~ i(L1, T) + {rhs}", data=d, vcov={"CRV1": "unique_id"})
    return _theta_by_l1(fit, l1_list, alpha)


def _lift_by_level(d, method, l1_list, cfg):
    """Mỗi mức giảm × ngành có biến giả riêng; θ cục bộ = β ÷ mức giảm TB thật trong mức (notebook mục 5.0b)."""
    est, y, rhs = _spec(method)
    d = d.copy()
    codes = pd.cut(d["T"], bins=cfg["level_edges"], labels=cfg["level_codes"]).astype(str).values
    for c in cfg["level_codes"]:
        d[f"D_{c}"] = (codes == c).astype(float)
    fit = est(f"{y} ~ " + " + ".join(f"i(L1, D_{c})" for c in cfg["level_codes"]) + f" + {rhs}",
              data=d, vcov={"CRV1": "unique_id"})
    coef, ci = fit.coef(), fit.confint(alpha=cfg["alpha"])
    rows = []
    for l1 in l1_list:
        in_l1 = (d["L1"] == l1).values
        for c, lvl in cfg["level_of"].items():
            k, m = f"L1::{l1}:D_{c}", in_l1 & (codes == c)
            if k not in coef.index or m.sum() == 0 or not np.isfinite(coef[k]):
                continue
            d_bar = d.loc[m, "T"].mean()
            th, lo, hi = coef[k] / d_bar, ci.loc[k].iloc[0] / d_bar, ci.loc[k].iloc[1] / d_bar
            rows.append({"L1": l1, "discount": lvl, "theta": th, "lift_%": float(lift_pct(th, lvl)),
                         "ci_low_%": float(lift_pct(lo, lvl)), "ci_high_%": float(lift_pct(hi, lvl)),
                         "d_tb_trong_muc": d_bar, "n_rows_support": int(m.sum()),
                         "support_share_%": m.sum() / in_l1.sum() * 100})
    return pd.DataFrame(rows)


def _build_promo_effect(theta_tab, lv, l1_list, cfg):
    levels = cfg["discount_levels"]
    exp_form = theta_tab.rename(columns={"theta": "theta_exp", "lift_%": "lift_exp_theta_%",
                                         "ci_low_%": "ci_low_exp_%", "ci_high_%": "ci_high_exp_%"})
    grid = pd.DataFrame([(l1, lvl) for l1 in l1_list for lvl in levels], columns=["L1", "discount"])
    pe = grid.merge(lv, on=["L1", "discount"], how="left") if len(lv) else grid.assign(
        theta=np.nan, **{"lift_%": np.nan, "ci_low_%": np.nan, "ci_high_%": np.nan},
        d_tb_trong_muc=np.nan, n_rows_support=np.nan, **{"support_share_%": np.nan})
    pe = pe.merge(exp_form, on=["L1", "discount"], how="left")
    miss = pe["lift_%"].isna()
    pe["nguon_lift"] = np.where(miss, "dang_e_mu_theta", "theo_muc")
    for a, b in [("theta", "theta_exp"), ("lift_%", "lift_exp_theta_%"), ("ci_low_%", "ci_low_exp_%"),
                 ("ci_high_%", "ci_high_exp_%")]:
        pe.loc[miss, a] = pe.loc[miss, b]
    pe["n_rows_support"] = pe["n_rows_support"].fillna(0).astype(int)
    pe["support_share_%"] = pe["support_share_%"].fillna(0.0)
    pe["method"], pe["kich_ban"] = FINAL_METHOD, "co_so"

    def warn(r):
        w = []
        if r["nguon_lift"] != "theo_muc":
            w.append("không có dữ liệu ở mức này – dùng dạng e^(θd), là ngoại suy")
        elif r["support_share_%"] < cfg["min_support_share"] * 100:
            w.append("ít dữ liệu (<1% SKU-ngày của ngành) – gần như ngoại suy")
        if r["ci_low_%"] <= 0 <= r["ci_high_%"]:
            w.append("KTC chứa 0 – chưa khác 0 có ý nghĩa")
        if pd.notna(r["lift_exp_theta_%"]) and r["lift_exp_theta_%"] > r["ci_high_%"]:
            w.append("dạng e^(θd) vượt cận trên của ước lượng theo mức – không dùng dạng e^(θd) ở mức này")
        return "; ".join(w) if w else "-"

    pe["canh_bao"] = pe.apply(warn, axis=1)
    cols = PE_COLS + ["method", "kich_ban", "nguon_lift", "n_rows_support", "support_share_%", "d_tb_trong_muc",
                      "theta_exp", "lift_exp_theta_%", "canh_bao"]
    return pe[cols].sort_values(["L1", "discount"]).reset_index(drop=True)


# ---------------------------------------------------------------- chuẩn bị dữ liệu
def _prepare(inputs, cfg, log):
    as_of, start = pd.Timestamp(cfg["as_of"]), pd.Timestamp(cfg["train_start"])
    cal_end = as_of + pd.Timedelta(days=int(cfg["horizon"]))
    t = {}
    for name in REQUIRED_INPUTS + OPTIONAL_INPUTS:
        if name not in inputs or inputs[name] is None:
            continue
        df = inputs[name].copy()                                     # không sửa input tại chỗ
        miss = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
        if miss:
            raise ValueError(f"{name}: thiếu cột bắt buộc {miss}")
        if "date" in REQUIRED_COLUMNS[name]:
            df = _to_date(df, name)
            df = _cut(df, name, start, cal_end if name == "calendar" else as_of, log)
        t[name] = df

    s = t["sku_sales_daily"]
    whs = sorted(s["warehouse"].dropna().unique())
    if cfg.get("warehouses"):
        lack = sorted(set(cfg["warehouses"]) - set(whs))
        if lack:
            raise ValueError(f"sku_sales_daily thiếu dữ liệu của kho {lack} (config.warehouses)")
        n0 = len(s)
        s = s[s["warehouse"].isin(cfg["warehouses"])]
        _log(log, "filter_warehouses", n0, len(s), f"giữ kho {list(cfg['warehouses'])}")
        whs = sorted(cfg["warehouses"])
    if len(s) == 0:
        raise ValueError("sku_sales_daily rỗng sau khi cắt mốc")

    # order_index theo (warehouse, date) = trung vị total_orders của các SKU; total_orders NULL bị bỏ qua
    n_null_to = int(s["total_orders"].isna().sum())
    oi = s.dropna(subset=["total_orders"]).groupby(["warehouse", "date"])["total_orders"].median()
    _log(log, "order_index", len(s), len(oi), f"trung vị total_orders theo (warehouse, date); bỏ qua {n_null_to} NULL")

    s = _dedupe(s, ["unique_id", "date"], "sku_sales_daily", log)
    n0 = len(s)
    s = s[s["sales"].notna() & (s["sales"] >= 0)]
    _log(log, "drop_sales_null_negative", n0, len(s), "sales NULL/âm → loại khỏi tập ước lượng (không điền 0)")

    # JOIN SKU-ngày (khoá unique_id + date), left join giữ grain sku_sales_daily
    pr = _dedupe(t["prices"][["unique_id", "date", "sell_price_main"]], ["unique_id", "date"], "prices", log)
    pm = _dedupe(t["promotions"][["unique_id", "date"] + TYPE_COLS], ["unique_id", "date"], "promotions", log)
    d = s.merge(pr, on=["unique_id", "date"], how="left").merge(pm, on=["unique_id", "date"], how="left")
    n0 = len(d)
    d = d[d["sell_price_main"].notna() & (d["sell_price_main"] > 0)]
    _log(log, "drop_price_invalid", n0, len(d), "sell_price_main NULL hoặc ≤ 0 → loại (như notebook 3.1)")
    n_neg = int((d[TYPE_COLS] < 0).sum().sum())
    n_na = int(d[TYPE_COLS].isna().sum().sum())
    d[TYPE_COLS] = d[TYPE_COLS].fillna(0).clip(0, 1)
    _log(log, "clip_discount", len(d), len(d), f"{n_neg} discount âm → 0; {n_na} ô NULL/không có dòng promotions → 0; kẹp [0,1]")
    d["T"] = d[TYPE_COLS].max(axis=1)                                 # T = max_discount

    # product_master: khoá unique_id
    pmast = t["product_master"].drop_duplicates("unique_id", keep="last")[
        ["unique_id", "L1_category_name_en", "L3_category_name_en"]].rename(
        columns={"L1_category_name_en": "L1", "L3_category_name_en": "L3"})
    d = d.merge(pmast, on="unique_id", how="left")
    n0 = len(d)
    d = d[d["L1"].notna()]
    _log(log, "join_product_master", n0, len(d), "JOIN unique_id; dòng thiếu L1 bị loại")

    # calendar: khoá warehouse + date
    cal = t["calendar"].drop_duplicates(["warehouse", "date"], keep="last")[["warehouse", "date"] + CAL_COLS]
    d = d.merge(cal, on=["warehouse", "date"], how="left")
    n_cal_na = int(d[CAL_COLS].isna().any(axis=1).sum())
    d[CAL_COLS] = d[CAL_COLS].fillna(0).astype(int)
    _log(log, "join_calendar", len(d), len(d), f"JOIN (warehouse, date); {n_cal_na} dòng không có lịch → ngày thường (0)")

    has_av = "availability" in t
    if has_av:
        av = _dedupe(t["availability"][["unique_id", "date", "availability"]], ["unique_id", "date"], "availability", log)
        d = d.merge(av, on=["unique_id", "date"], how="left")
        _log(log, "join_availability", len(d), len(d), "JOIN (unique_id, date); chỉ dùng cho dòng độ nhạy ngày đủ hàng, KHÔNG là biến kiểm soát (biến trung gian)")
    else:
        _log(log, "join_availability", 0, 0, "không có input availability → bỏ dòng độ nhạy ngày đủ hàng")

    # Đặc trưng trước can thiệp (theo ngày lịch thật, lùi 14 ngày)
    d = d.sort_values(["unique_id", "date"]).reset_index(drop=True)
    lag = int(cfg["lag_days"])
    roll = (d.set_index("date").groupby("unique_id")["sales"]
            .rolling(f"{int(cfg['roll_days'])}D", min_periods=int(cfg["roll_min_periods"])).mean()
            .reset_index().rename(columns={"sales": "roll28"}))
    roll["date"] = roll["date"] + pd.Timedelta(days=lag)
    d = d.merge(roll, on=["unique_id", "date"], how="left")
    lg = d[["unique_id", "date", "sales"]].copy()
    lg["date"] = lg["date"] + pd.Timedelta(days=lag)
    d = d.merge(lg.rename(columns={"sales": "lag14"}), on=["unique_id", "date"], how="left")
    d["log_roll28"] = np.log1p(d["roll28"])
    d["log_lag14"] = np.log1p(d["lag14"])
    d["lag14_missing"] = d["lag14"].isna().astype(int)
    d["log_lag14"] = d["log_lag14"].fillna(d["log_roll28"])
    d["log_price"] = np.log(d["sell_price_main"])
    # log order_index của chính kho, ngày t−14 (tránh biến hậu can thiệp); thiếu → trung vị log order_index của kho
    log_oi = np.log(oi.rename("oi")).reset_index()
    log_oi["date"] = log_oi["date"] + pd.Timedelta(days=lag)
    d = d.merge(log_oi.rename(columns={"oi": "log_orders"}), on=["warehouse", "date"], how="left")
    med = np.log(oi).groupby(level="warehouse").median()
    d["log_orders"] = d["log_orders"].fillna(d["warehouse"].map(med))
    d["dow"] = d["date"].dt.dayofweek
    d["month"] = d["date"].dt.month
    d["trend"] = (d["date"] - start).dt.days / 365
    d["Y"] = np.log1p(d["sales"])
    n0 = len(d)
    data = d[d["roll28"].notna()].reset_index(drop=True)
    _log(log, "estimation_sample", n0, len(data),
         f"chỉ giữ dòng có roll28 (≥ {cfg['roll_min_periods']} ngày lịch sử, lùi {lag} ngày); "
         f"{data['unique_id'].nunique()} SKU, {data['warehouse'].nunique()} kho, "
         f"{data['date'].min().date()} → {data['date'].max().date()}")
    if data.empty:
        raise ValueError("Không còn dòng nào để ước lượng sau khi tạo biến trễ")
    return data, whs, has_av


# ---------------------------------------------------------------- chạy chính
def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    missing = sorted(set(cfg["required_inputs"]) - {k for k, v in (inputs or {}).items() if v is not None})
    if missing:
        raise ValueError(f"Missing model inputs: {missing}")
    log: list = []
    _log(log, "config", 0, 0, f"as_of={cfg['as_of']}, train_start={cfg['train_start']}, seed={cfg['seed']}, "
                              f"final={FINAL_METHOD}, so_sanh={COMPARE_METHOD}, levels={cfg['discount_levels']}")
    data, whs, has_av = _prepare(inputs, cfg, log)
    l1_list = sorted(data["L1"].unique())
    levels = cfg["discount_levels"]
    alpha = cfg["alpha"]

    # 1) Final M1a: θ (dạng e^{θd}) + lift theo mức → promo_effect
    t0 = time.time()
    th_final = _fit_theta(data, FINAL_METHOD, l1_list, alpha)
    lt_final = _lift_table(th_final, levels)
    lv = _lift_by_level(data, FINAL_METHOD, l1_list, cfg)
    promo_effect = _build_promo_effect(lt_final, lv, l1_list, cfg)
    sec_final = time.time() - t0
    lacking_l1 = sorted(set(l1_list) - set(th_final["L1"]))
    if lacking_l1:
        raise ValueError(f"Không ước lượng được θ cho ngành {lacking_l1} (không có biến thiên giảm giá trong SKU)")
    _log(log, "final_promo_effect", len(data), len(promo_effect),
         f"{int((promo_effect['nguon_lift'] == 'theo_muc').sum())} ô theo mức, "
         f"{int((promo_effect['nguon_lift'] != 'theo_muc').sum())} ô dạng e^(θd); KTC = CRV1 gom theo SKU")

    evaluate = cfg["mode"] == "evaluate"
    comparison, do_tin_cay, pass_rate = None, None, None
    if evaluate:
        # 2) Phương pháp so sánh M1a
        t0 = time.time()
        lt_cmp = _lift_table(_fit_theta(data, COMPARE_METHOD, l1_list, alpha), levels)
        sec_cmp = time.time() - t0

        # 3) Placebo: xáo T trong cùng SKU (numpy Generator(seed)), tiêu chí đã sửa (P1–P3)
        rng = np.random.default_rng(int(cfg["seed"]))
        real20 = {FINAL_METHOD: lt_final[lt_final["discount"] == 0.2].set_index("L1")["lift_%"],
                  COMPARE_METHOD: lt_cmp[lt_cmp["discount"] == 0.2].set_index("L1")["lift_%"]}
        plc = {FINAL_METHOD: [], COMPARE_METHOD: []}
        for _ in range(int(cfg["placebo_perms"])):
            dp = data.copy()
            dp["T"] = dp.groupby("unique_id")["T"].transform(lambda v: rng.permutation(v.values)).values
            for m in plc:
                tab = _lift_table(_fit_theta(dp, m, l1_list, alpha), [0.2]).set_index("L1")
                ok = True
                for l1, r in tab.iterrows():
                    tol = max(float(cfg["placebo_tol"]), float(cfg["placebo_rel_max"]) * abs(float(real20[m].get(l1, 0.0))))
                    ok &= bool(r["ci_low_%"] <= 0 <= r["ci_high_%"]) and abs(float(r["lift_%"])) <= tol
                plc[m].append((float(tab["lift_%"].abs().max()) if len(tab) else np.nan, ok))
        rates = {m: float(np.mean([ok for _, ok in v])) if v else np.nan for m, v in plc.items()}
        pass_rate = rates[FINAL_METHOD]
        do_tin_cay = "cao" if pass_rate >= float(cfg["placebo_pass_rate"]) else "thấp"
        _log(log, "placebo", len(data), int(cfg["placebo_perms"]),
             f"tỷ lệ hoán vị đạt: {rates}; final {FINAL_METHOD} → độ tin cậy {do_tin_cay}")

        # 4) Bảng so sánh
        w_l1 = data["L1"].value_counts()

        def comp_row(name, tab, sec, role, final, plc_vals, sub):
            t20 = tab[tab["discount"] == 0.2].set_index("L1")
            r = {"method": name, "vai_tro": role, "final": final}
            for l1 in l1_list:
                r[f"theta_{l1}"] = t20["theta"].get(l1, np.nan)
                r[f"lift20_{l1}_%"] = t20["lift_%"].get(l1, np.nan)
            r["lift20_binh_quan_%"] = float(np.average(t20["lift_%"], weights=w_l1.reindex(t20.index)))
            r["do_rong_KTC20_%"] = float((t20["ci_high_%"] - t20["ci_low_%"]).mean())
            if plc_vals is not None:
                r["placebo_max_abs_lift20_%"] = float(np.nanmax([v for v, _ in plc_vals]))
                r["placebo_ty_le_dat"] = float(np.mean([ok for _, ok in plc_vals]))
                r["placebo_ok"] = int(r["placebo_ty_le_dat"] >= float(cfg["placebo_pass_rate"]))
            else:
                r["placebo_max_abs_lift20_%"], r["placebo_ty_le_dat"], r["placebo_ok"] = np.nan, np.nan, -1
            r["n_rows"], r["n_sku"], r["n_warehouses"] = len(sub), sub["unique_id"].nunique(), sub["warehouse"].nunique()
            r["giay_chay"] = round(sec, 2)
            r["lift_source"] = "dang_e_mu_theta (θ đơn, cùng cách notebook mục 7.1)"
            return r

        rows = [comp_row(FINAL_METHOD, lt_final, sec_final, "final – promo_effect", 1, plc[FINAL_METHOD], data),
                comp_row(COMPARE_METHOD, lt_cmp, sec_cmp, "so sánh (FE SKU + kho×ngày)", 0, plc[COMPARE_METHOD], data)]
        if has_av:
            full = data[data["availability"] >= cfg["availability_full"]].reset_index(drop=True)
            t0 = time.time()
            th_av = _fit_theta(full, FINAL_METHOD, l1_list, alpha)
            if len(th_av):
                rows.append(comp_row(f"{FINAL_METHOD} – chỉ ngày đủ hàng", _lift_table(th_av, levels), time.time() - t0,
                                     f"độ nhạy (availability ≥ {cfg['availability_full']})", 0, None, full))
            _log(log, "sensitivity_full_availability", len(data), len(full), "chạy lại final trên ngày đủ hàng")
        comparison = pd.DataFrame(rows)
    else:
        frozen = cfg.get("frozen") or {}
        do_tin_cay = frozen.get("do_tin_cay", "chưa đánh giá")
        _log(log, "frozen_params", 0, 0, f"độ tin cậy (placebo lần evaluate gần nhất): {do_tin_cay}")
    promo_effect["do_tin_cay"] = do_tin_cay

    # 5) promo_type_effect: mọi loại KM đủ dữ liệu trong 1 mô hình, đặc tả FE của final (notebook mục 8.2)
    counts = (data[TYPE_COLS] > 0).sum()
    used = [c for c in TYPE_COLS if counts[c] >= cfg["min_promo_rows"]]
    skipped = [c for c in TYPE_COLS if c not in used]
    if not used:
        raise ValueError("Không loại KM nào đủ min_promo_rows dòng có giảm giá")
    est, y, rhs = _spec(FINAL_METHOD)
    fit_t = est(f"{y} ~ {' + '.join(used)} + {rhs}", data=data, vcov={"CRV1": "unique_id"})
    coef, ci = fit_t.coef(), fit_t.confint(alpha=alpha)
    dropped = [c for c in used if c not in coef.index or not np.isfinite(coef[c])]
    used = [c for c in used if c not in dropped]
    pte = pd.DataFrame({"promo_type": used, "theta": coef[used].values,
                        "ci_low": ci.loc[used].iloc[:, 0].values, "ci_high": ci.loc[used].iloc[:, 1].values,
                        "so_dong_co_KM": [int(counts[c]) for c in used],
                        "muc_giam_tb_khi_co_KM": [float(data.loc[data[c] > 0, c].mean()) for c in used],
                        "method": FINAL_METHOD})
    for lvl in levels:
        pte[f"lift_{int(round(lvl * 100))}_%"] = lift_pct(pte["theta"], lvl)
    _log(log, "promo_type_effect", len(data), len(pte),
         f"ước lượng {used}; bỏ (< {cfg['min_promo_rows']} dòng có KM): {skipped}; bị loại do cộng tuyến: {dropped}")

    out = {"promo_effect": promo_effect, "promo_type_effect": pte,
           "run_log": pd.DataFrame(log, columns=["step", "rows_in", "rows_out", "note"])}
    if evaluate:
        out["bt5_method_comparison"] = comparison
        out["_params"] = {"final_method": FINAL_METHOD, "do_tin_cay": do_tin_cay, "placebo_pass_rate": pass_rate}
    validate_outputs(out, cfg)
    return out


# ---------------------------------------------------------------- kiểm tra hợp đồng
def validate_outputs(outputs: dict[str, pd.DataFrame], config: dict) -> None:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    evaluate = cfg.get("mode", "evaluate") == "evaluate"
    for name in (OUTPUTS if evaluate else FAST_OUTPUTS):
        if name not in outputs or not isinstance(outputs[name], pd.DataFrame):
            raise ValueError(f"Thiếu output '{name}'")
    pe = outputs["promo_effect"]
    miss = [c for c in PE_COLS if c not in pe.columns]
    if miss:
        raise ValueError(f"promo_effect thiếu cột {miss}")
    if pe.empty or pe[PE_COLS].isna().any().any():
        raise ValueError("promo_effect rỗng hoặc có NaN ở cột hợp đồng")
    if pe.duplicated(["L1", "discount"]).any():
        raise ValueError("promo_effect trùng khoá (L1, discount)")
    lv = sorted(cfg["discount_levels"])
    if not set(np.round(pe["discount"], 6)) <= set(np.round(lv, 6)):
        raise ValueError("promo_effect: discount ngoài {0.1, 0.2, 0.3}")
    if (pe.groupby("L1")["discount"].nunique() != len(lv)).any():
        raise ValueError("promo_effect: mỗi L1 phải đủ 3 mức giảm")
    if not np.allclose(pe["lift_%"], lift_pct(pe["theta"], pe["discount"]), rtol=1e-6, atol=1e-6):
        raise ValueError("promo_effect: lift_% ≠ (e^(θ·discount) − 1)·100")
    tol = 1e-9
    if ((pe["ci_low_%"] > pe["lift_%"] + tol) | (pe["lift_%"] > pe["ci_high_%"] + tol)).any():
        raise ValueError("promo_effect: lift_% nằm ngoài [ci_low_%, ci_high_%]")
    pt = outputs["promo_type_effect"]
    if not {"promo_type", "theta"} <= set(pt.columns) or pt.empty:
        raise ValueError("promo_type_effect thiếu cột promo_type/theta hoặc rỗng")
    if pt[["promo_type", "theta"]].isna().any().any() or pt["promo_type"].duplicated().any():
        raise ValueError("promo_type_effect có NaN hoặc trùng promo_type")
    if not set(pt["promo_type"]) <= set(TYPE_COLS):
        raise ValueError("promo_type_effect: promo_type ngoài type_0…type_6_discount")
    mc = outputs.get("bt5_method_comparison")
    if mc is not None and (not {"method", "final"} <= set(mc.columns) or mc["method"].duplicated().any()
                           or int(mc["final"].sum()) != 1):
        raise ValueError("bt5_method_comparison: cần cột method (không trùng) và đúng 1 dòng final = 1")
    rl = outputs["run_log"]
    if list(rl.columns) != ["step", "rows_in", "rows_out", "note"]:
        raise ValueError("run_log sai cột")
