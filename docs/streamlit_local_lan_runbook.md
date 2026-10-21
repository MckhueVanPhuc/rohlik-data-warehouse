# Rohlik Decision Hub v3.0 — Local/LAN Runbook

## Ranh giới an toàn

- Mặc định `.streamlit/config.toml` bind `127.0.0.1:8501`.
- LAN là opt-in, chạy đúng một foreground Streamlit process trên `0.0.0.0:8501`.
- Script không đổi Windows Firewall, Network Profile, router, database hoặc account.
- Client chỉ dùng browser; không mở trực tiếp `.duckdb` hoặc `data/auth/users.json`.
- Không port forwarding, UPnP, public DNS hoặc expose TCP 8501 ra Internet.

LAN dùng HTTP chưa mã hóa. Chỉ dùng mạng tin cậy và dữ liệu không nhạy cảm. Với dữ liệu
thật, cần HTTPS termination qua reverse proxy hoặc VPN/tunnel doanh nghiệp được phê duyệt.

## Localhost mặc định

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Mở `http://127.0.0.1:8501`. Sidebar hiển thị `LOCAL`.

## Khởi động LAN opt-in

```powershell
.\scripts\start_streamlit_lan.ps1
```

Script kiểm tra repository, `.venv`, entry point và listener TCP 8501, sau đó chạy:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py `
  --server.address 0.0.0.0 --server.port 8501
```

Script đặt `RDH_NETWORK_MODE=LAN` cho process để sidebar hiển thị `LAN`; giá trị môi
trường trước đó được khôi phục khi process dừng. Không có IPv4 host hardcode. Dừng bằng
`Ctrl+C` trong terminal đã chạy script.

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Format-Table InterfaceAlias,IPAddress
```

Client cùng LAN mở `http://<HOST_IPV4>:8501`.

## Windows Firewall — thao tác thủ công

Trước hết xác nhận profile là `Private`; runbook không tự đổi profile:

```powershell
Get-NetConnectionProfile
```

Nếu người quản trị host phê duyệt, mở PowerShell Run as Administrator:

```powershell
New-NetFirewallRule `
  -DisplayName "Rohlik Decision Hub LAN TCP 8501" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8501 `
  -Profile Private `
  -RemoteAddress LocalSubnet
```

Sau demo:

```powershell
Disable-NetFirewallRule -DisplayName "Rohlik Decision Hub LAN TCP 8501"
```

Không tắt toàn bộ firewall hoặc đổi Network Profile để chữa lỗi kết nối.

## MANUAL_VERIFY

- [ ] Host chỉ có một listener/process TCP 8501.
- [ ] Browser A mở URL LAN, thấy login và chỉ `admin_local` đăng nhập được.
- [ ] Browser B/profile riêng có session độc lập; logout B không logout A.
- [ ] Anonymous/direct URL không vượt qua `require_admin()`.
- [ ] Có đúng 8 pages; không có `/nhap-du-lieu`, upload, Undo, pipeline/model action.
- [ ] Client không có quyền/mount trực tiếp database hoặc credential store.
- [ ] Dừng server và disable firewall rule sau demo.

Không tuyên bố đã test vật lý hai thiết bị cho đến khi người vận hành hoàn tất checklist.

## Troubleshooting

- `Get-NetTCPConnection -State Listen -LocalPort 8501` để kiểm tra port/PID.
- `Test-NetConnection <HOST_IPV4> -Port 8501` từ Windows client.
- Guest Wi-Fi có thể bật AP isolation; dùng mạng nội bộ được phê duyệt.
- DHCP có thể đổi IPv4; tra lại trước mỗi demo, không hardcode IP.
- VPN có thể chặn local routes; tuân thủ chính sách tổ chức.
- Restart Streamlit thu hồi toàn bộ server-side sessions.
