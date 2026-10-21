# Rohlik Decision Hub — Dashboard v3.0 R0 Refactor Audit

**Ngày audit:** 21/10/2026  
**Phạm vi:** R0 — chỉ đọc/audit, không refactor source code  
**Quyết định đích:** single-admin, dashboard-only, read-only, local-first

## 1. Kết luận R0

- Streamlit hiện là ứng dụng có xác thực local, session phía server và RBAC 7 role; runtime vẫn phụ thuộc trực tiếp vào `config/roles.yaml` tại authentication, authorization và navigation.
- Có 9 page definitions. Trang thứ chín là `app/views/entry.py`; tám trang còn lại khớp danh sách dashboard v3.0.
- UI hiện chưa có upload, data editor, CRUD, Undo, pipeline execution hay model execution thật. Các chức năng này mới là placeholder/button bị disabled và mô tả trong tài liệu/test.
- `admin_local` tồn tại, enabled, là tài khoản duy nhất trong credential store và đang mang role legacy `data_team`. Record đọc hợp lệ theo schema hiện tại, bao gồm yêu cầu hash Argon2id. Không có password hoặc hash nào được in trong audit.
- Không thể chứng minh mật khẩu thực tế đăng nhập thành công nếu không có mật khẩu người dùng. R0 chỉ xác minh account có đầy đủ điều kiện cấu trúc để authentication hiện tại chấp nhận: tồn tại, enabled, role hợp lệ và credential record hợp lệ. Không thử/reset/đổi mật khẩu.
- Có thể chuyển sang single-admin mà không rewrite `data/auth/users.json`: giữ nguyên trường `role: data_team` như metadata legacy, ngừng dùng role để quyết định đăng nhập/quyền, và allowlist username chuẩn hóa `admin_local` từ `config/auth.yaml`.
- Baseline hiện xanh: `216 passed in 75.40s`; `pip check`: `No broken requirements found.`

> Lưu ý nguồn kế hoạch: file có tên `Rohlik_Streamlit_Dashboard_Only_Refactor_Plan_v3.md` không hiện diện vật lý trong workspace tại thời điểm audit (`rg --files` không tìm thấy). Audit này dùng nguyên văn kế hoạch v3.0 được cung cấp qua attachment của yêu cầu hiện tại. Không tạo hoặc di chuyển bản kế hoạch trong R0.

## 2. Git audit

- Branch hiện tại: `feat/streamlit-2.0-local`.
- Worktree đã dirty trước R0. R0 không revert, reset, stage, commit hoặc push bất kỳ thay đổi nào.
- Trạng thái quan sát trước khi tạo báo cáo:

```text
## feat/streamlit-2.0-local
 M .gitignore
 M .streamlit/config.toml
 M requirements.txt
?? Xây dựng streamlit-2.0.md
?? app/
?? config/auth.yaml
?? config/roles.yaml
?? docs/authentication_runbook.md
?? docs/streamlit_implementation_audit.md
?? docs/streamlit_local_lan_runbook.md
?? pytest.ini
?? scripts/
?? tests/test_streamlit_s02.py
?? tests/test_streamlit_s03_auth.py
?? tests/test_streamlit_s04_lan.py
?? tests/test_streamlit_scaffold.py
```

Các thay đổi/untracked trên được xem là tài sản có sẵn của người dùng. File duy nhất R0 tạo là báo cáo này.

## 3. Audit năm module bắt buộc

| File | Hiện trạng | Khoảng cách tới v3.0 | Quyết định |
|---|---|---|---|
| `app/main.py` | Gọi `require_authenticated()`, truyền `user.role` vào sidebar và `build_navigation(user.role)` | Shell vẫn quảng bá và dùng role; tên guard chưa thể hiện single-admin | **MODIFY** trong R1/R2: dùng `require_admin()`, bỏ role khỏi navigation/sidebar |
| `app/navigation.py` | Import 9 view, trong đó có `entry`; đọc `roles.yaml` qua `RolePolicy` để xác minh role | Phụ thuộc RBAC và còn route `/nhap-du-lieu` | **MODIFY**: R1 bỏ role validation; R2 bỏ import/definition `entry`, còn đúng 8 trang |
| `app/auth.py` | Login/logout, opaque session token, rate limiter wiring; tạo `RolePolicy`, `AuthorizationService`; export `can_read/write/undo/refresh/authorize` | Bất kỳ tài khoản enabled có một trong 7 role đều có thể đăng nhập; authorization vẫn là role-based | **MODIFY** trong R1: allowlist `admin_local`, giữ login/logout/rate limit/session, thay guard bằng admin-only, bỏ action authorization |
| `app/services/identity.py` | Credential JSON atomic, Argon2id, password policy, limiter, session registry, revalidation | `UserRecord`, `AuthenticatedUser`, session record và `AuthenticationService` mang/kiểm `role`; constructor nhận `valid_roles` | **KEEP lõi / MODIFY nhỏ**: giữ cryptography/store/session/rate limit; thay role membership bằng configured admin username, đọc schema cũ mà không rewrite store |
| `app/services/access.py` | Toàn bộ `RolePolicy` và `AuthorizationService` dựa trên `roles.yaml`; có `can_read/write/undo/refresh` | Không còn phù hợp single-admin dashboard-only | **REMOVE khỏi runtime** trong R1; có thể xóa file sau khi mọi import/test đã được thay và xác nhận không còn reference |

