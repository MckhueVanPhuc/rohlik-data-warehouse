# Rohlik Decision Hub v3.0 — Dashboard Runbook

## Kiến trúc vận hành

Streamlit v3.0 là dashboard admin-only và read-only. Tám trang sử dụng chung
`app/services/reporting.py`, chỉ truy cập năm allowlisted marts:

- `mart.sales_orders_day`
- `mart.ops_warehouse_day`
- `mart.category_sku_day`
- `mart.marketing_promo_day`
- `mart.exec_kpi_month`

Mọi operation reporting gọi `require_admin()`, mở DuckDB bằng connection read-only,
introspect schema hiện hữu, rồi chỉ dùng identifiers đã xác minh. Không có arbitrary SQL,
upload, CRUD, Undo, init/refresh pipeline hoặc model execution.

## Readiness

- `WAREHOUSE_NOT_READY`: file warehouse không tồn tại/không mở read-only được.
- `TABLE_NOT_AVAILABLE`: warehouse có nhưng mart của trang chưa được publish.
- `DATA_READY`: mart tồn tại; UI cho phép filter/pagination/aggregation trên cột thật.
- `PENDING_MODEL`: BT1–BT8 chưa có output đã kiểm định; không tạo forecast giả.

Warehouse chính hiện chưa có reporting marts. Đây là trạng thái hợp lệ; dashboard không
tự tạo schema hoặc đọc raw CSV để lấp khoảng trống.

## Bộ lọc và query

- Warehouse/category filter chỉ xuất hiện nếu schema introspection tìm thấy cột tương ứng.
- Time filter chỉ xuất hiện với cột DATE/TIMESTAMP thực tế.
- Metric chart chỉ cho chọn cột numeric hiện hữu; aggregation chạy trong SQL.
- Bảng chi tiết phân trang tối đa 250 rows từ UI, backend hard-limit 500.
- EDA chỉ chọn trong năm marts; không nhận SQL text.

## Cập nhật dữ liệu

MVP không hỗ trợ concurrent writer. Khi Data Engineering cần cập nhật warehouse:

1. Dừng Streamlit.
2. Chạy DE CLI độc lập theo runbook của pipeline.
3. Xác minh DQ/marts.
4. Khởi động lại Streamlit.

Không gọi DE CLI hoặc writer subprocess từ UI.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Reporting tests dùng DuckDB tạm và xác minh file không đổi sau query.
