# Source Registry & Configuration — TASK 07

Ngày 18/10/2026. **Đã triển khai loader/validation CLI và metadata**, chưa triển khai
ingestion, Source Tables, SQLite Business Schema, CSV upload, sync hoặc Warehouse.
Registry hợp lệ về kỹ thuật **không đồng nghĩa READY_FOR_INGESTION**.

Nguồn đối chiếu: [Task 06 Dictionary](data_dictionary.md), [Mapping](source_mapping.md),
[Profiling Report](data_profiling_report.md), [DQ Rules](data_quality_rules.md),
[v3 C1–C4/D1/E0–E1](../Rohlik_Decision_Hub_Huong_dan_thuc_hien_v3.md),
[CSV Upload Contract](csv_upload_contract.md), README và Setup Tutorial. Workflow
Data Contract BT1–BT8 đã RETIRED ngày 19/10/2026; registry dựa trên bằng chứng nguồn.

## 1. Kiến trúc và phạm vi

Lịch sử: sáu CSV Kaggle (read-only) → Source Tables → DuckDB Bronze → Silver → Gold
→ Mart. Cập nhật: Streamlit CSV Upload → backend validate → SQLite records + audit
events + metadata cùng transaction → PENDING_SYNC → DE chủ động batch sync DuckDB
→ kiểm định → Parquet snapshots → Streamlit Dashboard.

Task 07 chỉ cung cấp config cho các bước sau, chưa thực thi luồng nào. Không ghi
đè sáu CSV gốc, không coi upload trực tiếp vào file lịch sử hay DuckDB là kiến trúc
được duyệt. Finance/HR phải có nguồn thật, schema và giá trị được duyệt trước sử dụng.

## 2. Tổ chức cấu hình

[config/sources.yaml](../config/sources.yaml) dùng `registry_version: 1`:

| Nhóm | Nội dung |
| --- | --- |
| `source_files` | Catalog sáu file với paths, hash SHA-256, số dòng, UTF-8 compatibility, delimiter/header, inferred types và null counts đủ 64 cột từ Task 06. |
| `tables` | 14 định nghĩa logic: name, department, description, source_type/source_files/source_availability, grain/keys, columns, mappings, deferred_mappings, transformations, DQ refs, consumers, approvals, upload, provenance, pending_decisions. |
| `global_decisions` | Null Sales, discount âm, warehouse_limited, currency/units, calendar precedence, known-future, update/duplicate policy, Finance/HR, effective keys, authorization/audit và bằng chứng tích hợp model. |
| `upload_batch_metadata` | 11 tên metadata đã được đề xuất, không phải DDL hoặc cột tự động của Source Tables. |
| `analysis_only_derived_fields` | `order_index`, `max_discount`, `final_price` là REFERENCE_ONLY cho tầng phân tích, không phải cột CSV nguồn. |

Target columns chứa proposed DuckDB/SQLite types; `null` nghĩa chưa chốt datatype
hoặc precision, không tự đổi thành type mặc định. `required` nói về cột có bắt buộc
trong file upload, `nullable` nói về giá trị của cột, là hai khái niệm khác nhau.
`true/false/null` của hai thuộc tính là **đề xuất**, vì `columns[].status` vẫn pending.
Không dùng quan sát “không thấy null” để suy ra NOT NULL đã được duyệt.

Các key cơ sở Finance/HR hiện là L1_category_name_en và warehouse. Grain có ghi
version/hiệu lực chưa chốt; cần thống nhất composite key/cột hiệu lực trước schema,
không bịa tên cột/version hoặc dtype chỉ để lấp chỗ trống. Money/cost precision chưa
chốt được biểu diễn bằng type `null` và decision pending, không giả số liệu mẫu.

`mappings` khai báo từng direct source_column/file_id → target. Proposed casting
BIGINT cho integer-valued DOUBLE là quyết định type cần duyệt, chưa chạy CAST.
`transformations` là mô tả đề xuất có status/evidence, không là câu SQL được thực thi.
Giữ nguyên khả năng null Sales/total_orders, discount âm và weather null.

