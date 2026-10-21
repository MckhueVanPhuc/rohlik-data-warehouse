# Legacy Task07/08A Config

> Superseded by V4 `sources.yaml`, `contract.yaml` and `settings.yaml`.

`sources.yaml` là Source Registry của Task 07: **14 bảng logic / 9 phòng ban**, tham
chiếu sáu CSV lịch sử read-only. Chỉ mô tả và validate metadata; không có bảng thật,
Source Registry không thực thi ETL, CSV upload, authentication hoặc INSERT/UPSERT.

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry
```

Chạy tại root repository. Kỳ vọng cấu hình VALID, sáu file/hash VERIFIED, Finance/HR
MISSING đúng thiết kế. Task 08A có thể được chuẩn bị trong schema/database thử nghiệm
tách biệt sau khi phạm vi được duyệt; Task 08B vẫn NOT_READY vì schema/mapping/chính
sách còn pending. Không yêu cầu Data Contract BT1–BT8 cho bootstrap thử nghiệm.
Để kiểm tra source-free checkout, dùng `--metadata-only`; tùy chọn này không xác
nhận nguồn hiện tại tồn tại. Có `--json` để xem báo cáo có cấu trúc.

Cấu trúc:

- `source_files`: metadata nguồn đã đo ở Task 06 — path, hash, row count, 64 cột
  với inferred type/null count; evidence không có nghĩa schema nghiệp vụ được duyệt.
- `tables`: tên/department/purpose, source refs, grain/keys, proposed columns/types,
  direct mappings, mappings trì hoãn, DQ refs, consumers, upload và pending decisions.
- `global_decisions`: các chính sách chưa được phê duyệt.
- `upload_batch_metadata`: hợp đồng metadata batch, chưa tạo database schema.
- `analysis_only_derived_fields`: order_index/max_discount/final_price là đề xuất
  tầng phân tích, không tạo thành cột gốc hay tự tính trong registry.

Loader Python ở `src/config/`, YAML ở `config/`; hai thư mục có vai trò khác nhau.
Xem [Source Registry Guide](../docs/source_registry.md) cho cách sửa, review, đánh dấu
phê duyệt và bàn giao ETL/Streamlit. Không đưa secrets, mẫu records hay dữ liệu giả
Finance/HR vào YAML. Không tự đổi status pending thành VERIFIED chỉ để CLI hết cảnh báo.
