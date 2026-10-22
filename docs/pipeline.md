# Pipeline và runbook

Entry point duy nhất cho pipeline là `python -m pipeline.run`.

## Lệnh

| Lệnh | Mục đích |
| --- | --- |
| `status` | Xem trạng thái warehouse và lần chạy. |
| `init` | Khởi tạo warehouse khi database chưa tồn tại. |
| `ingest` | Kiểm tra registry và nạp landing. |
| `refresh` | Xây STG → Core → Mart → DQ trong transaction. |
| `evaluate` | Đánh giá model và tạo bằng chứng để chốt tham số. |
| `models` | Chạy DAG BT1–BT8 với tham số hiện hành. |
| `all` | Chạy chuỗi pipeline đầy đủ theo runner. |
| `import-outputs` | Nhập output model đã bàn giao theo contract. |

Xem tùy chọn chính xác bằng `python -m pipeline.run --help` và `python -m pipeline.run <lệnh> --help`.

## Trình tự lần đầu

1. Xác nhận 7 CSV bằng `python -m src.validate_source_registry`.
2. Kiểm tra `data/warehouse/rohlik.duckdb`. Nếu đã tồn tại, không chạy `init`.
3. Chạy `status`, đọc đường dẫn database và cấu hình.
4. Chỉ với môi trường mới, chạy `init` theo change window đã duyệt.
5. Chạy `evaluate` để đánh giá tham số model trên dữ liệu của môi trường.
6. Chạy `models`, kiểm tra metadata và DQ trước khi mở dashboard.

## Vận hành cập nhật

- Chỉ một writer được phép hoạt động; lock timeout mặc định là 10 giây.
- Update landing tuân thủ `config/contract.yaml`; policy được duyệt là `APPEND_FULL_ROW_SOFT_UNDO`.
- Refresh biến đổi và DQ là atomic. Khi có lỗi mức `ERROR`, transaction rollback.
- Không chỉnh DuckDB trực tiếp khi Streamlit hoặc pipeline writer đang chạy.
- Luôn giữ backup và run metadata trước một thay đổi dữ liệu quan trọng.

Mỗi batch có định danh và metadata riêng. Idempotency được đánh giá theo batch, business key và update policy; không chạy lại mù quáng một file chỉ vì lệnh trước mất kết nối. Soft undo tạo hành động có audit thay vì xóa vật lý lịch sử.

## Backup, recovery và nghiệm thu

- Xác nhận backup hoàn tất trước thay đổi material; backup không thay thế transaction.
- Recovery dùng công cụ DuckDB hiện hành và bản backup đã xác minh, không dùng module SQLite cũ.
- Sau ingest/refresh: kiểm tra run status, row counts từng lớp, DQ summary, mart freshness và model-output availability.
- Chỉ nghiệm thu khi không có DQ `ERROR`, transaction đã commit và reporting mở read-only thành công.
- Khi rollback xảy ra, giữ failure report và input batch để điều tra; không sửa trực tiếp warehouse để “hoàn tất” run.

## Xử lý sự cố

- Registry fail: sửa đúng file nguồn hoặc cấu hình được phê duyệt; không bỏ checksum.
- Writer lock: xác định process sở hữu lock, không xóa lock mù quáng.
- DQ error: đọc failure report và run metadata; không publish mart chưa đạt.
- Model fail: giữ input/output của run, kiểm tra params và dependency DAG.
- Warehouse đã tồn tại: không chạy lại `init`; dùng `status` và quy trình refresh.

DAG model chính thức: `BT1 → BT3 → BT5 → BT8 → BT2 → BT4 → BT6 → BT7`.
