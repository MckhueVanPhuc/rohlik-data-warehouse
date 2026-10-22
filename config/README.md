# Cấu hình V4-05

- `settings.yaml`: đường dẫn DuckDB, mốc thời gian, seed, giới hạn upload, writer lock và thư mục run.
- `sources.yaml`: registry production với đúng 7 nguồn active; Finance/workforce được gắn nhãn giả định khi áp dụng; `historical_sources.orders_calendar` chỉ là metadata lịch sử.
- `contract.yaml`: 14 landing contract trong 9 schema `src_*`, gồm khóa, schema và update policy.
- `model_params/BT1.json` … `BT8.json`: tham số có version cho model runner.

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only --json
.\.venv\Scripts\python.exe -m src.validate_source_registry --json
```

Validation không tự ingest hoặc tạo database. Xem [data contract](../docs/data_contract.md), [pipeline](../docs/pipeline.md) và [models](../docs/models.md).

V4-05 không dùng registry Task08A hay runtime SQLite.