### Calendar và derived fields

Calendar target hiện đề xuất hai key + năm giá trị chung, mỗi trường có mapping từ
cả hai file lịch. Tám cột Orders-only được liệt kê trong `deferred_mappings`, target
chưa quyết định, bao gồm warehouse_limited. Như vậy metadata nguồn không bị bỏ quên
nhưng không tự đưa cột vào schema/feature. Đề xuất union/precedence chưa thực hiện.

`orders` khác `total_orders`; order_index chỉ được mô tả là MEDIAN(total_orders)
theo warehouse/date, bỏ null, ở tầng phân tích tương lai. Loader từ chối mapping
order_index thành cột nguồn giả.

## 3. Trạng thái và 14 bảng

| Status | Nghĩa |
| --- | --- |
| VERIFIED | Có bằng chứng cho đúng nội dung được đánh dấu; file evidence khác schema approval. |
| REFERENCE_ONLY | Tham khảo v3/chưa được chủ dữ liệu hoặc model xác nhận; consumers hiện thuộc nhóm này. |
| PENDING_CONFIRMATION | Quyết định/schema/mapping chưa được duyệt, phải giữ nguyên câu hỏi mở. |
| MISSING | Không có nguồn thật; không phải lỗi cú pháp YAML. |
| NOT_APPLICABLE | Không áp dụng, có detail/evidence giải thích; ví dụ biến đổi khi chưa có nguồn. |

`source_files.*.verification_status` và `table.source_availability=VERIFIED` chỉ là
bằng chứng nguồn ở Task 06. `schema_approval`/`mapping_approval` của **mọi bảng đều
PENDING_CONFIRMATION**, upload cũng pending và disabled. Không bảng nào được cấp
quyền ingestion hoặc cập nhật tự động.

| Source table | Source file refs | Availability |
| --- | --- | --- |
| sales_ecommerce.orders_daily | orders | VERIFIED |
| sales_ecommerce.sku_sales_daily | sales | VERIFIED |
| marketing_pricing.prices | sales | VERIFIED |
| marketing_pricing.promotions | sales | VERIFIED |
| marketing_pricing.min_order_value_changes | orders | VERIFIED |
| warehouse_ops.availability | sales | VERIFIED |
| warehouse_ops.ops_events | orders | VERIFIED |
| category.product_master | inventory | VERIFIED |
| planning.calendar | orders_calendar + sales_calendar | VERIFIED |
| digital_product.user_activity | orders | VERIFIED |
| external.weather | orders | VERIFIED |
| finance.sku_weights | weights | VERIFIED |
| finance.cost_params | Không có path/records/mapping nguồn giả | MISSING |
| hr.workforce_params | Không có path/records/mapping nguồn giả | MISSING |

Finance/HR chỉ có mục đích, schema/type/required/key/grain đề xuất, consumers tham
khảo, câu hỏi mở và thiết kế upload tương lai. Các giá trị cost/lương/năng suất của
v3 là giả định REFERENCE_ONLY, không đưa thành records hoặc CSV trong registry.

## 4. Chạy kiểm tra

Từ root repository, dùng môi trường hiện có (PyYAML/Pydantic, không cài thêm gói):

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry
.\.venv\Scripts\python.exe -m src.validate_source_registry --json
```

CLI mặc định load YAML, kiểm cấu trúc/cross-references/path trước, rồi kiểm sáu file
tồn tại và SHA-256 khớp. Chỉ đọc bytes để hash, không parse/ingest CSV, không kết nối
database. Expected: SUCCESS, configuration VALID, source files VERIFIED, 14 tables,
hai MISSING by design, liệt kê pending và **Task 08 NOT_READY**. Nội dung tiếng Việt
được xuất UTF-8 để chạy được trong terminal Windows.

Trên máy mới chưa có CSV, chỉ kiểm metadata bằng:

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only
```

Kỳ vọng file_check=NOT_CHECKED, không coi nguồn hiện tại đã được xác minh. Có
`--config PATH`; path config tương đối tính từ root, không phải cwd. CLI `-m` vẫn
cần root có trong Python import path; cách đơn giản là chạy tại root repository.

