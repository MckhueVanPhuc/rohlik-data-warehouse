# Cấu hình V4 Local-first

- `settings.yaml`: DuckDB local, raw root, horizon, SKU scope và runner.
- `sources.yaml`: production registry v4 với đúng 7 active sources; Finance/HR là
  `ASSUMED`; `train_calendar.csv` chỉ historical-only.
- `contract.yaml`: đúng 14 business contracts tại 9 schema `src_*`; mọi update
  policy chưa được duyệt được ghi rõ `PENDING_CONFIRMATION`.
- `sources_task08a.yaml`: registry v1 chỉ cho bootstrap lịch sử Task08A.

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only --json
.\.venv\Scripts\python.exe -m src.validate_source_registry --json
```

Validation production không tạo bảng, không ingest và không mở database vật lý.
Chi tiết: [V4 Source Registry](../docs/source_registry.md). Tài liệu registry v1 được
giữ tại [legacy Task08A guide](../docs/source_registry_task08a.md).
