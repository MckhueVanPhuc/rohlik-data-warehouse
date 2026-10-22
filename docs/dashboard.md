# Dashboard và thao tác vận hành

Streamlit khởi chạy từ `app/main.py`. Điều hướng tập trung tại `app/navigation.py` với 10 trang: overview, operations, logistics, demand, pricing, growth, explorer, data entry, batches và system.

## Khởi chạy

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user status
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Ứng dụng dùng local authentication, password Argon2id, rate limiting và session phía server. Giữ localhost mặc định; chỉ bật LAN khi đã kiểm tra tài khoản, firewall và phạm vi mạng.

## Runbook LAN

Chạy script preflight bằng PowerShell thường, không chạy elevated:

```powershell
.\scripts\start_streamlit_lan.ps1
```

Từ máy khác trong cùng mạng, mở `http://<HOST_IPV4>:8501`. Đánh dấu bước này là `MANUAL_VERIFY`: xác nhận login, logout, timeout và các trang không rò dữ liệu khi chưa xác thực. Nếu client không kết nối được, kiểm tra đúng IPv4, DHCP thay đổi địa chỉ và AP isolation trên Wi-Fi.

Chỉ quản trị viên mới tạo firewall rule, và chỉ sau khi xác nhận network profile là Private:

```powershell
New-NetFirewallRule -DisplayName "Rohlik Streamlit 8501" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8501 -Profile Private -RemoteAddress LocalSubnet
```

Thu hồi rule khi kết thúc thử nghiệm bằng `Disable-NetFirewallRule`. Không mở ra Internet trực tiếp. Truy cập ngoài máy/trusted LAN phải dùng HTTPS qua reverse proxy đã được harden và có quy trình quản trị credential.

## Quyền và ranh giới

- Reporting service mở DuckDB read-only và chỉ đọc mart allowlist.
- Upload CSV và data entry đi qua validation + contract, không ghi trực tiếp tùy ý.
- Batch history, undo mềm và refresh UI đi qua operations service có audit.
- Chạy BT1–BT8 chỉ bằng CLI, không từ nút trên dashboard.
- Khi mart/model output chưa có, UI hiển thị readiness thay vì dữ liệu giả.

## Reporting, freshness và readiness

Năm base marts là `mart.sales_orders_day`, `mart.ops_warehouse_day`, `mart.category_sku_day`, `mart.marketing_promo_day` và `mart.exec_kpi_month`. Bảy model views là `bt1_forecast_orders`, `bt2_staff_driver_plan`, `bt3_lost_sales_day`, `bt4_bt6_sku_plan_day`, `bt5_promo_effect`, `bt7_markdown_day` và `bt8_growth_month` trong schema `mart`.

Mỗi trang phải phân biệt warehouse không khả dụng, mart chưa publish, dữ liệu sẵn sàng và model output đang chờ. Freshness lấy từ metadata/run thực tế; không dùng thời gian render trang làm thời gian cập nhật dữ liệu. KPI chỉ được tính từ reporting marts allowlist.

## Quy trình upload an toàn

1. Chọn đúng source/contract và xem preview.
2. Kiểm tra schema, số hàng và giới hạn mặc định 50.000 hàng.
3. Xác nhận batch trước khi append.
4. Theo dõi refresh và DQ; upload thành công không có nghĩa mart đã publish.
5. Nếu cần đảo, dùng soft undo theo batch và giữ audit trail.

Không upload file chứa credential, PII ngoài phạm vi hoặc schema chưa được phê duyệt.

## Chẩn đoán nhanh

- Không đăng nhập được: kiểm tra `scripts.create_user status`, clock máy và quyền đọc `data/auth`.
- Warehouse unavailable: kiểm tra cấu hình và file database; không tự chạy `init`.
- Trang không có dữ liệu: kiểm tra mart allowlist, pipeline và model output.
- Writer busy: đóng tác vụ ghi khác hoặc chờ lock; không sửa DuckDB trực tiếp.
- Upload bị từ chối: sửa file theo contract, không tắt validation.

Thay đổi giao diện không được làm yếu authentication, audit, data contract hoặc ranh giới read-only của reporting.
