# V4 Source Registry & Business Contract Foundation

**Ngày xác minh:** 21/10/2026. **Trạng thái:** V4-01 IMPLEMENTED; pipeline/ingestion
PLANNED. Source of truth là
[`Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md`](../Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md),
đặc biệt I.1, I.2, I.4 và I.5 Bước 0–4.

Task này chỉ cung cấp registry, business contract và read-only preflight. Nó không
tạo bảng vật lý, không mở/ghi DuckDB chính thức, không ingest, không xây stg/core/mart,
model, orchestrator hoặc Streamlit entry.

## Kiến trúc cấu hình

- [`config/settings.yaml`](../config/settings.yaml): local DuckDB
  `data/warehouse/rohlik.duckdb`, raw root, horizon 14 ngày, SKU scope, local runner.
- [`config/sources.yaml`](../config/sources.yaml): registry v4, đúng 7 nguồn active,
  fingerprint/header/type/key/check evidence; Finance/HR là `ASSUMED`.
- [`config/contract.yaml`](../config/contract.yaml): đúng 14 business contracts tại
  9 schema `src_*`; mapping raw → canonical, grain/key/type/required/nullable,
  editable/checks/schema version/source type/update policy.
- [`src/config/source_registry.py`](../src/config/source_registry.py): safe YAML loader,
  Pydantic validation, exact-count/path/schema guards và read-only DuckDB preflight.

`orders/train_calendar.csv` chỉ nằm trong `historical_sources` với trạng thái
`HISTORICAL_ONLY`; nó không là active source, không thuộc contract V4 và không tạo
bảng thứ 15. File này hiện MISSING trên local nhưng không chặn V4 production preflight.

## Bảy nguồn active

| ID | Path | Loại | Rows | SHA-256 |
| --- | --- | --- | ---: | --- |
| orders | `data/raw/orders/train.csv` | KAGGLE_ORIGINAL | 7,340 | `1d0e15de...10be67` |
| sales | `data/raw/sales/sales_train.csv` | KAGGLE_ORIGINAL | 4,007,419 | `af45f951...3e0469` |
| inventory | `data/raw/sales/inventory.csv` | KAGGLE_ORIGINAL | 5,432 | `e1ada9e6...7e966b` |
| calendar | `data/raw/sales/calendar.csv` | KAGGLE_ORIGINAL | 23,016 | `2633d53e...36e84` |
| weights | `data/raw/sales/test_weights.csv` | KAGGLE_ORIGINAL | 5,390 | `a3b33db3...ccb783` |
| cost_params | `data/raw/assumptions/cost_params.csv` | ASSUMED | 3 | `22077d43...af8a24` |
| workforce_params | `data/raw/assumptions/workforce_params.csv` | ASSUMED | 7 | `2af353b2...d8d49b` |

Read-only preflight thực tế xác nhận cả 7 file: tồn tại, UTF-8 không BOM, header và
SHA-256 đúng, strict DuckDB type parse thành công, row count đúng, key không null và
không duplicate. Checks phát hiện 32 discount cells âm trong Sales
(`type_0_discount=27`, `type_4_discount=1`, `type_6_discount=4`). Đây là warning nguồn
đã biết; raw không bị clip/drop/sửa. `sales` và `total_orders` vẫn giữ 52 NULL mỗi cột.

## Mười bốn business contracts

| Schema | Tables |
| --- | --- |
| `src_sales` | `orders_daily`, `sku_sales_daily` |
| `src_marketing` | `prices`, `promotions`, `mov_changes` |
| `src_ops` | `availability`, `ops_events` |
| `src_category` | `product_master` |
| `src_planning` | `calendar` |
| `src_digital` | `user_activity` |
| `src_external` | `weather` |
| `src_finance` | `sku_weights`, `cost_params` |
| `src_hr` | `workforce_params` |

Mọi `update_policy` là `PENDING_CONFIRMATION`; contract không tự chọn INSERT/UPSERT,
conflict resolution hay partial-file policy. Currency/precision và model-level
semantics vẫn cần owner xác nhận ở task sau. `source_type: ASSUMED` trên Cost/HR
ngăn việc diễn giải các giá trị này là kết quả kinh doanh thực tế.

## Cost và HR

Cost giữ đúng bốn raw/canonical columns:
`L1_category_name_en`, `cost_ratio`, `shelf_life_days`,
`waste_handling_cost_ratio`. Tên cũ `disposal_cost_ratio` không được dùng.

HR giữ nguyên raw CSV 11 header nhưng contract canonical đổi chính xác năm tên:

| Raw | Canonical |
| --- | --- |
| `wage_eur_per_hour` | `hourly_wage_eur` |
| `morning_share` | `morning_shift_ratio` |
| `overtime_cap` | `overtime_cap_ratio` |
| `shortage_penalty` | `shortage_penalty_multiplier` |
| `rule_buffer` | `legacy_rule_buffer_ratio` |

Sáu cột còn lại giữ tên. Contract HR có đủ 11 canonical columns; nguồn có đúng 7
warehouse keys duy nhất.

## Compatibility Task08A

Task08A giữ code bootstrap, fingerprint, source path guard, ownership, idempotency và
transaction. Registry v1 cũ được version hóa tại
[`config/sources_task08a.yaml`](../config/sources_task08a.yaml) và loader adapter tại
[`src/config/source_registry_task08a.py`](../src/config/source_registry_task08a.py).
`src.bootstrap_sources` chỉ dùng adapter này. Không có migration/reset tự động và
không đổi `rohlik_bootstrap_dev.duckdb`.

## Chạy validation

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only --json
.\.venv\Scripts\python.exe -m src.validate_source_registry --json
.\.venv\Scripts\python.exe -m pytest tests/test_source_registry.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_bootstrap_sources.py -q
```

Lệnh đầu chỉ kiểm cấu hình. Lệnh thứ hai đọc đủ 7 CSV và dùng DuckDB `:memory:`;
không ghi raw hoặc database file. Exit `0` là cấu hình/preflight hợp lệ (warning
anomaly được báo trong JSON), `1` là config/contract sai, `2` là source preflight lỗi.
Missing source, wrong header/hash/row count/type, duplicate/null business key đều bị
chặn. YAML duplicate keys và unsafe paths bị chặn trước khi đọc file.

## PLANNED sau V4-01

V4-02 mới được phép thiết kế/tạo 14 physical landing tables và ingest theo
fingerprint/idempotency/transaction. Trước đó cần duyệt update policies và kế hoạch
backup/migration; không dùng `CREATE OR REPLACE` trên landing đã có update. Các tầng
stg/core/mart, DQ gates, entry/audit/undo, models và orchestrator không thuộc V4-01.