Dependency liên quan ngoài năm file:

- `app/common.py`: có `load_roles()`, hiển thị role/policy ở sidebar, và renderer generic cho disabled action buttons — **MODIFY** ở R1/R2.
- `scripts/create_user.py`: load `RolePolicy`, cho tạo nhiều username/role và list role — **MODIFY** ở R1 thành công cụ quản lý đúng một admin; không tự chạy công cụ trong refactor.
- `config/auth.yaml`: đang có credential path, idle timeout, rate limit và password policy nhưng chưa có admin allowlist — **MODIFY** bằng `admin_username: admin_local`.
- `config/roles.yaml`: nguồn 7-role runtime hiện tại, trạng thái `PENDING_APPROVAL` — **REMOVE khỏi Streamlit runtime**; chỉ xóa file sau khi reference runtime/test/doc cần thiết đã được xử lý và xác nhận file không còn consumer DE độc lập.

## 4. Inventory `roles.yaml` và 7 roles

### 4.1. Runtime/CLI cần xử lý

| Consumer | Dependency |
|---|---|
| `app/auth.py` | `ROLE_CONFIG_PATH`, `RolePolicy`, `valid_roles`, `AuthorizationService`, các helper `can_*` và `authorize` |
| `app/navigation.py` | `RolePolicy(...).role_exists(role)` trước khi build menu |
| `app/services/access.py` | Loader/policy và toàn bộ quyết định read/write/undo/refresh |
| `app/services/identity.py` | Không đọc YAML trực tiếp nhưng nhận `valid_roles`, kiểm role khi login và revalidate session |
| `app/common.py` | `load_roles()` và copy role/policy trong sidebar |
| `scripts/create_user.py` | Đọc `roles.yaml`, validate `--role`, tạo/list business users |

### 4.2. Tests phải thay cùng refactor

- `tests/test_streamlit_scaffold.py`: hard-code đúng 7 roles, cấu trúc `roles.yaml`, permission matrix và `load_roles()`.
- `tests/test_streamlit_s03_auth.py`: tạo user `marketing`/`data_team`, dựng `RolePolicy`, kiểm `can_read/write/undo/refresh`, và CLI multi-user/multi-role.
- `tests/test_streamlit_s02.py`: hard-code 9 pages, có `entry`, và kiểm disabled sensitive actions.

### 4.3. Tài liệu lịch sử cần đánh dấu superseded/cập nhật, không dùng làm runtime

- `docs/authentication_runbook.md`
- `docs/streamlit_implementation_audit.md`
- `Xây dựng streamlit-2.0.md`

Các occurrence `roles.yaml` khác trong tài liệu Data Engineering/V4 là mô tả kiến trúc cũ. Không xóa máy móc trong R1 và không sửa `src/`.

### 4.4. Bảy role hiện tại

`executive`, `sales`, `demand_planning`, `warehouse_ops`, `logistics`, `marketing`, `data_team`.

Cần phân biệt occurrence role với tên miền nghiệp vụ. Ví dụ `warehouse_ops`, `marketing`, `sales`, `logistics` còn xuất hiện hợp lệ trong schema/source mapping, tên module/page hoặc dữ liệu DE. Chỉ loại bỏ ý nghĩa **authorization role**; không rename/xóa schema, source, mart, view hoặc module nghiệp vụ vì trùng tên.

## 5. Inventory entry/upload/undo/write/refresh/model actions

### 5.1. Code UI hiện có