| Exit | Ý nghĩa | Xử lý |
| --- | --- | --- |
| 0 | Config VALID, pending/MISSING đúng thiết kế được báo rõ; file check đạt hoặc chủ động bỏ qua. | Review pending; không coi là cho phép Task 08. |
| 1 | FAILED_CONFIGURATION: YAML/cấu trúc/cross-ref/path sai. | Sửa config theo lỗi; không sửa CSV/database để vượt check. |
| 2 | FAILED_SOURCE_FILES: nguồn lịch sử thiếu/không đọc được hoặc hash thay đổi. | Kiểm tra bàn giao/quyền/path; profile nguồn mới và review evidence trước cập nhật catalog. |

Hash khớp không chứng minh dữ liệu hợp lệ nghiệp vụ. Catalog giữ evidence lịch sử;
file_check mới là kết quả sự hiện diện/hash tại thời điểm chạy. Không tải lại nguồn
hoặc tự đổi hash trong YAML chỉ để báo SUCCESS.

## 5. Loader, API và validation

[src/config/source_registry.py](../src/config/source_registry.py) là package Python;
`config/` ở root chỉ chứa YAML/README, tránh nhầm hai vai trò.

```python
from src.config.source_registry import load_registry, registry_report

registry = load_registry()  # metadata only; không yêu cầu CSV tồn tại
names = registry.list_tables(department="finance")
table = registry.get_table("sales_ecommerce.sku_sales_daily")
print(table.business_keys)
print(table.schema_approval.status)  # PENDING_CONFIRMATION
print(registry_report(registry)["task08"])  # NOT_READY
```

get_table trả bản sao metadata, không thực hiện SQL hoặc cung cấp hàm save/ingest.
Pydantic strict models từ chối field lạ, thiếu required metadata, type/status sai.
Safe YAML loader không thực thi Python tags và từ chối duplicate mapping keys.

Kiểm tra: đúng bộ 14 logical names; names/columns/keys không trùng; key không rỗng
và có trong target; source refs/column mappings/deferred mappings có trong catalog;
upload columns tạo partition required/optional/unresolved; DQ refs hợp lệ; file
paths thuộc allowlist sáu CSV và không absolute/traversal/URL/symlink thoát root.
Schema VERIFIED cần người/ngày/evidence và verified keys/columns; mapping VERIFIED
cần verified mappings. Finance/HR không thể tự mang path hoặc approval thật khi MISSING.

`expected_tables` chỉ phục vụ fixtures nhỏ trong test/API kiểm cấu trúc; CLI luôn
kiểm đủ 14. Không dùng tùy chọn đó để bỏ qua governance hay cho nguồn ngoài allowlist.
Không triển khai khóa đa tiến trình, authentication, pipeline hoặc kiểm tra giá trị
records trong Task 07.

## 6. Cấu hình phục vụ CSV Upload sau này

Mỗi bảng có owner department, source_type, business keys và proposed column types;
upload.allowed_columns/required_columns/optional_columns/unresolved_columns là
metadata ứng viên gắn schema pending, **không phải quyền đã cấp**.
`access=BLOCKED_PENDING_APPROVAL`, `enabled=false`, backend_authorization_required=true.
Mọi write_policy/duplicate_policy còn PENDING_CONFIRMATION; không tự INSERT/UPSERT,
không tự clip/fill/drop/giữ file mới nhất. Loader Task 07 cố ý không cho enabled=true.

Upload metadata được tham chiếu từ `upload_batch_metadata`: batch_id, source_table,
department, uploaded_by, uploaded_at, original_filename, file_hash, total_rows,
accepted_rows, rejected_rows, status. Chưa tạo schema lưu các metadata này.
Backend tương lai phải xác minh danh tính/quyền, không tin department client gửi.
Records hợp lệ + audit + metadata phải cùng transaction SQLite; commit thành công
PENDING_SYNC; DE sync và chỉ publish Parquet sau kiểm định theo CSV Upload Contract.

