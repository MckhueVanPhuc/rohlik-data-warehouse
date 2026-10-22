"""Nhập liệu CSV (M9): sinh template từ contract và kiểm tra file upload (U-01 … U-10).

Nguyên tắc đã duyệt (22/10/2026): cả file hoặc không ghi gì; tối đa 50.000 dòng/lần; 14/14 bảng được upload (D13);
full-row: mỗi dòng có đủ mọi cột của bảng (tên cột canonical của Landing); không có 4 cột kỹ thuật.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
import io
from typing import Any

import duckdb
import pandas as pd

from src.config.settings import Settings
from src.config.source_registry import BusinessContract, ContractCatalog

TECH_COLUMNS = ("_batch_id", "_source", "_loaded_at", "_entered_by")
MAX_TEXT = 200


@dataclass
class UploadReport:
    table: str
    file_name: str
    sha256: str
    n_rows: int = 0
    blocking: list[str] = field(default_factory=list)            # U-01, U-02, U-08 → chặn cả file
    row_errors: list[dict[str, Any]] = field(default_factory=list)  # U-03 … U-07 → lỗi dòng
    n_keys_replaced: int = 0                                     # U-09
    n_unchanged: int = 0                                         # U-09
    n_after_as_of: int = 0                                       # U-10
    clean: pd.DataFrame | None = None                            # dữ liệu đã ép kiểu, sẵn sàng ghi

    @property
    def ok(self) -> bool:
        return not self.blocking and not self.row_errors and self.clean is not None and self.n_rows > 0

    def errors_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.row_errors, columns=["dong", "cot", "ma", "loi"])


def table_by_name(contract: ContractCatalog, name: str) -> BusinessContract:
    """Nhận 'orders_daily' hoặc 'src_sales.orders_daily'."""
    for qualified, table in contract.tables.items():
        if name in (qualified, table.table):
            return table
    raise KeyError(f"Không có bảng {name} trong config/contract.yaml")


def template_columns(table: BusinessContract) -> list[str]:
    return list(table.columns)


def template_csv(table: BusinessContract, conn: duckdb.DuckDBPyConnection | None = None, example_rows: int = 0) -> bytes:
    """File mẫu UTF-8; nếu có kết nối kho và example_rows > 0 thì kèm vài dòng thật từ STG làm ví dụ."""
    cols = template_columns(table)
    if conn is not None and example_rows > 0:
        try:
            df = conn.execute(
                f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} FROM stg."{table.table}" '
                f'ORDER BY {", ".join(chr(34) + k + chr(34) for k in table.business_keys)} DESC LIMIT {int(example_rows)}'
            ).df()
            return df.to_csv(index=False).encode("utf-8")
        except duckdb.Error:
            pass
    return (",".join(cols) + "\n").encode("utf-8")


def column_guide(table: BusinessContract) -> pd.DataFrame:
    rows = []
    for name, col in table.columns.items():
        chk = table.checks.get(name)
        dom = ""
        if chk is not None:
            dom = " ".join(x for x in [f"≥ {chk.min:g}" if chk.min is not None else "",
                                       f"≤ {chk.max:g}" if chk.max is not None else ""] if x)
        rows.append({"cot": name, "kieu": col.type, "khoa": name in table.business_keys,
                     "bat_buoc": not col.nullable, "mien_gia_tri": dom})
    return pd.DataFrame(rows)


def _err(report: UploadReport, row: int, col: str, code: str, msg: str) -> None:
    if len(report.row_errors) < 5000:
        report.row_errors.append({"dong": row, "cot": col, "ma": code, "loi": msg})


def _parse(series: pd.Series, kind: str) -> tuple[pd.Series, pd.Series]:
    """Trả (giá trị đã ép kiểu, mặt nạ lỗi kiểu). Ô rỗng = NULL (không phải lỗi kiểu)."""
    s = series.astype("string").str.strip()
    empty = s.isna() | (s == "")
    if kind == "VARCHAR":
        return s.where(~empty, None), pd.Series(False, index=s.index)
    if kind == "DATE":
        ok_fmt = s.str.fullmatch(r"\d{4}-\d{2}-\d{2}").fillna(False)
        val = pd.to_datetime(s.where(ok_fmt), format="%Y-%m-%d", errors="coerce")
        bad = ~empty & val.isna()
        return val.dt.date.where(~val.isna(), None), bad
    num = pd.to_numeric(s.where(~empty), errors="coerce")
    bad = ~empty & num.isna()
    if kind == "BIGINT":
        frac = num.notna() & (num % 1 != 0)
        bad = bad | frac
        return num.where(~bad).astype("Int64"), bad
    return num.astype("Float64"), bad


def validate_upload(
    raw: bytes,
    file_name: str,
    table: BusinessContract,
    settings: Settings,
    conn: duckdb.DuckDBPyConnection | None,
) -> UploadReport:
    """Đọc file trong bộ nhớ (chưa ghi kho) và chạy U-01 … U-10."""
    sha = hashlib.sha256(raw).hexdigest()
    rep = UploadReport(table=f"{table.schema_name}.{table.table}", file_name=file_name, sha256=sha)
    # ---- U-01: file ----
    if not file_name.lower().endswith(".csv"):
        rep.blocking.append("U-01: file phải có đuôi .csv")
        return rep
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        rep.blocking.append("U-01: file không phải UTF-8 – lưu lại bằng 'CSV UTF-8 (Comma delimited)'")
        return rep
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, sep=",")
    except Exception as exc:  # noqa: BLE001
        rep.blocking.append(f"U-01: không đọc được CSV (dấu phẩy, UTF-8): {exc}")
        return rep
    rep.n_rows = len(df)
    if rep.n_rows == 0:
        rep.blocking.append("U-01: file không có dòng dữ liệu nào")
        return rep
    if rep.n_rows > settings.upload_max_rows:
        rep.blocking.append(f"U-01: {rep.n_rows:,} dòng > giới hạn {settings.upload_max_rows:,} dòng/lần – hãy chia nhỏ file")
        return rep
    # ---- U-02: tiêu đề ----
    cols = [c.strip() for c in df.columns]
    df.columns = cols
    expected = template_columns(table)
    dup = sorted({c for c in cols if cols.count(c) > 1})
    missing = [c for c in expected if c not in cols]
    extra = [c for c in cols if c not in expected]
    if dup or missing or extra:
        parts = []
        if missing: parts.append(f"thiếu cột {missing}")
        if extra: parts.append(f"thừa cột {extra}")
        if dup: parts.append(f"trùng tên cột {dup}")
        rep.blocking.append("U-02: tiêu đề sai – " + "; ".join(parts) + " (tải lại template, không đổi dòng tiêu đề)")
        return rep
    # ---- U-08: chống upload lặp (SHA-256 trùng lô COMPLETED) ----
    if conn is not None:
        try:
            hit = conn.execute(
                """SELECT b.batch_id FROM meta.source_batches b JOIN meta.v_batch_current c USING (batch_id)
                   WHERE b.source_id LIKE 'upload:%' AND b.source_fingerprint = ? AND c.status = 'COMPLETED'""",
                [sha]).fetchone()
        except duckdb.Error:
            hit = None
        if hit:
            rep.blocking.append(f"U-08: file này đã được nhập ở lô {hit[0]} – muốn nhập lại thì undo lô cũ trước")
            return rep
    line = pd.Series(range(2, rep.n_rows + 2), index=df.index)   # số dòng trong file (dòng 1 = tiêu đề)
    clean = pd.DataFrame(index=df.index)
    bad_row = pd.Series(False, index=df.index)
    # ---- U-03 kiểu, U-04 bắt buộc, U-05 miền ----
    for name, col in table.columns.items():
        val, bad = _parse(df[name], col.type)
        for i in df.index[bad]:
            _err(rep, int(line[i]), name, "U-03", f"'{df.at[i, name]}' không phải {col.type}"
                 + (" (ngày dạng YYYY-MM-DD)" if col.type == "DATE" else ""))
        bad_row |= bad
        null = val.isna() & ~bad
        if not col.nullable or name in table.business_keys:
            for i in df.index[null]:
                _err(rep, int(line[i]), name, "U-04", "cột bắt buộc đang trống")
            bad_row |= null
        chk = table.checks.get(name)
        if chk is not None and col.type in ("DOUBLE", "BIGINT"):
            v = val.astype("Float64")
            out = pd.Series(False, index=df.index)
            if chk.min is not None: out |= (v < chk.min).fillna(False)
            if chk.max is not None: out |= (v > chk.max).fillna(False)
            for i in df.index[out]:
                _err(rep, int(line[i]), name, "U-05", f"{df.at[i, name]} ngoài miền "
                     f"[{chk.min if chk.min is not None else '-∞'}, {chk.max if chk.max is not None else '+∞'}]")
            bad_row |= out
        if col.type == "VARCHAR":
            long = val.fillna("").str.len() > (100 if name == "holiday_name" else MAX_TEXT)
            for i in df.index[long]:
                _err(rep, int(line[i]), name, "U-05", "chuỗi quá dài")
            bad_row |= long
        clean[name] = val
    if "date" in clean.columns:
        early = pd.to_datetime(clean["date"]).lt(pd.Timestamp(settings.train_from)).fillna(False)
        for i in df.index[early]:
            _err(rep, int(line[i]), "date", "U-05", f"ngày trước {settings.train_from.isoformat()}")
        bad_row |= early
    if "warehouse" in clean.columns:
        wrong = clean["warehouse"].notna() & ~clean["warehouse"].isin(settings.warehouses)
        for i in df.index[wrong]:
            _err(rep, int(line[i]), "warehouse", "U-07", f"kho '{clean.at[i, 'warehouse']}' không thuộc 7 kho")
        bad_row |= wrong
    if table.table == "product_master":
        miss = clean["L1_category_name_en"].isna()
        for i in df.index[miss]:
            _err(rep, int(line[i]), "L1_category_name_en", "U-04", "ngành L1 bắt buộc")
        bad_row |= miss
    # ---- U-06: trùng khoá trong file ----
    keys = list(table.business_keys)
    dmask = clean.duplicated(keys, keep=False) & clean[keys].notna().all(axis=1)
    for i in df.index[dmask]:
        _err(rep, int(line[i]), "+".join(keys), "U-06", "trùng khoá với dòng khác trong file")
    bad_row |= dmask
    # ---- U-07: tham chiếu danh mục ----
    if conn is not None and "unique_id" in clean.columns and table.table != "product_master":
        try:
            pm = conn.execute('SELECT unique_id, warehouse FROM stg.product_master').df()
        except duckdb.Error:
            pm = None
        if pm is not None:
            known = clean["unique_id"].isin(pm["unique_id"])
            unk = clean["unique_id"].notna() & ~known
            for i in df.index[unk]:
                _err(rep, int(line[i]), "unique_id", "U-07", f"unique_id {clean.at[i, 'unique_id']} chưa có trong danh mục SKU")
            bad_row |= unk
            if "warehouse" in clean.columns:
                wh_of = dict(zip(pm["unique_id"], pm["warehouse"]))
                mis = known & clean["warehouse"].notna() & (clean["unique_id"].map(wh_of) != clean["warehouse"])
                for i in df.index[mis]:
                    _err(rep, int(line[i]), "warehouse", "U-07", "kho không khớp kho của SKU trong danh mục")
                bad_row |= mis
    rep.clean = clean
    # ---- U-09: so với bản đang có hiệu lực; U-10: ngày sau as_of ----
    if "date" in clean.columns:
        rep.n_after_as_of = int(pd.to_datetime(clean["date"]).gt(pd.Timestamp(settings.as_of)).sum())
    if conn is not None and not bad_row.any():
        try:
            conn.register("_upload_preview", clean.astype(object))
            on = " AND ".join(f'CAST(u."{k}" AS VARCHAR) = CAST(s."{k}" AS VARCHAR)' for k in keys)
            same = " AND ".join(f'CAST(u."{c}" AS VARCHAR) IS NOT DISTINCT FROM CAST(s."{c}" AS VARCHAR)'
                                for c in table.columns if c not in keys) or "TRUE"
            row = conn.execute(f'SELECT count(*), count(*) FILTER (WHERE {same}) FROM _upload_preview u '
                               f'JOIN stg."{table.table}" s ON {on}').fetchone()
            rep.n_keys_replaced, rep.n_unchanged = int(row[0]) - int(row[1]), int(row[1])
        except duckdb.Error:
            pass
        finally:
            try:
                conn.unregister("_upload_preview")
            except duckdb.Error:
                pass
    return rep


def validate_person_fields(operator: str, reason: str) -> list[str]:
    """Ô bắt buộc Người nhập (2–50 ký tự) và Lý do (5–200 ký tự) – D14."""
    errors = []
    if not (operator or "").strip() or not 2 <= len(operator.strip()) <= 50:
        errors.append("Người nhập: bắt buộc, 2–50 ký tự")
    if not (reason or "").strip() or not 5 <= len(reason.strip()) <= 200:
        errors.append("Lý do: bắt buộc, 5–200 ký tự")
    return errors


def today_iso() -> str:
    return date.today().isoformat()
