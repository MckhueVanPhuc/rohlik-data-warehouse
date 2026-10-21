# Rohlik Decision Hub v3.0 — Single-admin Authentication Runbook

## Phạm vi

Streamlit chỉ cho phép username được cấu hình tại `config/auth.yaml`: `admin_local`.
Credential store là `data/auth/users.json`, được Git ignore và nằm ngoài DuckDB. Hệ thống
giữ Argon2id, generic login errors, rate limiting theo account/browser session, opaque
server-side sessions, idle timeout và session revocation.

Trường legacy `role: data_team` vẫn được đọc để tương thích schema credential v1 nhưng
không cấp quyền. Streamlit không còn đọc `config/roles.yaml` và không có guest, demo,
public registration hoặc password hardcode.

## Nguyên tắc bảo toàn account

- Không xóa, reset hoặc rewrite credential store trong deploy/refactor.
- Không tự tạo admin nếu `admin_local` bị thiếu. CLI phải fail closed.
- Không truyền password trên command line. `change-password` dùng `getpass`.
- Không chia sẻ `data/auth/` qua network drive và không commit file này.
- Disable hoặc đổi password làm session hiện có mất hiệu lực ở lần xác minh tiếp theo.

## Quản lý admin trên máy host

```powershell
# Chỉ in username và enabled; không in role/hash
.\.venv\Scripts\python.exe -m scripts.create_user status

# Đổi password bằng prompt ẩn
.\.venv\Scripts\python.exe -m scripts.create_user change-password

# Vô hiệu hóa và khôi phục account hiện hữu
.\.venv\Scripts\python.exe -m scripts.create_user disable
.\.venv\Scripts\python.exe -m scripts.create_user enable
```

CLI chỉ thao tác username từ `config/auth.yaml`. Không còn lệnh tạo business user hoặc
tham số `--role`. Nếu configured admin không tồn tại, CLI dừng và không tạo account mới.

```powershell
icacls data\auth
icacls data\auth\users.json
git check-ignore data/auth/users.json
```

## Login, logout và session

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Mở `http://127.0.0.1:8501`. Browser chỉ giữ opaque token trong Streamlit session state.
Mỗi rerun/action xác minh lại token với registry server, account hiện tại, username
allowlist, enabled state và `password_changed_at`. Restart Streamlit thu hồi toàn bộ
session in-memory. Idle timeout mặc định là 30 phút.

Checklist:

- Anonymous hoặc direct page URL chỉ thấy login.
- `admin_local` với password hiện hữu đăng nhập được.
- Username khác nhận cùng generic error kể cả credential hợp lệ.
- Logout thu hồi đúng session hiện tại.
- Disable/đổi password làm token cũ không còn hợp lệ.
- Forged token và expired session bị từ chối.

## LAN

Authentication không thay đổi giữa LOCAL và LAN. LAN dùng HTTP chưa mã hóa, chỉ phù hợp
demo trên mạng tin cậy với dữ liệu không nhạy cảm. Dữ liệu thật cần HTTPS/VPN được quản
trị phê duyệt. Xem [LAN runbook](streamlit_local_lan_runbook.md).