| Vị trí | Reference | Trạng thái hiện tại | Đích |
|---|---|---|---|
| `app/navigation.py` | import `entry`, page `/nhap-du-lieu` | Route thật trong menu | **REMOVE** ở R2 |
| `app/views/entry.py` | template/preview/confirm/soft undo copy; ba disabled buttons chọn CSV, preview, confirm write | Placeholder, không nhận file/không ghi DB | **REMOVE** khỏi UI ở R2; xóa file sau reference audit |
| `app/common.py` | `disabled_actions` và `st.button(..., disabled=True)` | Renderer generic | **KEEP/MODIFY**: giữ nếu dashboard read-only còn cần disabled informational action; không dùng cho write/pipeline/model controls |
| `app/views/system.py` | disabled `Khởi tạo`, `Làm mới`, `Chạy mô hình` | Không gọi init/refresh/model | **REMOVE buttons** ở R2; giữ page ở chế độ status-only |
| `app/views/explorer.py` | disabled `Chạy truy vấn`, `Xuất kết quả` | Không thực thi query hiện tại | **MODIFY/KEEP**: query template SELECT và export kết quả có thể là read-only; không đồng nhất với database write |
| `app/auth.py` | logout button và login form submit | Security controls, không phải business write | **KEEP** |

Không tìm thấy `st.file_uploader`, `st.data_editor`, CRUD service, DuckDB `INSERT/UPDATE/DELETE`, subprocess pipeline, model runner hoặc write coordinator trong `app/`. `can_write`, `can_undo`, `can_refresh` chỉ là authorization API; `can_refresh(data_team)` hiện có thể trả true nhưng S03 không có execution path.

### 5.2. Tests/tài liệu mang scope 2.0

- `tests/test_streamlit_s02.py` yêu cầu entry và các disabled upload/write/refresh/model buttons; phải đảo thành negative assertions trong R2.
- `tests/test_streamlit_s03_auth.py` yêu cầu action permissions; phải thay bằng single-admin access tests trong R1.
- `docs/streamlit_implementation_audit.md`, `docs/authentication_runbook.md` và `Xây dựng streamlit-2.0.md` mô tả CSV upload, soft undo và refresh tương lai. Đây là tài liệu lịch sử 2.0, không phải implementation đang chạy.
- `docs/csv_upload_contract.md`, `config/sources_task08a.yaml`, `config/contract.yaml` và các tài liệu/source registry thuộc thiết kế hoặc Data Engineering. Giữ nguyên trong refactor Streamlit trừ khi một lần tài liệu riêng được duyệt; không được dùng occurrence từ khóa để xóa pipeline/contract DE.

## 6. Credential store và phương án migration không reset password

Kiểm tra chỉ-đọc qua `CredentialStore` hiện tại cho kết quả:

| Kiểm tra | Kết quả |
|---|---|
| Store theo `config/auth.yaml` tồn tại | Có |
| Store/schema đọc hợp lệ | Có |
| `admin_local` tồn tại | Có |
| Enabled | Có |
| Role legacy | `data_team` |
| Credential record hợp lệ, bao gồm định dạng Argon2id bắt buộc | Có |
| Tổng số account | 1 |

Password và password hash không được xuất, copy hay ghi vào báo cáo. Credential store không bị sửa.

### Migration đề xuất

1. Thêm `admin_username: admin_local` vào `config/auth.yaml`; normalize bằng cùng `normalize_username()` đang dùng trong identity service.
2. Giữ nguyên toàn bộ `data/auth/users.json`, đặc biệt `password_hash`, `password_changed_at`, `user_id`, `enabled` và trường legacy `role: data_team`.
3. Cho `UserRecord.from_mapping()` tiếp tục đọc schema v1 có `role`; coi role là metadata backward-compatible, không còn là input authorization.
4. Thay `AuthenticationService(valid_roles=...)` bằng allowlist một username admin. Sau password verification, chỉ record enabled có username normalized khớp config mới được tạo session. Tài khoản khác phải nhận cùng generic login failure.
5. Khi validate session, tiếp tục re-read store và kiểm `user_id`, username, enabled, `password_changed_at`; bỏ yêu cầu role thuộc policy và bỏ role-based permission decision. Logout/revocation/idle timeout/rate limiting giữ nguyên.
6. Tạo `require_admin()` làm guard duy nhất cho shell/page/reporting service. Guard phải dựa trên session token đã được server xác minh, không dựa vào username/role do browser gửi.
7. Không gọi `create_user`, `change-password`, migration script hoặc hàm `_atomic_write()` trong lúc refactor. Không cần migration dữ liệu để mật khẩu cũ tiếp tục dùng.
8. Test trên credential store tạm: copy record fixture có schema legacy `role: data_team`, xác nhận password cũ đăng nhập được, hash string không đổi, account khác bị từ chối, disable/password change làm session mất hiệu lực, logout/revocation/rate limit vẫn hoạt động.

