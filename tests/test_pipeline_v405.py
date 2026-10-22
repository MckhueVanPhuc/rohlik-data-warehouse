"""V4-05: STG → Core → Mart → DQ, nhập liệu CSV + soft undo, CLI pipeline.run – mọi ghi đều ở thư mục tạm.

Dữ liệu tổng hợp nhỏ (2 kho, 4 SKU, 01/02 → 15/03/2024, lịch tới 29/03/2024) theo đúng header 7 file nguồn.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
import hashlib
from pathlib import Path

import pytest
import yaml

from src.config.settings import load_settings
from src.config.source_registry import DEFAULT_CONTRACT, DEFAULT_REGISTRY, load_contract, load_registry
from src.db.duckdb import connection, initialize_database, transaction
from src.entry.validate import table_by_name, template_csv, validate_upload
from src.entry.write import EntryError, undo_batch, write_upload
from src.ingestion.landing import ingest_landing
from src.transform.refresh import refresh

WHS = ["Prague_1", "Brno_1"]
D0, AS_OF, FC_END = date(2024, 2, 1), date(2024, 3, 15), date(2024, 3, 29)
SKUS = {1: ("Prague_1", "Bakery"), 2: ("Prague_1", "Meat and fish"), 3: ("Brno_1", "Bakery"), 4: ("Brno_1", "Fruit and vegetable")}


def _days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def _rows(source_id: str, header: list[str]) -> list[list]:
    out = []
    if source_id == "orders":
        for w in WHS:
            for d in _days(D0, AS_OF):
                rec = dict(warehouse=w, date=d.isoformat(), orders=1000 + d.day, holiday_name="", holiday=0, shutdown=0,
                           mini_shutdown=0, shops_closed=0, winter_school_holidays=0, school_holidays=0, blackout=0,
                           mov_change=0.0, frankfurt_shutdown=0, precipitation="" if d.day == 3 else 0.5, snow=0.0,
                           user_activity_1=2000.0, user_activity_2=3000.0, id=f"{w}_{d.isoformat()}")
                out.append([rec[c] for c in header])
    elif source_id == "sales":
        for uid, (w, _) in SKUS.items():
            for d in _days(D0, AS_OF):
                rec = dict(unique_id=uid, date=d.isoformat(), warehouse=w, total_orders=900.0 + d.day,
                           sales=10.0 + uid, sell_price_main=20.0 + uid, availability=0.8 if d.day == 10 else 1.0,
                           type_0_discount=-0.1 if (uid == 1 and d.day == 5) else 0.0, type_1_discount=0.0,
                           type_2_discount=0.2 if d.day == 7 else 0.0, type_3_discount=0.0, type_4_discount=0.0,
                           type_5_discount=0.0, type_6_discount=0.0)
                out.append([rec[c] for c in header])
    elif source_id == "inventory":
        for uid, (w, l1) in SKUS.items():
            rec = dict(unique_id=uid, product_unique_id=100 + uid, name=f"Item_{uid}", L1_category_name_en=l1,
                       L2_category_name_en=f"{l1}_L2", L3_category_name_en=f"{l1}_L3", L4_category_name_en=f"{l1}_L4",
                       warehouse=w)
            out.append([rec[c] for c in header])
    elif source_id == "calendar":
        for w in WHS:
            for d in _days(D0, FC_END):
                rec = dict(date=d.isoformat(), holiday_name="", holiday=0, shops_closed=0, winter_school_holidays=0,
                           school_holidays=0, warehouse=w)
                out.append([rec[c] for c in header])
    elif source_id == "weights":
        out = [[uid, 1.0 + uid / 10] for uid in SKUS]
    elif source_id == "cost_params":
        out = [["Bakery", 0.6, 2, 0.05], ["Fruit and vegetable", 0.65, 4, 0.05], ["Meat and fish", 0.7, 3, 0.1]]
    elif source_id == "workforce_params":
        out = [[w, 9.0, 28, 150, 8, 0.55, 1.5, 0.25, 3.0, 0.1, 25] for w in WHS]
    return out


@pytest.fixture
def project(tmp_path: Path):
    registry = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "contract.yaml").write_text(DEFAULT_CONTRACT.read_text(encoding="utf-8"), encoding="utf-8")
    for source_id, source in registry["active_sources"].items():
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = _rows(source_id, source["header"])
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(source["header"])
            writer.writerows(rows)
        source["row_count"] = len(rows)
        source["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    (tmp_path / "config" / "sources.yaml").write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    settings_data = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "settings.yaml").read_text(encoding="utf-8"))
    settings_data["sku_scope"] = {"warehouses": WHS, "train_from": D0.isoformat()}
    settings_path = tmp_path / "config" / "settings.yaml"
    settings_path.write_text(yaml.safe_dump(settings_data, sort_keys=False), encoding="utf-8")
    settings = load_settings(settings_path)
    database = tmp_path / "warehouse" / "test.duckdb"
    initialize_database(database)
    assert ingest_landing(database, execute=True, root=tmp_path, entered_by="developer:test")["status"] == "COMPLETED"
    contract = load_contract("config/contract.yaml", registry=load_registry("config/sources.yaml", root=tmp_path), root=tmp_path)
    return tmp_path, database, settings, contract


def _value(database: Path, sql: str):
    with connection(database) as conn:
        return conn.execute(sql).fetchone()[0]


def test_refresh_builds_stg_core_marts_and_passes_dq(project):
    _, database, settings, contract = project
    report = refresh(database, settings, contract)
    assert report.status == "SUCCESS", report.failed
    assert len(report.stg_rows) == 14
    assert report.core_rows["core.fct_sku_day"] == 4 * 44
    assert report.core_rows["core.fct_warehouse_day"] == 2 * 58          # 01/02 → 29/03/2024 (lịch tới cuối kỳ dự báo)
    assert report.mart_rows["mart.sales_orders_day"] == 2 * 44
    ids = {c["check_id"]: c for c in report.checks}
    assert ids["C-SD-06"]["status"] == "WARN" and ids["C-SD-06"]["observed"] == 2   # 2 ô giảm giá âm (ngày 5/2, 5/3 – D04)
    assert ids["C-WD-06"]["observed"] == 4                                          # precipitation NULL ngày 3 (2 tháng × 2 kho)
    assert _value(database, "SELECT max_discount FROM core.fct_sku_day WHERE unique_id = 1 AND date = '2024-02-05'") == 0
    assert _value(database, "SELECT count(*) FROM core.fct_warehouse_day WHERE is_forecast_period") == 2 * 14


def test_upload_refresh_undo_refresh_restores_previous_value(project):
    _, database, settings, contract = project
    assert refresh(database, settings, contract).status == "SUCCESS"
    table = table_by_name(contract, "orders_daily")
    raw = b"warehouse,date,orders\nPrague_1,2024-03-10,99999\n"
    with connection(database) as conn:
        report = validate_upload(raw, "fix.csv", table, settings, conn)
    assert report.ok and report.n_keys_replaced == 1
    info = write_upload(database, contract, table, report, operator="Nam", reason="sửa số đơn thử")
    assert refresh(database, settings, contract).status == "SUCCESS"
    sql = "SELECT orders FROM core.fct_warehouse_day WHERE warehouse = 'Prague_1' AND date = '2024-03-10'"
    assert _value(database, sql) == 99999
    undo_batch(database, info["batch_id"], operator="Nam", reason="hoàn tác thử nghiệm")
    assert refresh(database, settings, contract).status == "SUCCESS"
    assert _value(database, sql) == 1010
    with connection(database) as conn:
        log = conn.execute("SELECT action, operator_name, reason FROM meta.entry_log ORDER BY entered_at").fetchall()
        entered = conn.execute(f"SELECT DISTINCT _entered_by FROM src_sales.orders_daily WHERE _batch_id = '{info['batch_id']}'").fetchall()
    assert [r[0] for r in log] == ["UPLOAD", "UNDO"] and log[0][1] == "Nam"
    assert entered == [("user:admin_local",)]
    # nạp lại nguồn vẫn NO_OP dù Landing có thêm dòng upload (dòng upload không thuộc lô nguồn)
    root = project[0]
    assert ingest_landing(database, execute=True, root=root)["status"] == "NO_OP"


def test_upload_validation_blocks_bad_files_and_duplicates(project):
    _, database, settings, contract = project
    assert refresh(database, settings, contract).status == "SUCCESS"
    table = table_by_name(contract, "orders_daily")
    assert template_csv(table) == b"warehouse,date,orders\n"
    with connection(database) as conn:
        assert "U-02" in validate_upload(b"warehouse,date\nPrague_1,2024-03-10\n", "a.csv", table, settings, conn).blocking[0]
        assert "U-01" in validate_upload(b"x", "a.txt", table, settings, conn).blocking[0]
        bad = validate_upload(b"warehouse,date,orders\nPrague_9,2024-03-10,-1\nBrno_1,10/03/2024,x\n"
                              b"Brno_1,2024-03-11,1\nBrno_1,2024-03-11,2\n", "b.csv", table, settings, conn)
    codes = {e["ma"] for e in bad.row_errors}
    assert {"U-03", "U-05", "U-06", "U-07"} <= codes and not bad.ok
    with pytest.raises(EntryError):
        write_upload(database, contract, table, bad, operator="Nam", reason="không được ghi")
    with connection(database) as conn:
        ok = validate_upload(b"warehouse,date,orders\nBrno_1,2024-03-18,5\n", "c.csv", table, settings, conn)
    assert ok.ok and ok.n_after_as_of == 1
    with pytest.raises(EntryError, match="Người nhập"):
        write_upload(database, contract, table, ok, operator=" ", reason="thiếu người nhập")
    write_upload(database, contract, table, ok, operator="Nam", reason="nhập ngày tương lai")
    with connection(database) as conn:
        again = validate_upload(b"warehouse,date,orders\nBrno_1,2024-03-18,5\n", "c.csv", table, settings, conn)
        source_batch = conn.execute("SELECT batch_id FROM meta.source_batches WHERE source_id = 'orders'").fetchone()[0]
    assert again.blocking and "U-08" in again.blocking[0]
    with pytest.raises(EntryError, match="UPLOAD"):
        undo_batch(database, source_batch, operator="Nam", reason="không undo lô nguồn")


def test_dq_error_rolls_back_and_keeps_previous_marts(project):
    _, database, settings, contract = project
    assert refresh(database, settings, contract).status == "SUCCESS"
    before = _value(database, "SELECT sum(orders) FROM mart.sales_orders_day")
    with transaction(database) as conn:                      # mô phỏng dữ liệu lỗi lọt vào Landing
        conn.execute("""INSERT INTO meta.source_batches VALUES ('b_bad', 'upload:orders_daily', 'upload:bad.csv', 'x', 4,
                        'COMPLETED', '2030-01-01T00:00:00+00:00', '2030-01-01T00:00:01+00:00', 1, NULL)""")
        conn.execute("""INSERT INTO src_sales.orders_daily VALUES ('Prague_1', '2024-03-01', -50,
                        'b_bad', 'upload:bad.csv', TIMESTAMP '2030-01-01 00:00:00', 'user:admin_local')""")
    report = refresh(database, settings, contract)
    assert report.status == "FAILED"
    assert {"B17", "C-WD-03"} <= {c["check_id"] for c in report.failed}
    assert _value(database, "SELECT sum(orders) FROM mart.sales_orders_day") == before
    assert _value(database, f"SELECT count(*) FROM meta.quality_report WHERE run_id = '{report.run_id}' AND status = 'FAIL'") >= 2


def test_cli_status_runs_without_database(tmp_path, capsys):
    from pipeline.run import main
    code = main(["status", "--database", str(tmp_path / "warehouse" / "none.duckdb")])
    assert code == 1
    assert "pipeline.run init" in capsys.readouterr().out
