"""BT1 – Dự báo số đơn hàng 14 ngày theo kho (P50/P90) – bản tinh gọn để tích hợp pipeline.

Hai chế độ (D06 đã duyệt 22/10/2026):
  * mode="models"  : chỉ mô hình final LightGBM quantile, học 1 lần trên dữ liệu ≤ as_of, dự báo 14 ngày;
                     hệ số hiệu chỉnh P90 lấy từ tham số đã chốt (frozen["p90_hs"]) – không backtest.
  * mode="evaluate": như notebook final – 3 mốc backtest (LightGBM + SeasonalNaive), hiệu chỉnh P90 bỏ-từng-mốc,
                     bảng so sánh; trả thêm "_params" để lưu làm tham số chốt cho lần chạy "models" sau.

Nguồn phương án: /home/claude/final8/bt1/BT1_final.ipynb (bản nghiên cứu đầy đủ = original_notebook.ipynb).
Giữ nguyên: lưới ngày + cờ đóng cửa (ô 3.4), hệ số thang đo order_index (5.1), tiền xử lý/đặc trưng (5.2–5.3, 6.7),
3 mốc backtest chính (6.1), LightGBM quantile (6.10, 9.1), SeasonalNaive baseline (6.9),
hiệu chỉnh P90 theo kho/chung chọn bằng bỏ-từng-mốc (9.2), cảnh báo tuần trước Thứ Sáu Tốt lành (9.3, 9.4, 10.1).
Bỏ (chỉ có ở notebook): EDA, biểu đồ, AutoETS/AutoARIMA/Prophet (ứng viên thua), mốc phụ Phục Sinh 2023,
bootstrap + quy tắc chọn mô hình, feature importance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BT_ID = "BT1"
REQUIRED_INPUTS = ["orders_daily", "calendar", "sku_sales_daily"]
OPTIONAL_INPUTS: list[str] = []
UPSTREAM: dict[str, tuple[str, str]] = {}
OUTPUTS = ["fc_orders", "bt1_backtest", "bt1_model_comparison", "run_log"]
FAST_OUTPUTS = ["fc_orders", "run_log"]
FAST_INPUTS = REQUIRED_INPUTS

DEFAULT_CONFIG: dict[str, Any] = {
    "as_of": "2024-03-15",            # ngày cuối có số thật (data_until)
    "train_start": "2020-12-05",      # ngày đầu dữ liệu được dùng
    "horizon": 14,                    # 16/03 → 29/03/2024
    "seed": 42,
    "n_jobs": 1,                      # luồng CPU cho LightGBM/statsforecast; >1 có thể đổi kết quả ở mức sai số
    "warehouses": None,               # None = tất cả kho có trong orders_daily
    "fx_eur": {"CZK": 0.04, "HUF": 0.0025, "EUR": 1.0},   # ASSUMED – BT1 không dùng tiền, giữ để thống nhất config
    "required_inputs": REQUIRED_INPUTS,
    "series": ["orders", "order_index"],
    "final_model": "LightGBM",
    "baseline_model": "SeasonalNaive",
    "n_folds": 3,                     # 3 mốc 14 ngày nối liền, mốc cuối kết thúc as_of
    "munich_skip_days": 42,           # bỏ 6 tuần đầu Munich_1 khỏi huấn luyện
    "oi_spread_threshold": 0.5,       # ngưỡng (max-min)/trung vị gắn cờ order_index nghi vấn
    "scale_breaks": ["2023-02-01", "2023-08-01"],   # mốc đổi thang đo order_index (giai đoạn A/B/C)
    "lags": [14, 21, 28, 35, 364],
    "p90_shrink_weight": 0.5,         # hệ số theo kho co về hệ số chung
    "lgb_params": {"n_estimators": 400, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 20,
                   "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "verbose": -1,
                   "deterministic": True, "force_row_wise": True},
    "czech_warehouses": ["Brno_1", "Prague_1", "Prague_2", "Prague_3"],
    "mode": "evaluate",               # "models" (nhanh, tham số chốt) | "evaluate" (backtest + cập nhật tham số)
    "frozen": None,                   # tham số chốt: {"p90_hs": {series: {warehouse: hệ số}}, "p90_method": {...}}
}

INPUT_COLUMNS = {
    "orders_daily": ["warehouse", "date", "orders"],
    "calendar": ["warehouse", "date", "holiday_name", "holiday", "shops_closed", "winter_school_holidays", "school_holidays"],
    "sku_sales_daily": ["unique_id", "date", "warehouse", "total_orders"],
}
INPUT_KEYS = {"orders_daily": ["warehouse", "date"], "calendar": ["warehouse", "date"], "sku_sales_daily": ["unique_id", "date"]}

FC_COLS = ["warehouse", "date", "series", "p50", "p90", "model", "data_until", "closed", "p90_tho", "risk_flag", "note", "p90_scenario"]
CO_LICH = ["holiday", "school_holidays", "winter_school_holidays", "truoc_le", "sau_le", "truoc_dong", "sau_dong"]


# ----------------------------------------------------------------------------------------------------------
# Tiện ích
# ----------------------------------------------------------------------------------------------------------
def _merge_config(config: dict | None) -> dict:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    cfg["lgb_params"] = {**DEFAULT_CONFIG["lgb_params"], **(config or {}).get("lgb_params", {})}
    return cfg


def _log(log: list, step: str, rows_in: Any, rows_out: Any, note: str) -> None:
    log.append({"step": step, "rows_in": rows_in, "rows_out": rows_out, "note": note})


def _prepare_inputs(inputs: dict, cfg: dict, log: list) -> dict[str, pd.DataFrame]:
    """Kiểm tra input bắt buộc/cột/kiểu ngày, chống trùng khoá, cắt mốc chống rò rỉ. Không sửa DataFrame gốc."""
    missing = sorted(set(cfg["required_inputs"]) - set(inputs))
    if missing:
        raise ValueError(f"{BT_ID}: thiếu input bắt buộc {missing}")
    t0, as_of = pd.Timestamp(cfg["train_start"]), pd.Timestamp(cfg["as_of"])
    fc_end = as_of + pd.Timedelta(days=int(cfg["horizon"]))
    out = {}
    for name in REQUIRED_INPUTS:
        df = inputs[name]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{BT_ID}: input '{name}' phải là pandas.DataFrame")
        miss_c = [c for c in INPUT_COLUMNS[name] if c not in df.columns]
        if miss_c:
            raise ValueError(f"{BT_ID}: input '{name}' thiếu cột {miss_c}")
        df = df[INPUT_COLUMNS[name]].copy()
        try:
            df["date"] = pd.to_datetime(df["date"])
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"{BT_ID}: cột date của '{name}' không chuyển được sang ngày: {e}") from e
        hi = fc_end if name == "calendar" else as_of     # lịch là thông tin biết trước → giữ tới as_of + horizon
        n0 = len(df)
        df = df[(df["date"] >= t0) & (df["date"] <= hi)].copy()
        _log(log, f"cut_{name}", n0, len(df), f"giữ {t0.date()} ≤ date ≤ {hi.date()}")
        if df.duplicated(INPUT_KEYS[name]).any():
            raise ValueError(f"{BT_ID}: input '{name}' trùng khoá {INPUT_KEYS[name]}")
        out[name] = df
    o = out["orders_daily"]
    n_null = int(o["orders"].isna().sum())
    out["orders_daily"] = o[o["orders"].notna()].copy()
    _log(log, "null_orders", len(o), len(out["orders_daily"]),
         f"{n_null} dòng orders NULL bị bỏ (coi như không có dòng → ngày kho đóng cửa theo quy tắc notebook)")
    s = out["sku_sales_daily"]
    _log(log, "null_total_orders", len(s), int(s["total_orders"].notna().sum()),
         "total_orders NULL bỏ qua khi lấy trung vị kho-ngày (không điền 0)")
    whs = cfg.get("warehouses")
    all_wh = sorted(out["orders_daily"]["warehouse"].unique())
    if whs is not None:
        lack = sorted(set(whs) - set(all_wh))
        if lack:
            raise ValueError(f"{BT_ID}: orders_daily không có kho {lack}")
        for k in out:
            out[k] = out[k][out[k]["warehouse"].isin(whs)].copy()
    whs = sorted(out["orders_daily"]["warehouse"].unique())
    if not whs:
        raise ValueError(f"{BT_ID}: orders_daily rỗng sau khi cắt mốc")
    lack_s = sorted(set(whs) - set(out["sku_sales_daily"]["warehouse"]))
    if lack_s:
        raise ValueError(f"{BT_ID}: sku_sales_daily thiếu kho {lack_s} (cần cho chuỗi order_index)")
    if (out["orders_daily"].groupby("warehouse")["date"].max() < as_of - pd.Timedelta(days=7)).any():
        raise ValueError(f"{BT_ID}: có kho không có orders trong 7 ngày trước as_of – kiểm tra snapshot dữ liệu")
    _log(log, "warehouses", len(all_wh), len(whs), ",".join(whs))
    return out


# ----------------------------------------------------------------------------------------------------------
# Bảng gộp kho-ngày (notebook ô 2.8, 2.9, 2.11, 3.4)
# ----------------------------------------------------------------------------------------------------------
def _build_gold(d: dict, cfg: dict, log: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    as_of = pd.Timestamp(cfg["as_of"]); fc_end = as_of + pd.Timedelta(days=int(cfg["horizon"]))
    orders_daily = d["orders_daily"][["warehouse", "date", "orders"]]
    nhom = d["sku_sales_daily"].groupby(["warehouse", "date"])["total_orders"]
    oi = nhom.agg(order_index="median", n_sku="size", oi_min="min", oi_max="max").reset_index()
    oi["order_index"] = oi["order_index"].astype(float)
    order_index_daily = oi[["warehouse", "date", "order_index"]].copy()
    lich = d["calendar"].copy()
    ngay_mo = orders_daily.groupby("warehouse")["date"].min().rename("ngay_mo").reset_index()
    luoi = pd.concat([pd.DataFrame({"warehouse": w, "date": pd.date_range(d0, fc_end)}) for w, d0 in ngay_mo.values],
                     ignore_index=True)
    gold = luoi.merge(lich, on=["warehouse", "date"], how="left")
    cot_lich = ["holiday", "shops_closed", "school_holidays", "winter_school_holidays"]
    n_thieu = int(gold["holiday"].isna().sum())
    gold[cot_lich] = gold[cot_lich].fillna(0)
    _log(log, "calendar_gaps", len(gold), n_thieu, "kho-ngày thiếu trong calendar → cờ lịch = 0 (như notebook ô 3.4)")
    from dateutil.easter import easter
    gf = [pd.Timestamp(easter(y)) - pd.Timedelta(days=2) for y in range(pd.Timestamp(cfg["train_start"]).year, fc_end.year + 1)]
    bo_sung = gold["date"].isin(gf) & (gold["holiday"] == 1) & gold["holiday_name"].isna()
    gold.loc[bo_sung, "holiday_name"] = "Good Friday"
    gold["split"] = np.where(gold["date"] <= as_of, "history", "forecast")
    gold = gold.merge(orders_daily, on=["warehouse", "date"], how="left")
    oi["oi_spread"] = (oi["oi_max"] - oi["oi_min"]) / oi["order_index"]
    gold = gold.merge(oi[["warehouse", "date", "order_index", "n_sku", "oi_max", "oi_spread"]], on=["warehouse", "date"], how="left")
    qk = gold[gold["split"] == "history"].assign(dong=lambda x: x["orders"].isna().astype(int), thu=lambda x: x["date"].dt.dayofweek)
    dong_cn = qk[qk["thu"] == 6].groupby("warehouse").tail(26).groupby("warehouse")["dong"].mean() > 0.9
    dong_sc = qk[qk["shops_closed"] == 1].groupby("warehouse")["dong"].mean() > 0.5
    dong_du_kien = (((gold["date"].dt.dayofweek == 6) & gold["warehouse"].map(dong_cn).fillna(False).astype(bool)) |
                    ((gold["shops_closed"] == 1) & gold["warehouse"].map(dong_sc).fillna(False).astype(bool))).values
    gold["closed"] = np.where(gold["split"] == "history", gold["orders"].isna(), dong_du_kien).astype(int)
    gold["oi_nghi_van"] = (gold["oi_spread"] > cfg["oi_spread_threshold"]).astype(int)
    gold = gold.sort_values(["warehouse", "date"]).reset_index(drop=True)
    _log(log, "gold_warehouse_day", len(orders_daily), len(gold),
         f"lưới ngày liên tục từ ngày mở kho → {fc_end.date()}; ngày đóng dự kiến kỳ dự báo = "
         f"{int(gold.loc[gold['split'] == 'forecast', 'closed'].sum())}; kho nghỉ CN: {dong_cn[dong_cn].index.tolist()}")
    _log(log, "order_index", len(d["sku_sales_daily"]), len(order_index_daily),
         f"order_index = trung vị total_orders theo kho-ngày; ngày nghi vấn (spread>{cfg['oi_spread_threshold']}) = "
         f"{int(gold['oi_nghi_van'].sum())}")
    return gold, ngay_mo


def _dien_tu_tuan_truoc(y: pd.Series, can_dien: pd.Series) -> pd.Series:
    goc = y.where(~can_dien)
    tuan_truoc = pd.concat([goc.shift(k) for k in (7, 14, 21, 28)], axis=1).median(axis=1)
    return y.where(~can_dien, tuan_truoc)


def _scale_factors(gold: pd.DataFrame, moc: list) -> pd.DataFrame:
    """Ô 5.1 – hệ số đưa order_index về thang đo giai đoạn C (theo kho)."""
    ls = gold[gold["split"] == "history"]
    nen = ls[(ls["closed"] == 0) & (ls["oi_nghi_van"] == 0)].copy()
    nen["giai_doan"] = np.select([nen["date"] < moc[0], nen["date"] < moc[1]], ["A", "B"], "C")
    nen["ty_le"] = nen["order_index"] / nen["orders"]
    t = nen.pivot_table(index="warehouse", columns="giai_doan", values="ty_le", aggfunc="median")
    for g in "ABC":
        if g not in t.columns:
            t[g] = np.nan
    return pd.DataFrame({"A": t["C"] / t["A"], "B": t["C"] / t["B"], "C": 1.0})


def _tao_panel(gold: pd.DataFrame, ten: str, he_so: pd.DataFrame, kho_ma: dict, moc: list, mo_mu, cfg: dict) -> pd.DataFrame:
    """Ô 5.3 – bảng đã tiền xử lý + đặc trưng cho một chuỗi."""
    cac_kho = []
    cols = ["warehouse", "date", "split", "closed", "orders", "order_index", "oi_nghi_van",
            "holiday", "shops_closed", "school_holidays", "winter_school_holidays"]
    for w, x in gold[cols].groupby("warehouse"):
        x = x.sort_values("date").reset_index(drop=True)
        gd = np.select([x["date"] < moc[0], x["date"] < moc[1]], ["A", "B"], "C")
        x["he_so"] = [he_so.loc[w, g] for g in gd]
        if ten == "orders":
            y_goc = x["orders"].astype(float)
            co_nv = pd.Series(0, index=x.index)
        else:
            y_goc = (x["order_index"] * x["he_so"]).astype(float)
            co_nv = x["oi_nghi_van"].fillna(0).astype(int)
        y_sach = _dien_tu_tuan_truoc(y_goc, co_nv == 1)
        ls_mask = x["split"] == "history"
        y_dien = _dien_tu_tuan_truoc(y_sach, y_sach.isna() & ls_mask)
        y_dien = y_dien.where(~ls_mask, y_dien.ffill())
        f = pd.DataFrame({"warehouse": w, "date": x["date"], "split": x["split"], "closed": x["closed"],
                          "y_goc": y_goc, "y_sach": y_sach, "y_dien": y_dien, "co_nghi_van": co_nv, "he_so": x["he_so"]})
        dd = x["date"]
        f["kho"] = kho_ma[w]
        f["thu"] = dd.dt.dayofweek
        f["thang"] = dd.dt.month
        f["tuan_nam"] = dd.dt.isocalendar().week.astype(int).values
        f["ngay_thang"] = dd.dt.day
        for c in ["holiday", "shops_closed", "school_holidays", "winter_school_holidays"]:
            f[c] = x[c].fillna(0).astype(int)
        f["truoc_le"] = ((x["holiday"].shift(-1) == 1) & (x["holiday"] == 0)).astype(int)
        f["sau_le"] = ((x["holiday"].shift(1) == 1) & (x["holiday"] == 0)).astype(int)
        f["truoc_dong"] = ((x["closed"].shift(-1) == 1) & (x["closed"] == 0)).astype(int)
        f["sau_dong"] = ((x["closed"].shift(1) == 1) & (x["closed"] == 0)).astype(int)
        for k in cfg["lags"]:
            f[f"lag{k}"] = y_sach.shift(k)
        f["nen_28"] = y_sach.shift(14).rolling(28, min_periods=14).mean()
        f["y_ty_le"] = y_sach / f["nen_28"]
        skip = (w == "Munich_1") & (mo_mu is not None)
        f["bo_huan_luyen"] = ((dd < mo_mu + pd.Timedelta(days=int(cfg["munich_skip_days"]))) if skip
                              else pd.Series(False, index=x.index)).astype(int)
        for k in cfg["lags"]:                                  # ô 6.7 – độ trễ dạng tỷ lệ so với mức nền
            f[f"lag{k}_r"] = f[f"lag{k}"] / f["nen_28"]
        cac_kho.append(f)
    return pd.concat(cac_kho, ignore_index=True)


def _features(ten: str, cfg: dict) -> list[str]:
    base = ["kho", "thu", "thang", "tuan_nam", "ngay_thang", "shops_closed"] + (["closed"] if ten == "order_index" else [])
    return base + CO_LICH + [f"lag{k}_r" for k in cfg["lags"]]


# ----------------------------------------------------------------------------------------------------------
# Mô hình (ô 6.9, 6.10, 9.1)
# ----------------------------------------------------------------------------------------------------------
def _split(p: pd.DataFrame, goc, test_dau, test_cuoi):
    train = p[(p["date"] <= goc) & (p["split"] == "history") & (p["bo_huan_luyen"] == 0)]
    test = p[(p["date"] >= test_dau) & (p["date"] <= test_cuoi)]
    return train, test


def _seasonal_naive(train: pd.DataFrame, h: int, cfg: dict) -> pd.DataFrame:
    from statsforecast import StatsForecast
    from statsforecast.models import SeasonalNaive
    df = train[["warehouse", "date", "y_dien"]].rename(columns={"warehouse": "unique_id", "date": "ds", "y_dien": "y"})
    if df["y"].isna().any():
        raise ValueError(f"{BT_ID}: y_dien còn ô trống – không chạy được SeasonalNaive")
    sf = StatsForecast(models=[SeasonalNaive(season_length=7)], freq="D", n_jobs=int(cfg["n_jobs"]))
    fc = sf.forecast(df=df, h=h, level=[80])
    if "unique_id" not in fc.columns:
        fc = fc.reset_index()
    return pd.DataFrame({"warehouse": fc["unique_id"], "date": pd.to_datetime(fc["ds"]),
                         "p50": fc["SeasonalNaive"], "p90": fc["SeasonalNaive-hi-80"]})


def _lightgbm(ten: str, train: pd.DataFrame, test: pd.DataFrame, cfg: dict, p90_col: str = "p90") -> pd.DataFrame:
    import lightgbm as lgb
    dt = _features(ten, cfg)
    params = {**cfg["lgb_params"], "random_state": int(cfg["seed"]), "n_jobs": int(cfg["n_jobs"])}
    tr = train[train["y_ty_le"].notna() & train["nen_28"].notna()]
    te = test[test["nen_28"].notna()]
    if ten == "orders":
        tr = tr[tr["closed"] == 0]
        te = te[te["closed"] == 0]
    kq = te[["warehouse", "date", "closed"]].copy()
    for col, alpha in [("p50", 0.5), (p90_col, 0.9)]:
        mdl = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **params)
        mdl.fit(tr[dt], tr["y_ty_le"], categorical_feature=["kho"])
        kq[col] = mdl.predict(te[dt]) * te["nen_28"].values
    kq[p90_col] = np.maximum(kq[p90_col], kq["p50"])
    return kq


def _mape(y, f) -> float:
    y = np.asarray(y, dtype=float); f = np.asarray(f, dtype=float)
    ok = np.isfinite(y) & np.isfinite(f) & (y > 0)
    return float(np.mean(np.abs(y[ok] - f[ok]) / y[ok]) * 100) if ok.any() else np.nan


def _mask(df: pd.DataFrame, ten: str) -> pd.Series:
    if ten == "orders":
        return (df["closed"] == 0) & df["y_goc"].notna()
    return df["y_goc"].notna() & (df["co_nghi_van"] == 0)


# ----------------------------------------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------------------------------------
def run_model(*, inputs: dict[str, pd.DataFrame], config: dict[str, Any], artifact_dir: Path | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    log: list = []
    _log(log, "config", None, None, f"as_of={cfg['as_of']}, horizon={cfg['horizon']}, seed={cfg['seed']}, n_jobs={cfg['n_jobs']}, "
                                    f"final={cfg['final_model']}, baseline={cfg['baseline_model']}, artifact_dir không dùng (refit mỗi run)")
    np.random.seed(int(cfg["seed"]))
    d = _prepare_inputs(inputs, cfg, log)
    H = int(cfg["horizon"]); as_of = pd.Timestamp(cfg["as_of"])
    fc_start, fc_end = as_of + pd.Timedelta(days=1), as_of + pd.Timedelta(days=H)
    moc = [pd.Timestamp(x) for x in cfg["scale_breaks"]]
    final_m, base_m = cfg["final_model"], cfg["baseline_model"]
    if final_m != "LightGBM" or base_m != "SeasonalNaive":
        raise ValueError(f"{BT_ID}: model.py chỉ hỗ trợ final=LightGBM, baseline=SeasonalNaive (ứng viên khác ở original_notebook)")
    series = list(cfg["series"])

    gold, ngay_mo = _build_gold(d, cfg, log)
    he_so = _scale_factors(gold, moc)
    kho_ma = {w: i for i, w in enumerate(sorted(gold["warehouse"].unique()))}
    mo_mu = ngay_mo.set_index("warehouse")["ngay_mo"].get("Munich_1")
    pn = {ten: _tao_panel(gold, ten, he_so, kho_ma, moc, mo_mu, cfg) for ten in series}
    for ten in series:
        con = int(pn[ten].loc[pn[ten]["split"] == "history", "y_dien"].isna().sum())
        if con:
            raise ValueError(f"{BT_ID}: {ten} còn {con} ô trống trong y_dien sau khi điền")
    _log(log, "panel", len(gold), sum(len(v) for v in pn.values()),
         f"hệ số thang đo order_index (A,B→C) tính trên toàn lịch sử như notebook; Munich_1 bỏ {cfg['munich_skip_days']} ngày đầu")

    evaluate = cfg["mode"] == "evaluate"
    if evaluate:
        # ---- 3 mốc backtest chính (ô 6.1) ----
        folds = []
        for i in range(int(cfg["n_folds"])):
            cuoi = as_of - pd.Timedelta(days=H * i); dau = cuoi - pd.Timedelta(days=H - 1)
            folds.append({"fold": f"F{int(cfg['n_folds']) - i}", "goc": dau - pd.Timedelta(days=1), "test_dau": dau, "test_cuoi": cuoi})
        folds = sorted(folds, key=lambda x: x["test_dau"])
        fold_names = [f["fold"] for f in folds]

        kq_list = []
        for ten in series:
            for fd in folds:
                train, test = _split(pn[ten], fd["goc"], fd["test_dau"], fd["test_cuoi"])
                for m in [base_m, final_m]:
                    kq = _seasonal_naive(train, H, cfg) if m == base_m else _lightgbm(ten, train, test, cfg)
                    out = test[["warehouse", "date", "closed", "y_goc", "co_nghi_van"]].merge(
                        kq[["warehouse", "date", "p50", "p90"]], on=["warehouse", "date"], how="left")
                    if ten == "orders":
                        out.loc[out["closed"] == 1, ["p50", "p90"]] = np.nan
                    out.insert(0, "model", m); out.insert(0, "fold", fd["fold"]); out.insert(0, "series", ten)
                    kq_list.append(out)
        kq_bt = pd.concat(kq_list, ignore_index=True)
        _log(log, "backtest", None, len(kq_bt), f"{len(folds)} mốc × {len(series)} chuỗi × 2 mô hình; cutoff = "
                                              + ", ".join(str(f['goc'].date()) for f in folds))

        # ---- đánh giá (ô 7.1, 7.2, 7.4) ----
        kq_bt["tinh"] = False
        for ten in series:
            m_ = kq_bt["series"] == ten
            kq_bt.loc[m_, "tinh"] = (_mask(kq_bt[m_], ten) & kq_bt.loc[m_, "p50"].notna()).values
        kq_bt["ape"] = (kq_bt["p50"] - kq_bt["y_goc"]).abs() / kq_bt["y_goc"] * 100
        ev = kq_bt[kq_bt["tinh"]]
        bang_mape = {ten: ev[ev["series"] == ten].groupby(["model", "fold"])["ape"].mean().unstack().reindex(columns=fold_names)
                     for ten in series}

    # ---- dự báo tương lai bằng LightGBM (ô 9.1) ----
    du_bao = {}
    for ten in series:
        train, test = _split(pn[ten], as_of, fc_start, fc_end)
        if test["nen_28"].isna().any():
            raise ValueError(f"{BT_ID}: {ten} có dòng dự báo thiếu mức nền nen_28")
        du_bao[ten] = _lightgbm(ten, train, test, cfg, p90_col="p90_tho")

    # ---- hiệu chỉnh P90 (ô 9.2) ----
    HS, HS_LOFO, CACH = {}, {}, {}
    if evaluate:
        wgt = float(cfg["p90_shrink_weight"])

        def he_so_p90(c):
            q = float(np.percentile(c["e"], 90))
            return q, {w: wgt * q + (1 - wgt) * float(np.percentile(g["e"], 90)) for w, g in c.groupby("warehouse")}

        for ten in series:
            c = kq_bt[(kq_bt["series"] == ten) & (kq_bt["model"] == final_m)].copy()
            c = c[_mask(c, ten) & c["p50"].notna()]
            c["e"] = (c["y_goc"] - c["p50"]) / c["p50"]
            q_all, qk_all = he_so_p90(c)
            lofo, cov = {}, []
            for f_ in fold_names:
                q_f, qk_f = he_so_p90(c[c["fold"] != f_])
                lofo[f_] = (q_f, qk_f)
                x = c[c["fold"] == f_]
                cov.append(((x["e"] <= q_f).mean() * 100, (x["e"] <= x["warehouse"].map(qk_f)).mean() * 100))
            lech = {"chung": abs(np.mean([a for a, _ in cov]) - 90), "theo kho": abs(np.mean([b for _, b in cov]) - 90)}
            CACH[ten] = min(lech, key=lech.get)
            pick = (lambda q, qk: {w: q for w in qk}) if CACH[ten] == "chung" else (lambda q, qk: qk)
            HS[ten] = (q_all, pick(q_all, qk_all))
            HS_LOFO[ten] = {f_: pick(*v) for f_, v in lofo.items()}
            _log(log, f"p90_calibration_{ten}", len(c), None,
                 f"cách={CACH[ten]}; Q_chung={q_all:.4f}; hệ số kho={ {w: round(v, 4) for w, v in HS[ten][1].items()} }; "
                 f"lệch phủ bỏ-mốc: chung {lech['chung']:.1f}, theo kho {lech['theo kho']:.1f} điểm")
    else:
        frozen = cfg.get("frozen") or {}
        hs_frozen = frozen.get("p90_hs") or {}
        for ten in series:
            if ten not in hs_frozen:
                raise ValueError(f"{BT_ID}: chế độ models cần tham số chốt p90_hs['{ten}'] – chạy `evaluate` trước "
                                 "hoặc kiểm tra config/model_params/BT1.json")
            hs_w = {w: float(v) for w, v in hs_frozen[ten].items()}
            lack = sorted(set(du_bao[ten]["warehouse"]) - set(hs_w))
            if lack:
                raise ValueError(f"{BT_ID}: tham số chốt p90_hs['{ten}'] thiếu kho {lack}")
            HS[ten] = (float(np.mean(list(hs_w.values()))), hs_w)
            CACH[ten] = (frozen.get("p90_method") or {}).get(ten, "frozen")
        _log(log, "p90_calibration_frozen", None, None, f"dùng hệ số P90 đã chốt (nguồn: {frozen.get('_source', 'params')})")
    for ten in series:
        f = du_bao[ten]
        f["p90"] = np.maximum(f["p50"] * (1 + f["warehouse"].map(HS[ten][1])), f["p50"])

    # ---- cảnh báo tuần trước Thứ Sáu Tốt lành (ô 9.3, 9.4, 10.1) ----
    o = du_bao["orders"]
    canh_bao = {}
    ngay_gf = gold.loc[(gold["split"] == "forecast") & (gold["holiday_name"] == "Good Friday"), "date"].min()
    nam_ls = (fc_end.year - 2, fc_end.year - 1)
    if pd.notna(ngay_gf):
        def nen_4_tuan(x):
            x = x.sort_values("date")
            thuong = x["orders"].where((x["closed"] == 0) & (x["holiday"] == 0) & (x["shops_closed"] == 0))
            cac = pd.concat([thuong.shift(k) for k in (7, 14, 21, 28)], axis=1)
            return pd.Series(cac.median(axis=1).where(cac.notna().sum(axis=1) >= 3).values, index=x["date"].values)
        nen = {w: nen_4_tuan(x) for w, x in gold.groupby("warehouse")}
        thu5 = ngay_gf - pd.Timedelta(days=1)
        for w in sorted(gold["warehouse"].unique()):
            dong = o[(o["warehouse"] == w) & (o["date"] == thu5)]
            if dong.empty:
                continue
            gfh = gold[(gold["warehouse"] == w) & (gold["holiday_name"] == "Good Friday") & (gold["split"] == "history")]
            ls_ty_le = {}
            for nd in gfh["date"] - pd.Timedelta(days=1):
                thuc = gold.loc[(gold["warehouse"] == w) & (gold["date"] == nd), "orders"]
                if len(thuc) and pd.notna(thuc.iloc[0]) and pd.notna(nen[w].get(nd, np.nan)):
                    ls_ty_le[nd.year] = thuc.iloc[0] / nen[w][nd]
            ty_le_db = dong["p50"].iloc[0] / nen[w].get(thu5, np.nan)
            ls_v = [v for k, v in ls_ty_le.items() if k in nam_ls]
            if ls_v and ty_le_db < min(ls_v) - 0.05:
                canh_bao[(w, thu5)] = (
                    f"Thứ Năm trước Thứ Sáu Tốt lành: năm {nam_ls[0]}–{nam_ls[1]} số đơn cao hơn mức nền {min(ls_v) - 1:.0%} đến "
                    f"{max(ls_v) - 1:.0%}, mô hình chỉ dự báo cao hơn {ty_le_db - 1:.0%}; dự báo có thể thấp hơn thực tế, nên dùng p90_scenario",
                    min(ls_v))
        # ô 9.4: Thứ Tư trước Thứ Sáu Tốt lành theo nhóm kho (mức nền ±4 tuần, chỉ lịch sử)
        lich_su = gold[gold["split"] == "history"]
        tl_list = []
        for _, x in lich_su.groupby("warehouse"):
            x = x.sort_values("date")
            thuong = x["orders"].where((x["closed"] == 0) & (x["holiday"] == 0) & (x["shops_closed"] == 0))
            cac = pd.concat([thuong.shift(k) for k in (-28, -21, -14, -7, 7, 14, 21, 28)], axis=1)
            nen_c = cac.median(axis=1).where(cac.notna().sum(axis=1) >= 3)
            tl_list.append(x[["warehouse", "date", "closed"]].assign(ty_le=x["orders"] / nen_c))
        tl = pd.concat(tl_list, ignore_index=True)
        tl = tl[(tl["closed"] == 0) & tl["ty_le"].notna()]
        gf_ngay = lich_su[lich_su["holiday_name"] == "Good Friday"][["warehouse", "date"]].drop_duplicates()
        m_ = tl.merge(gf_ngay.assign(date=gf_ngay["date"] - pd.Timedelta(days=2)), on=["warehouse", "date"])
        czech = set(cfg["czech_warehouses"])
        m_["nhom"] = np.where(m_["warehouse"].isin(czech), "kho Czech", "kho khác")
        t_ = m_.groupby(["nhom", m_["date"].dt.year])["ty_le"].median().unstack()
        for nhom, r_ in t_.iterrows():
            r_min = min(r_.get(nam_ls[0], np.nan), r_.get(nam_ls[1], np.nan))
            if pd.notna(r_min) and r_min > 1.05:
                for w in sorted(gold["warehouse"].unique()):
                    if (w in czech) == (nhom == "kho Czech"):
                        canh_bao[(w, ngay_gf - pd.Timedelta(days=2))] = (
                            f"Thứ Tư trước Thứ Sáu Tốt lành: năm {nam_ls[0]}–{nam_ls[1]} nhóm {nhom} cao hơn mức nền "
                            f"{r_min - 1:.0%} trở lên; mô hình không có cờ riêng cho ngày này, nên dùng p90_scenario", r_min)
    _log(log, "easter_risk_flags", None, len(canh_bao), f"Thứ Sáu Tốt lành trong kỳ dự báo: {ngay_gf.date() if pd.notna(ngay_gf) else 'không có'}")

    # ---- fc_orders (ô 10.1) ----
    khung = gold[gold["split"] == "forecast"][["warehouse", "date", "closed"]]
    phan = []
    for ten in series:
        x = khung.merge(du_bao[ten][["warehouse", "date", "p50", "p90", "p90_tho"]], on=["warehouse", "date"], how="left").assign(series=ten)
        if ten == "orders":
            x.loc[x["closed"] == 1, ["p50", "p90", "p90_tho"]] = 0.0
        phan.append(x)
    dai = pd.concat(phan, ignore_index=True)
    dai["model"] = final_m
    dai["data_until"] = as_of
    dai["risk_flag"] = 0; dai["note"] = ""; dai["p90_scenario"] = dai["p90"]
    dai.loc[(dai["series"] == "orders") & (dai["closed"] == 1), "note"] = "Kho dự kiến đóng cửa (Chủ nhật/ngày lễ): không có đơn"
    for (w, ngay), (ghi_chu, r_hist) in canh_bao.items():
        mo = (dai["warehouse"] == w) & (dai["date"] == ngay) & ~((dai["series"] == "orders") & (dai["closed"] == 1))
        if not mo.any():
            continue
        p50_o = dai.loc[mo & (dai["series"] == "orders"), "p50"]
        nv = nen[w].get(ngay, np.nan)
        he_so_kb = max(1.0, r_hist * nv / p50_o.iloc[0]) if len(p50_o) and pd.notna(nv) else 1.0
        for ten in series:
            mm = mo & (dai["series"] == ten)
            dai.loc[mm, "risk_flag"] = 1
            dai.loc[mm, "note"] = ghi_chu
            dai.loc[mm, "p90_scenario"] = np.maximum(dai.loc[mm, "p90"], dai.loc[mm, "p50"] * he_so_kb * (1 + HS[ten][1][w]))
    dai[["p50", "p90", "p90_tho", "p90_scenario"]] = dai[["p50", "p90", "p90_tho", "p90_scenario"]].round(0)
    fc_orders = dai[FC_COLS].sort_values(["series", "warehouse", "date"]).reset_index(drop=True)

    if evaluate:
        # ---- bt1_backtest dạng rộng (ô 10.1 d) ----
        cut = {f["fold"]: f["goc"] for f in folds}
        bt = kq_bt.copy()
        bt["cutoff"] = bt["fold"].map(cut)
        m_lgb = bt["model"] == final_m
        bt["p90_raw"] = np.where(m_lgb, bt["p90"], np.nan)
        for (ten, f_), idx in bt[m_lgb].groupby(["series", "fold"]).groups.items():
            hs = bt.loc[idx, "warehouse"].map(HS_LOFO[ten][f_])
            bt.loc[idx, "p90"] = np.maximum(bt.loc[idx, "p50"] * (1 + hs), bt.loc[idx, "p50"])
        khoa = ["series", "warehouse", "date", "cutoff"]
        w_ = bt.set_index(khoa + ["model"])[["p50", "p90"]].unstack("model")
        w_.columns = [m if v == "p50" else f"{m}-p90" for v, m in w_.columns]
        w_ = w_.join(bt[m_lgb].set_index(khoa)["p90_raw"].rename(f"{final_m}-p90_raw")).reset_index()
        yy = bt.drop_duplicates(khoa)[khoa + ["y_goc", "closed", "co_nghi_van"]].rename(columns={"y_goc": "y"})
        w_ = w_.merge(yy, on=khoa, how="left")
        models = [base_m, final_m]
        cot_mh = models + [f"{m}-p90" for m in models] + [f"{final_m}-p90_raw"]
        dong_o = (w_["series"] == "orders") & (w_["closed"] == 1)
        w_.loc[dong_o, ["y"] + cot_mh] = 0.0
        bt1_backtest = w_[["warehouse", "date", "cutoff", "y"] + cot_mh + ["series", "closed", "co_nghi_van"]] \
            .sort_values(["series", "cutoff", "warehouse", "date"]).reset_index(drop=True)
        n_nan = int(bt1_backtest[["y"] + cot_mh].isna().sum().sum())
        _log(log, "bt1_backtest", len(bt), len(bt1_backtest), f"dạng rộng; ô trống ở cột y/mô hình = {n_nan} (ngày thiếu số thật hoặc mức nền)")

        # ---- bt1_model_comparison (ô 10.1 e) ----
        rows = []
        bt_t = bt[bt["tinh"]]
        for ten in series:
            base_mape = bang_mape[ten].loc[base_m].mean()
            for m in models:
                x = bt_t[(bt_t["series"] == ten) & (bt_t["model"] == m)]
                raw = ev[(ev["series"] == ten) & (ev["model"] == m)]
                mm = float(bang_mape[ten].loc[m].mean())
                rows.append({"series": ten, "model": m, "mape_mean": round(mm, 3), "MAPE_%": round(mm, 2),
                             "MAPE_by_fold": str([float(round(bang_mape[ten].loc[m, f_], 2)) for f_ in fold_names]),
                             **{f"mape_{f_}": round(float(bang_mape[ten].loc[m, f_]), 3) for f_ in fold_names},
                             "P90_coverage_%": round(float((x["y_goc"] <= x["p90"]).mean() * 100), 1),
                             "P90_coverage_raw_%": round(float((raw["y_goc"] <= raw["p90"]).mean() * 100), 1),
                             "improvement_vs_baseline_%": round(float((base_mape - mm) / base_mape * 100), 1),
                             "n_eval_days": int(len(x)), "p90_method": CACH[ten] if m == final_m else "statsforecast hi-80",
                             "role": "final" if m == final_m else "baseline", "selected": m == final_m})
        cmp_df = pd.DataFrame(rows)

    run_log = pd.DataFrame(log, columns=["step", "rows_in", "rows_out", "note"])
    run_log["rows_in"] = run_log["rows_in"].astype("Int64"); run_log["rows_out"] = run_log["rows_out"].astype("Int64")
    outputs = {"fc_orders": fc_orders, "run_log": run_log}
    if evaluate:
        outputs.update({"bt1_backtest": bt1_backtest, "bt1_model_comparison": cmp_df})
        outputs["_params"] = {"p90_hs": {ten: {w: round(float(v), 6) for w, v in HS[ten][1].items()} for ten in series},
                              "p90_method": dict(CACH)}
    validate_outputs(outputs, cfg)
    return outputs


def validate_outputs(outputs: dict[str, pd.DataFrame], config: dict) -> None:
    """Kiểm tra hợp đồng đầu ra; raise ValueError nếu sai."""
    cfg = _merge_config(config)
    need = OUTPUTS if cfg["mode"] == "evaluate" else FAST_OUTPUTS
    for name in need:
        if name not in outputs or not isinstance(outputs[name], pd.DataFrame):
            raise ValueError(f"{BT_ID}: thiếu output '{name}'")
    as_of = pd.Timestamp(cfg["as_of"]); H = int(cfg["horizon"])
    fc = outputs["fc_orders"]
    req = ["warehouse", "date", "series", "p50", "p90", "model", "data_until"]
    _req_cols(fc, req, "fc_orders")
    _no_dup(fc, ["series", "warehouse", "date"], "fc_orders")
    if fc[req].isna().any().any():
        raise ValueError(f"{BT_ID}: fc_orders có NaN ở cột hợp đồng")
    if (fc[["p50", "p90"]] < 0).any().any() or (fc["p90"] < fc["p50"]).any():
        raise ValueError(f"{BT_ID}: fc_orders có p50/p90 âm hoặc p90 < p50")
    dts = pd.to_datetime(fc["date"])
    if dts.min() != as_of + pd.Timedelta(days=1) or dts.max() != as_of + pd.Timedelta(days=H):
        raise ValueError(f"{BT_ID}: fc_orders sai khoảng ngày dự báo")
    if set(fc["series"]) != set(cfg["series"]):
        raise ValueError(f"{BT_ID}: fc_orders sai tập series")
    if (pd.to_datetime(fc["data_until"]) != as_of).any():
        raise ValueError(f"{BT_ID}: data_until phải = as_of")
    n_wh = fc["warehouse"].nunique()
    if cfg.get("warehouses") is not None and set(fc["warehouse"]) != set(cfg["warehouses"]):
        raise ValueError(f"{BT_ID}: fc_orders thiếu kho")
    if len(fc) != n_wh * H * len(cfg["series"]):
        raise ValueError(f"{BT_ID}: fc_orders phải có kho × {H} ngày × {len(cfg['series'])} chuỗi dòng")
    if cfg["mode"] != "evaluate":
        _req_cols(outputs["run_log"], ["step", "rows_in", "rows_out", "note"], "run_log")
        return
    bt = outputs["bt1_backtest"]
    mcols = [cfg["baseline_model"], cfg["final_model"]]
    req_bt = ["warehouse", "date", "cutoff", "y", "series"] + mcols + [f"{m}-p90" for m in mcols]
    _req_cols(bt, req_bt, "bt1_backtest")
    _no_dup(bt, ["warehouse", "date", "cutoff", "series"], "bt1_backtest")
    if pd.to_datetime(bt["date"]).max() > as_of or (pd.to_datetime(bt["cutoff"]) >= pd.to_datetime(bt["date"])).any():
        raise ValueError(f"{BT_ID}: bt1_backtest có ngày sau as_of hoặc cutoff không trước ngày kiểm tra")
    num = bt[["y"] + mcols + [f"{m}-p90" for m in mcols]]
    if (num < -1e-9).any().any():
        raise ValueError(f"{BT_ID}: bt1_backtest có giá trị âm")
    lg, lg9 = bt[cfg["final_model"]], bt[f"{cfg['final_model']}-p90"]
    if (lg9 + 1e-9 < lg).any():
        raise ValueError(f"{BT_ID}: bt1_backtest LightGBM-p90 < LightGBM")
    if set(bt["warehouse"]) != set(fc["warehouse"]) or pd.to_datetime(bt["cutoff"]).nunique() != int(cfg["n_folds"]):
        raise ValueError(f"{BT_ID}: bt1_backtest thiếu kho hoặc sai số mốc")
    cmp_df = outputs["bt1_model_comparison"]
    _req_cols(cmp_df, ["series", "model", "mape_mean", "MAPE_%", "P90_coverage_%", "selected"], "bt1_model_comparison")
    _no_dup(cmp_df, ["series", "model"], "bt1_model_comparison")
    if cmp_df[["mape_mean", "P90_coverage_%"]].isna().any().any():
        raise ValueError(f"{BT_ID}: bt1_model_comparison có NaN")
    _req_cols(outputs["run_log"], ["step", "rows_in", "rows_out", "note"], "run_log")


def _req_cols(df: pd.DataFrame, cols: list, name: str) -> None:
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f"{BT_ID}: output '{name}' thiếu cột {miss}")


def _no_dup(df: pd.DataFrame, keys: list, name: str) -> None:
    if df.duplicated(keys).any():
        raise ValueError(f"{BT_ID}: output '{name}' trùng khoá {keys}")