Rủi ro cần khóa bằng test: nếu chỉ bỏ `RolePolicy` nhưng vẫn cho mọi record enabled đăng nhập, hệ thống sẽ không còn là single-admin. Username allowlist phải nằm ở authentication service/guard phía server, không chỉ ẩn navigation.

## 7. Ma trận KEEP / MODIFY / REMOVE

| Thành phần | Quyết định | Giai đoạn | Ghi chú |
|---|---|---|---|
| `src/` và toàn bộ DE pipeline | **KEEP** | Tất cả | Ngoài phạm vi refactor UI |
| `data/auth/users.json` và hash hiện tại | **KEEP** | R1 | Không rewrite/migrate/reset |
| Argon2id/password policy | **KEEP** | R1 | Giữ implementation đã test |
| Server-side session, idle timeout, revoke/logout | **KEEP** | R1 | Opaque token phía browser |
| Login rate limiting | **KEEP** | R1 | Account + browser-session scope |
| Login/logout UI | **KEEP** | R1/R2 | Chỉ đổi guard/allowlist |
| Default localhost `127.0.0.1` | **KEEP** | R4 | Không mở LAN trong R0–R3 |
| 8 dashboard pages v3.0 | **KEEP** | R2/R3 | Overview, Ops, Logistics, Demand, Pricing, Growth, Explorer, System |
| `PENDING_MODEL` và nguyên tắc không fake forecast | **KEEP** | R2/R3 | BT1–BT8 chưa sẵn |
| `app/services/identity.py` | **MODIFY** | R1 | Single configured username; giữ schema legacy |
| `app/auth.py` | **MODIFY** | R1 | `require_admin()`, bỏ RBAC/action helpers |
| `app/main.py` | **MODIFY** | R1/R2 | Không truyền/render role |
| `app/navigation.py` | **MODIFY** | R1/R2 | Bỏ policy filter rồi giảm 9→8 pages |
| `app/common.py` | **MODIFY** | R1/R2 | Bỏ roles loader/copy role; giữ UI primitives hữu ích |
| `config/auth.yaml` | **MODIFY** | R1 | Thêm `admin_username` |
| `scripts/create_user.py` | **MODIFY** | R1 | Giới hạn quản lý `admin_local`, không tạo business users |
| Auth/navigation tests | **MODIFY** | R1/R2 | Chuyển từ 7-role/9-page sang single-admin/8-page negative tests |
| `app/services/access.py` RBAC | **REMOVE** khỏi runtime | R1 | Xóa file chỉ sau khi hết import/reference |
| `config/roles.yaml` | **REMOVE** khỏi Streamlit | R1 | Có thể giữ file tạm đến khi audit consumer hoàn tất; không để runtime đọc |
| `app/views/entry.py` và `/nhap-du-lieu` | **REMOVE** | R2 | Không còn navigation/direct page registration |
| Upload/data entry/confirm write/Undo controls | **REMOVE** | R2 | Kể cả disabled placeholders |
| Init/refresh/pipeline/model execution controls | **REMOVE** | R2 | System page chỉ xem trạng thái |
| CRUD/write path từ Streamlit | **REMOVE/PROHIBIT** | R2–R4 | Có negative tests/static audit |
| Tài liệu 2.0 mô tả RBAC/UI write | **MODIFY** hoặc đánh dấu superseded | R1–R4 | Không xóa tài liệu DE contract ngoài phạm vi |

## 8. Thứ tự thay đổi đề xuất

1. **R1 tests trước:** thêm fixture legacy `admin_local/data_team`, test password/hash preservation, admin-only login, non-admin denial, session revalidation, logout và rate limit.
2. **R1 config:** thêm `admin_username` vào `config/auth.yaml`; validate thiếu/sai config theo deny-by-default.
3. **R1 identity:** bỏ `valid_roles` khỏi quyết định authentication/session; allowlist configured admin username, vẫn đọc record schema v1 không rewrite.
4. **R1 auth/access:** đưa `require_admin()` thành boundary duy nhất; bỏ `RolePolicy`, `AuthorizationService`, `can_read/write/undo/refresh/authorize` khỏi runtime.
5. **R1 shell/navigation tối thiểu:** `main.py` gọi admin guard; `navigation.py` không đọc `roles.yaml`. Chưa xóa page `entry` trong R1 để không trộn scope dashboard với auth.
6. **R1 CLI:** giới hạn các lệnh vào configured `admin_local`; không chạy CLI và không chạm credential thật trong test.
7. **R1 verification:** chạy targeted auth tests, full pytest, `pip check`; xác nhận credential hash/store và DB/raw fingerprints/metadata không đổi.
8. **R2 sau phê duyệt riêng:** bỏ `entry` route/file, role copy/sidebar, write/upload/undo/refresh/model buttons; cập nhật registry còn đúng 8 pages và negative tests.
9. **R3/R4 sau phê duyệt riêng:** chỉ-read DuckDB adapter/dashboard thật, rồi mới nghiệm thu LAN opt-in. Không sinh dữ liệu dự báo giả.

