# Kiến trúc V4-05

Rohlik Decision Hub là hệ thống local-first: dữ liệu và credential được giữ trên máy vận hành, DuckDB là kho dữ liệu duy nhất và Streamlit là lớp phục vụ quyết định.

## Luồng dữ liệu

```text
7 CSV active
    -> source registry + checksum
    -> 14 landing tables (src_*)
    -> 14 STG tables
    -> 6 Core tables
    -> 5 base marts + 7 model-result marts/views
    -> reporting service read-only
    -> 10 Streamlit pages
```

`config/sources.yaml` khai báo nguồn; `config/contract.yaml` khai báo 14 landing contract. `pipeline/run.py` điều phối ingestion, transform, data quality và model. Refresh STG → Core → Mart → DQ chạy trong một writer transaction: lỗi mức `ERROR` làm rollback; báo cáo lỗi được ghi riêng sau rollback.

## Ranh giới trách nhiệm

- `src/ingestion/`: kiểm tra và nạp landing theo contract.
- `src/transform/`: xây STG, Core, Mart và điều phối refresh.
- `src/models/`: registry, DAG, runner, tham số và I/O của BT1–BT8.
- `src/db/`: kết nối DuckDB, lock writer, transaction, backup và metadata.
- `app/services/`: reporting read-only và các thao tác vận hành được kiểm soát.
- `app/pages/`: 10 trang được khai báo tập trung trong `app/navigation.py`.

Model execution không chạy từ giao diện. Upload, data entry, undo và refresh UI chỉ đi qua service được kiểm soát. Reporting mở warehouse ở chế độ read-only.

Pipeline model công bố các nhóm forecast, staffing/driver, lost-sales, SKU/replenishment, promo, markdown và growth qua bảy view `mart`. Writer duy nhất giữ lock khi ingest/refresh/import; reader dashboard không được nâng quyền ghi. Batch audit và transaction metadata tạo ranh giới giữa một thao tác được commit, rollback hoặc soft-undo.

## Trạng thái local

Các thành phần sau không thuộc Git: `.env`, `.venv`, `data/auth`, raw data được bàn giao, model artifacts và `data/warehouse/*.duckdb`. Không tự tạo lại warehouse chỉ để mở dashboard hoặc làm test. Runtime SQLite và bootstrap Task08A đã được loại khỏi V4-05.

## Cấu hình chính thức

- `config/settings.yaml`: thời gian, seed, giới hạn upload, lock và thư mục chạy.
- `config/sources.yaml`: 7 nguồn active cùng checksum và metadata lịch sử.
- `config/contract.yaml`: schema, khóa và update policy của landing.
- `config/model_params/BT1.json` … `BT8.json`: tham số model có version.

`historical_sources.orders_calendar` trong registry chỉ là metadata lịch sử, không phải nguồn active và không khôi phục Task08A.