## 7. Sửa mapping, thêm nguồn và phê duyệt

1. Có bằng chứng nguồn mới/đổi version: chạy profiling và review dictionary/mapping;
   giữ hash cũ trong lịch sử tài liệu nếu cần. Không thay Task 06 snapshot trong lần này.
2. Cập nhật catalog path/header/type/hash/null evidence; cập nhật bảng dùng file đó,
   source columns/target schema/keys và required/optional/unresolved upload lists.
3. Không thêm trường chưa có trong CSV vào direct mapping. Dẫn xuất thuộc tầng phân
   tích hoặc phải được thiết kế/duyệt riêng. Missing Finance/HR không được tạo placeholder records.
4. Thêm một logical table/CSV ngoài bộ Task 07 cần quyết định thay đổi phạm vi: cập
   nhật allowlist `ALLOWED_SOURCE_PATHS`, `EXPECTED_TABLES` và consistency policy/tests
   trong loader cùng YAML/docs, không chỉ thêm dòng YAML để bypass danh sách 14.
5. Bổ sung DQ rules ở tài liệu và tham chiếu hợp lệ; chưa thực thi rule chỉ vì có ID.
6. Ghi người duyệt, ngày, evidence, version cho quyết định VERIFIED; cập nhật đồng
   bộ field/key/mapping statuses. Không sửa status nếu chưa có phê duyệt thực tế.
7. Chạy CLI và pytest; người nghiệm thu review cả pending/readiness trước giao Task 08.

Task 07 có chốt chặn cố ý: Finance/HR chưa được phép đổi MISSING và upload chưa được
enabled. Khi thật sự có nguồn/approval phải có change được duyệt để mở rộng validator,
không sửa một flag để tạo cảm giác mọi thứ đã sẵn sàng. Loader không tự chấp nhận
nguồn Finance/HR giả hoặc deploy upload trong lúc phạm vi chỉ là cấu hình.

## 8. Kiểm thử, bàn giao và readiness

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_source_registry.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Các ca mới kiểm YAML hợp lệ/sai/duplicate keys/unsafe tags, metadata thiếu, trùng
bảng, keys/path/mapping sai, file thiếu/hash đổi, MISSING hợp lệ, pending/API copy,
trạng thái phê duyệt/upload, CLI exit codes và không kết nối database. Source files
tạm chỉ được tạo cho test existence/hash; metadata-only fixtures không cần CSV thật.
Path escape sau resolve được giả lập để không cần quyền tạo symlink Windows.

Kết quả thực tế trên cấu hình hoàn chỉnh: **39 registry tests PASS, 0 FAIL; toàn bộ
77 PASS, 0 FAIL, không skip** (baseline Task 06 là 38). Không hardcode số tests trong
API hoặc validator. Test hạ tầng không xác nhận Finance/HR hay CSV upload đã hoạt động.

**Task 08A — Provisional Historical Source Bootstrap:** có thể chuẩn bị triển khai từ
sáu CSV và registry hiện tại trong database/schema thử nghiệm tách biệt sau khi phạm
vi thử nghiệm được phê duyệt. Không cần Data Contract BT1–BT8; Task 07 không tự cấp
quyền chạy bootstrap.

**Task 08B — Approved Source Finalization: NOT_READY.** Chưa được tạo/nạp Source Tables
chính thức. Còn BLOCKED: approval schemas/mappings, null/discount,
warehouse_limited/calendar/currency/known-future/update/duplicate policy, effective
keys và nguồn/giá trị Finance/HR, bằng chứng tích hợp model. Đừng gọi 12 bảng có source là
12 bảng đã duyệt hoặc tự chọn subset ingestion trong Task 07.

Người ETL nhận Registry API, proposed mappings/DQ refs và pending list; người Streamlit
nhận cấu hình ứng viên template/column types/keys, bộ metadata batch và ranh giới
backend authorization. Cả hai phải chờ schema/quyền/chính sách đã duyệt và triển khai
được nghiệm thu, không suy từ SUCCESS của CLI.