## 9. Baseline verification

Các lệnh an toàn đã chạy từ virtual environment hiện tại:

```text
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp_v3_r0_20261021
216 passed in 75.40s (0:01:15)

.\.venv\Scripts\python.exe -m pip check
No broken requirements found.
```

Test suite dùng database/CSV tạm dưới pytest `tmp_path`; không chạy init, migration, refresh hay pipeline trên database/raw CSV thật. R0 không mở LAN và không thực hiện commit/push.

## 10. Đề xuất R1 nhỏ nhất — chờ duyệt

R1 nhỏ nhất nên chỉ thay authorization boundary từ 7-role sang một configured admin, đồng thời giữ nguyên 9-page shell tạm thời. Phạm vi file dự kiến:

- `config/auth.yaml`
- `app/services/identity.py`
- `app/auth.py`
- `app/services/access.py` (retire/remove sau khi hết consumer)
- `app/main.py`
- `app/navigation.py` (chỉ bỏ role-policy dependency, chưa giảm page)
- `scripts/create_user.py`
- `tests/test_streamlit_s03_auth.py`
- các test scaffold liên quan trực tiếp `roles.yaml`
- tài liệu authentication tương ứng

Acceptance R1: password cũ của `admin_local` vẫn hoạt động; credential store/hash không đổi; chỉ `admin_local` đăng nhập được; anonymous và account khác bị từ chối; logout, revoke, timeout, disable và rate limiting vẫn xanh; Streamlit runtime không còn đọc `roles.yaml`; không có thay đổi database/raw CSV/LAN. Việc giảm 9→8 pages và loại bỏ các control UI thuộc R2, không triển khai trong cùng lần R1.

**Trạng thái:** R0 hoàn tất. Dừng tại đây để chờ phê duyệt R1.

## 11. Implementation update — R1–R5

R1–R5 được triển khai trong lần làm việc tiếp theo theo yêu cầu tổng hợp:

- Authentication allowlist `admin_local`; credential schema/hash hiện hữu được giữ nguyên.
- Runtime không còn `roles.yaml`, RolePolicy hoặc table-action RBAC.
- Navigation còn đúng 8 pages; Entry UI và các write/execution controls đã loại bỏ.
- Reporting adapter allowlist 5 marts, DuckDB read-only, schema introspection, filters,
  SQL aggregation và pagination; không arbitrary SQL hoặc fallback raw CSV.
- LAN vẫn localhost-default và opt-in `0.0.0.0:8501`; firewall là thao tác thủ công.
- Tài liệu 2.0 được đánh dấu superseded cho phần UI.

Kết quả kiểm thử/fingerprint cuối cùng được ghi trong handoff của lần triển khai R1–R5.

## 12. Final verification — 21/10/2026

- Full suite: `207 passed in 121.30s` (gồm regression cho lỗi DuckDB lúc runtime,
  nhãn navigation tiếng Việt và semantic accessibility của status/model states).
- Dependency integrity: `pip check` → `No broken requirements found.`
- Patch hygiene: `git diff --check` PASS; chỉ có cảnh báo Git về LF/CRLF trên các file
  đã tồn tại, không có whitespace error.
- Fingerprint SHA-256 trước/sau khớp byte-for-byte cho `data/auth/users.json`,
  `data/warehouse/rohlik.duckdb`, `data/warehouse/rohlik_bootstrap_dev.duckdb` và 7 raw CSV.
- Warehouse chính vẫn không có table/mart; refactor không tạo schema hoặc dữ liệu.
- LAN script/config được test tĩnh. Kiểm thử vật lý hai browser/device và firewall vẫn là
  `MANUAL_VERIFY`, chưa được tuyên bố hoàn tất.
- Review giao diện ở mức code không còn phát hiện P0/P1. Capture authenticated desktop/mobile,
  keyboard-only và browser DOM vẫn là `MANUAL_VERIFY` vì môi trường hiện tại không có browser
  automation và không sử dụng credential thật để tạo ảnh.
- Không commit/push, không reset password/account, không chạy migration/init/refresh.
