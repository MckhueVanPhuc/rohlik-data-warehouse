"""Bộ điều phối pipeline Rohlik Decision Hub (Local) – chạy bằng 1 lệnh.

    python -m pipeline.run init            # tạo kho + nạp 7 file nguồn vào 14 bảng Landing + refresh
    python -m pipeline.run ingest          # nạp lại nguồn (NO_OP nếu file nguồn không đổi)
    python -m pipeline.run refresh         # STG → Core → Mart → kiểm định chất lượng (DQ)
    python -m pipeline.run models          # 8 mô hình bản tinh gọn (tham số chốt) → pred.* → mart kết quả
    python -m pipeline.run evaluate        # backtest + so sánh như notebook, cập nhật tham số chốt
    python -m pipeline.run all             # init (nếu chưa có kho) / ingest → refresh → models
    python -m pipeline.run import-outputs --from "/Users/namnut/Downloads/Final Code"
    python -m pipeline.run status          # tóm tắt số dòng, DQ, lần chạy gần nhất

Tuỳ chọn chung: --database data/warehouse/rohlik.duckdb (mặc định theo config/settings.yaml), --bt BT1 BT3 …
Mã thoát: 0 = thành công; 1 = lỗi cấu hình/kho bận; 2 = DQ có ERROR (dữ liệu cũ giữ nguyên) hoặc mô hình lỗi.
Trước khi chạy lệnh ghi: tắt Streamlit (Ctrl+C) và đóng DBeaver.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import duckdb

from src.config.settings import SettingsError, load_settings
from src.config.source_registry import PROJECT_ROOT, RegistryError, load_contract, load_registry
from src.db.duckdb import DEFAULT_DATABASE, DuckDBSafetyError, WriterLockTimeout, connection, initialize_database
from src.db.duckdb_metadata import initialize_metadata
from src.db.pipeline_metadata import table_exists
from src.ingestion.landing import LandingIngestionError, ingest_landing
from src.transform.refresh import new_run_id, record_run, run_refresh_logged

DEFAULT_ENTERED_BY = "developer:Nam"


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _contract(root: Path):
    registry = load_registry("config/sources.yaml", root=root)
    return load_contract("config/contract.yaml", registry=registry, root=root)


def _print_refresh(report) -> None:
    print(f"\n== Refresh {report.run_id}: {report.status} ==")
    print("STG :", ", ".join(f"{k.split('.')[1]}={v:,}" for k, v in sorted(report.stg_rows.items())))
    if report.stg_rejects:
        print("Bản lỗi bị loại khỏi STG:", report.stg_rejects)
    print("Core:", ", ".join(f"{k.split('.')[1]}={v:,}" for k, v in report.core_rows.items()))
    print("Mart:", ", ".join(f"{k.split('.')[1]}={v:,}" for k, v in report.mart_rows.items()))
    n_pass = sum(c["status"] == "PASS" for c in report.checks)
    print(f"DQ  : {n_pass} PASS · {len(report.warned)} WARN · {len(report.failed)} FAIL (tổng {len(report.checks)} kiểm tra)")
    for c in report.warned:
        print(f"   WARN {c['check_id']:<9} {c['observed']:>12,.0f}  {c['description']}")
    for c in report.failed:
        print(f"   FAIL {c['check_id']:<9} {c['observed']:>12,.0f}  {c['description']}")


def cmd_ingest(args, settings, database: Path) -> int:
    if not database.is_file():
        print(f"Chưa có kho {database} – chạy `python -m pipeline.run init` trước")
        return 1
    t0 = time.time()
    report = ingest_landing(database, execute=True, root=args.project_root, entered_by=args.entered_by,
                            lock_timeout=args.lock_timeout)
    print(f"Landing: {report['status']} ({time.time() - t0:.0f}s) – 7 nguồn, 14 bảng")
    for w in report.get("warnings", []):
        print(f"   giữ nguyên bất thường nguồn: {w['source_id']}.{w['column']} = {w['count']} ô")
    return 0


def cmd_refresh(args, settings, database: Path) -> int:
    t0 = time.time()
    report = run_refresh_logged(database, settings, _contract(args.project_root), lock_timeout=args.lock_timeout)
    _print_refresh(report)
    print(f"Thời gian: {time.time() - t0:.0f}s")
    return 0 if report.status == "SUCCESS" else 2


def cmd_init(args, settings, database: Path) -> int:
    created = initialize_database(database)
    print(f"Kho DuckDB: {created['database_path']} (DuckDB {created['duckdb_version']}, tạo mới: {created['created']})")
    initialize_metadata(database, lock_timeout=args.lock_timeout)
    code = cmd_ingest(args, settings, database)
    return code or cmd_refresh(args, settings, database)


def _models(args, settings, database: Path, mode: str) -> int:
    from src.models.runner import last_refresh_ok, run_models
    ok, why = last_refresh_ok(database)
    if not ok and not args.force:
        print(f"Không chạy mô hình: {why}. Sửa lỗi DQ rồi refresh lại (hoặc thêm --force nếu chắc chắn).")
        return 2
    run_id = new_run_id(mode)
    record_run(database, run_id, mode, "RUNNING", settings, lock_timeout=args.lock_timeout)
    t0 = time.time()
    results = run_models(database, settings, mode=mode, bts=args.bt, run_id=run_id, lock_timeout=args.lock_timeout)
    bad = [r for r in results if r.status != "SUCCESS"]
    record_run(database, run_id, mode, "SUCCESS" if not bad else "FAILED", settings,
               details={r.bt_id: {"status": r.status, "sec": round(r.runtime_sec, 1), "outputs": r.outputs} for r in results},
               error="; ".join(f"{r.bt_id}: {r.message}" for r in bad) or None, lock_timeout=args.lock_timeout)
    print(f"\n== {mode} {run_id}: {len(results) - len(bad)}/{len(results)} BT thành công ({time.time() - t0:.0f}s) ==")
    for r in results:
        line = f"  {r.bt_id}: {r.status:<8} {r.runtime_sec:7.1f}s  " + ", ".join(f"{k}={v:,}" for k, v in r.outputs.items())
        print(line + (f"  ← {r.message}" if r.status != "SUCCESS" else ""))
        if r.params_file:
            print(f"        tham số mới: {r.params_file}")
    return 0 if not bad else 2


def cmd_models(args, settings, database: Path) -> int:
    return _models(args, settings, database, "models")


def cmd_evaluate(args, settings, database: Path) -> int:
    return _models(args, settings, database, "evaluate")


def cmd_all(args, settings, database: Path) -> int:
    code = cmd_init(args, settings, database) if not database.is_file() else (
        cmd_ingest(args, settings, database) or cmd_refresh(args, settings, database))
    return code or cmd_models(args, settings, database)


def cmd_import(args, settings, database: Path) -> int:
    from src.models.import_outputs import import_outputs
    if not args.source:
        print('Thiếu --from "<thư mục Final Code>"')
        return 1
    run_id = new_run_id("import")
    print(f"Nạp kết quả có sẵn từ {args.source}:")
    counts = import_outputs(database, settings, args.source, run_id=run_id, lock_timeout=args.lock_timeout)
    record_run(database, run_id, "import-outputs", "SUCCESS", settings, details=counts, lock_timeout=args.lock_timeout)
    print(f"Đã nạp {len(counts)} bảng; mart kết quả mô hình đã cập nhật.")
    return 0


def cmd_status(args, settings, database: Path) -> int:
    if not database.is_file():
        print(f"Chưa có kho {database} – chạy `python -m pipeline.run init`")
        return 1
    with connection(database) as conn:
        print(f"Kho: {database}  ·  as_of {settings.as_of}  ·  dự báo {settings.forecast_start} → {settings.forecast_end}")
        rows = conn.execute("""SELECT table_schema, table_name, table_type FROM information_schema.tables
                               WHERE table_schema IN ('stg','core','mart','pred','pred_eval') ORDER BY 1, 2""").fetchall()
        by_schema: dict[str, list[str]] = {}
        for schema, table, kind in rows:
            n = conn.execute(f'SELECT count(*) FROM {schema}."{table}"').fetchone()[0]
            by_schema.setdefault(schema, []).append(f"{table}{' (view)' if kind == 'VIEW' else ''}={n:,}")
        for schema in ("stg", "core", "mart", "pred", "pred_eval"):
            print(f"{schema:<9}: " + (", ".join(by_schema.get(schema, [])) or "chưa có"))
        if table_exists(conn, "meta", "pipeline_runs"):
            print("\nLần chạy gần nhất:")
            for r in conn.execute("""SELECT command, status, started_at, finished_at, error_message FROM meta.pipeline_runs
                                     ORDER BY started_at DESC LIMIT 8""").fetchall():
                print(f"  {r[2][:19]}  {r[0]:<14} {r[1]:<8} {('– ' + r[4]) if r[4] else ''}")
            q = conn.execute("""SELECT status, count(*) FROM meta.quality_report WHERE run_id = (
                                SELECT run_id FROM meta.pipeline_runs WHERE command IN ('refresh','init','all','ui-refresh')
                                ORDER BY started_at DESC LIMIT 1) GROUP BY 1""").fetchall()
            print("DQ lần refresh gần nhất:", dict(q) or "chưa có")
        if table_exists(conn, "meta", "model_runs"):
            print("\nMô hình (lần gần nhất mỗi BT):")
            for r in conn.execute("""SELECT bt_id, mode, status, runtime_sec, finished_at, error_message FROM (
                                     SELECT *, row_number() OVER (PARTITION BY bt_id ORDER BY started_at DESC) rn
                                     FROM meta.model_runs WHERE bt_id NOT LIKE '%:%') WHERE rn = 1 ORDER BY bt_id""").fetchall():
                print(f"  {r[0]}: {r[1]:<8} {r[2]:<8} {r[3] or 0:7.1f}s  {str(r[4])[:19]} {('– ' + r[5]) if r[5] else ''}")
        if table_exists(conn, "meta", "v_batch_current"):
            pend = conn.execute("""SELECT count(*) FROM meta.v_batch_current WHERE batch_type = 'UPLOAD'
                                   AND status_at > COALESCE((SELECT max(finished_at) FROM meta.pipeline_runs
                                   WHERE command IN ('refresh','init','all','ui-refresh') AND status = 'SUCCESS'), '')""").fetchone()[0]
            print(f"\nLô upload/undo chờ refresh: {pend}")
    return 0


COMMANDS = {"init": cmd_init, "ingest": cmd_ingest, "refresh": cmd_refresh, "models": cmd_models,
            "evaluate": cmd_evaluate, "all": cmd_all, "import-outputs": cmd_import, "status": cmd_status}


def main(argv: list[str] | None = None) -> int:
    _utf8()
    parser = argparse.ArgumentParser(prog="python -m pipeline.run", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=list(COMMANDS))
    parser.add_argument("--database", default=None, help="đường dẫn kho .duckdb (mặc định theo settings.yaml)")
    parser.add_argument("--bt", nargs="+", default=None, help="chỉ chạy các BT này, vd --bt BT1 BT2")
    parser.add_argument("--from", dest="source", default=None, help="thư mục Final Code (lệnh import-outputs)")
    parser.add_argument("--force", action="store_true", help="vẫn chạy mô hình khi refresh gần nhất chưa SUCCESS")
    parser.add_argument("--entered-by", default=DEFAULT_ENTERED_BY, help="ghi vào _entered_by của lô nạp nguồn")
    parser.add_argument("--lock-timeout", type=float, default=None, help="giây chờ khoá ghi (mặc định settings)")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        args.lock_timeout = args.lock_timeout or settings.lock_timeout_seconds
        database = Path(args.database).resolve() if args.database else DEFAULT_DATABASE
        if not database.is_absolute():
            database = (PROJECT_ROOT / database).resolve()
        return COMMANDS[args.command](args, settings, database)
    except WriterLockTimeout:
        print("Kho đang bận (Streamlit/DBeaver/lệnh khác đang ghi). Đóng chúng rồi chạy lại – chưa ghi gì.")
        return 1
    except (SettingsError, RegistryError, LandingIngestionError, DuckDBSafetyError, FileNotFoundError, ValueError,
            duckdb.Error) as exc:
        print(f"LỖI: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

