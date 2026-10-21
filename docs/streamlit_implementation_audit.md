# BÁO CÁO AUDIT TRIỂN KHAI STREAMLIT 2.0 (ROHLIK DECISION HUB)

> **SUPERSEDED FOR UI — 21/10/2026:** Các mục 7-role RBAC, 9 pages, CSV upload/write,
> Undo và refresh/model action trong tài liệu 2.0 này không còn là scope Streamlit.
> Runtime v3.0 là single-admin, 8-page, read-only. Phần DE evidence vẫn được giữ lịch sử.

**Ngày thực hiện:** 21/10/2026  
**Môi trường:** Windows 11 · PowerShell · Python 3.13.15 (`.venv`) · DuckDB 1.5.6 · Streamlit 1.66.0  
**Tài liệu đối chiếu:** `Xây dựng streamlit-2.0.md.md`, `Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md`, `docs/v4_03_landing_handover.md`  
**Mục tiêu kiểm tra:** Đánh giá hiện trạng kho dữ liệu, xác định ranh giới Data Engineering (DE) và Dashboard, thiết lập kế hoạch triển khai Streamlit 2.0 đa người dùng trên mạng LAN/Wi-Fi **khi chưa có 8 mô hình BT1–BT8**.

---

## 1. TỔNG QUAN HIỆN TRẠNG VÀ RÀNG BUỘC KIẾN TRÚC

### 1.1. Quyết định kiến trúc bắt buộc (Streamlit 2.0)
1. **Local-first DuckDB:** DuckDB local file (`data/warehouse/rohlik.duckdb`) là kho lưu trữ duy nhất. Tuyệt đối không dùng SQLite, MotherDuck hay Streamlit Community Cloud.
2. **Một máy host Windows chạy Streamlit:** Máy host đóng vai trò server phục vụ giao diện qua trình duyệt cho các máy trong mạng LAN (`http://<HOST_IPV4>:8501`). Không chia sẻ file `.duckdb` qua network drive / SMB.
3. **Điều phối ghi đơn tiến trình (Single-Process Writer Coordinator):** Vì DuckDB là cơ sở dữ liệu file (embedded), mọi kết nối ghi (CSV upload, confirm, undo, in-process refresh) từ các session người dùng phải được điều phối qua một Coordinator duy nhất trong cùng tiến trình Streamlit host. Không dùng CLI subprocess `python -m pipeline.run` từ giao diện web vì sẽ gây khóa file (DuckDB writer file lock conflict).
4. **Chưa cần 8 mô hình BT1–BT8 (Model-Free MVP):** Streamlit 2.0 được nghiệm thu theo 2 cổng:
   - **Gate A (UI-ONLY):** Khung ứng dụng, điều hướng 9 trang, đăng nhập 7 role (Argon2id), cấu hình LAN, download template & preview/validate CSV (không ghi DB). Nếu DB chưa có bảng hoặc chưa có model, hiển thị nhãn `WAREHOUSE_NOT_READY` hoặc `PENDING_MODEL`, **tuyệt đối không crash và không hiển thị số liệu dự báo giả**.
   - **Gate B (DATA-READY):** Hoạt động khi DE nạp 14 bảng landing và dựng `stg -> core -> mart`. Cho phép nạp CSV vào DuckDB với audit transaction, soft undo, và refresh dữ liệu lịch sử.

---

## 2. AUDIT GIT, NHÁNH VÀ MÔI TRƯỜNG PYTHON

### 2.1. Git & Branch
- **Nhánh hiện tại:** `feat/v4-03-landing-ingestion` (tracking `origin/feat/v4-03-landing-ingestion`).
- **Trạng thái Git:** Sạch đối với các file được quản lý (no modified tracked files).
- **File chưa theo dõi (Untracked):**
  - `Xây dựng streamlit-2.0.md.md` (Tài liệu đặc tả kiến trúc Streamlit 2.0).
- **Kiểm tra rò rỉ dữ liệu nhạy cảm / database trong Git:**
  - `git ls-files` đối với `.env`, `secrets.toml`, `data/raw`, `data/warehouse`, `*.duckdb`: **0 kết quả** (Hoàn toàn tuân thủ `.gitignore`).
  - Không có file CSV nào bị track trong Git.

### 2.2. Môi trường Python
- **Trình thông dịch:** Python 3.13.15 tại `c:\Users\win11\Documents\rohlik-data-warehouse\.venv\Scripts\python.exe`.
- **Thư viện chính đã cài đặt:**
  - `duckdb` == 1.5.6
  - `streamlit` == 1.66.0
  - `pydantic` == 2.14.1
  - `pytest` == 9.1.1
  - `pandas` == 3.0.6
  - `pyarrow` == 26.0.0
  - `pyyaml` == 6.0.3
  - `altair` == 6.3.0
- **Kiểm tra xung đột package (`pip check`):** **PASS** (`No broken requirements found.`).
- **Thư viện còn thiếu cho Streamlit 2.0:**
  - `argon2-cffi` (bắt buộc cho việc băm mật khẩu chuẩn bảo mật cao theo đặc tả S03, loại bỏ hoàn toàn SHA-256 trần và mật khẩu mặc định).
  - `plotly` (cho biểu đồ tương tác tại các trang Overview, Ops, EDA khi hiển thị dữ liệu lịch sử).

---

## 3. KIỂM KÊ MODULE VÀ THƯ MỤC TRONG REPOSITORY

| Thư mục / File | Trạng thái | Chi tiết nội dung và vai trò |
|---|---|---|
| `config/contract.yaml` | **EXISTING** | Định nghĩa chi tiết 14 bảng landing, business keys, kiểu dữ liệu DuckDB, kiểm tra min/max, mapping raw-to-canonical và 5 tên cột chuẩn hóa cho HR (`hourly_wage_eur`, `morning_shift_ratio`, `overtime_cap_ratio`, `shortage_penalty_multiplier`, `legacy_rule_buffer_ratio`). |
| `config/sources.yaml` | **EXISTING** | Khai báo 7 nguồn active (5 Kaggle + 2 giả định) kèm SHA-256, schema, row counts và 1 nguồn `orders_calendar` đánh dấu `HISTORICAL_ONLY`. |
| `config/settings.yaml` | **EXISTING** | Cấu hình đường dẫn warehouse `data/warehouse/rohlik.duckdb`, raw_dir `data/raw`, runner `local`. |
| `config/roles.yaml` | **EXISTING** | Đã tạo trong S01: Ánh xạ 7 vai trò người dùng UI (`executive`, `sales`, `demand_planning`, `warehouse_ops`, `logistics`, `marketing`, `data_team`) theo nguyên tắc deny-by-default, chỉ `data_team` có quyền refresh, các quyền write chưa chốt đánh dấu `PENDING_APPROVAL`. |
| `src/config/` | **EXISTING** | Chứa `source_registry.py` (load registry, contract, preflight checksums) và bản Task 08A. |
| `src/db/` | **EXISTING** | Chứa `duckdb.py` (cơ chế khóa OS `msvcrt/fcntl`, bounded wait, atomic transaction, chặn ghi vào dev DB), `duckdb_metadata.py` (quản lý schema `meta`), `sqlite.py` (legacy). |
| `src/ingestion/` | **EXISTING** | Chứa `landing.py` (bootstrap nạp 7 CSV vào 14 bảng landing kèm 4 cột truy vết `_batch_id`, `_source`, `_loaded_at`, `_entered_by`). |
| `src/models/` | **PARTIAL** | Chỉ có file `.gitkeep`. Đúng với hiện trạng chưa bàn giao 8 mô hình BT1–BT8. |
| `src/services/` | **MISSING** | Chỉ có file `.gitkeep`. Chưa có các service dùng chung cho backend Streamlit. |
| `rohlik/` | **MISSING** | Chưa tồn tại. Duy trì `src/` làm module DE duy nhất, không tạo package song song. |
| `app/` | **EXISTING** | Đã tạo trong S01: Khung scaffold Streamlit 2.0 (`app/main.py`, `app/common.py`, `app/auth.py`, `app/views/`, `app/services/`). Auth guard chặn mọi truy cập dữ liệu trước S03. |
| `app_smoke.py` | **EXISTING** | File smoke test cũ ở thư mục gốc (chứa kiểm tra SQLite và DuckDB). |
| `pipeline/` | **MISSING** | Thư mục `pipeline/` và file điều phối `pipeline/run.py` chưa được xây dựng. |
| `.streamlit/config.toml` | **EXISTING** | Đã cấu hình cho S01: `address = "127.0.0.1"`, `port = 8501`, `headless = true`, `maxUploadSize = 25`, `enableCORS = true`, `enableXsrfProtection = true`. Giữ localhost an toàn trước khi có auth S03. |
| `.streamlit/secrets.toml` | **MISSING** | Đang được gitignore đúng quy định; sẽ tạo khi triển khai auth S03. |
| `pytest.ini` | **EXISTING** | Đã tạo trong S01: Cấu hình `addopts = -p no:cacheprovider --basetemp=.pytest_tmp` và `testpaths = tests`. Thư mục `.pytest_tmp/` được gitignore, loại bỏ rủi ro xóa backup. |
| `tests/` | **EXISTING** | Có 9 file test (bổ sung `tests/test_streamlit_scaffold.py` kiểm tra imports, 7 roles, contract consistency, Streamlit AppTest). |

---

## 4. TÌNH TRẠNG DỮ LIỆU VÀ CÁC THÀNH PHẦN DATA ENGINEERING

### 4.1. Tình trạng 7 file CSV nguồn (`data/raw/`)
Chạy kiểm tra độc lập qua `src.validate_source_registry` trả về kết quả **VERIFIED_WITH_WARNINGS**:
1. `data/raw/orders/train.csv`: 7,340 dòng, SHA-256 khớp chuẩn Kaggle.
2. `data/raw/sales/sales_train.csv`: 4,007,419 dòng, SHA-256 khớp chuẩn Kaggle. Có 32 dòng vi phạm constraint mức nhẹ (27 dòng type_0_discount âm, 1 dòng type_4, 4 dòng type_6) — đây là dị biệt dữ liệu lịch sử Kaggle đã được ghi nhận trong DQ.
3. `data/raw/sales/inventory.csv`: 5,432 dòng, SHA-256 khớp.
4. `data/raw/sales/calendar.csv`: 23,016 dòng, SHA-256 khớp.
5. `data/raw/sales/test_weights.csv`: 5,390 dòng, SHA-256 khớp (là trọng số đánh giá Kaggle, không phải trọng lượng sản phẩm hay giá vốn).
6. `data/raw/assumptions/cost_params.csv`: 3 dòng, nguồn giả định (`ASSUMED`).
7. `data/raw/assumptions/workforce_params.csv`: 7 dòng (7 kho), nguồn giả định (`ASSUMED`).

### 4.2. Tình trạng DuckDB
- **Kho chính thức (`data/warehouse/rohlik.duckdb`):**
  - Kích thước: 12,288 bytes.
  - Số bảng: **0 bảng**. Chưa được nạp 14 bảng landing, chưa có metadata schema `meta`.
- **Kho thử nghiệm Task 08A (`data/warehouse/rohlik_bootstrap_dev.duckdb`):**
  - Kích thước: 122.7 MB.
  - Chứa 23 bảng theo schema cũ (`bronze`, `sales_ecommerce`, `marketing_pricing`, `warehouse_ops`, ...).
  - Đã được khóa bảo vệ cứng trong `src/db/duckdb.py` (`_ensure_writable_target`), không cho phép bất kỳ tiến trình nào ghi đè.

### 4.3. Các thành phần DE còn thiếu (Gây cản trở Gate B)
1. **14 bảng Landing trên kho thật:** Logic nạp đã có trong `src/ingestion/landing.py`, nhưng chưa được chạy nạp vào `data/warehouse/rohlik.duckdb`.
2. **Tầng Staging (`stg` - 14 bảng):** Chưa có SQL/service sinh bảng sạch và chọn phiên bản ACTIVE mới nhất từ landing.
3. **Tầng Core (`core` - 6 bảng):** Chưa có `fct_warehouse_day`, `fct_sku_day`, `dim_product`, `dim_warehouse`, `params_cost`, `params_workforce`.
4. **Tầng Marts (`mart` - 5 view):** Chưa có `sales_orders_day`, `ops_warehouse_day`, `category_sku_day`, `marketing_promo_day`, `exec_kpi_month`.
5. **In-process Refresh Service:** Chưa có hàm callable nội bộ để chạy `stg -> core -> mart -> DQ` trong cùng tiến trình máy chủ web.
6. **Entry Service & Soft Undo Service:** Chưa có logic xử lý preview token, transactional INSERT và gắn cờ `UNDONE` trong `meta.batch_status_events`.

---

## 5. THÀNH PHẦN STREAMLIT CÓ THỂ XÂY DỰNG NGAY (KHÔNG CẦN 8 MODEL)

Theo nguyên tắc **Gate A (UI-ONLY)**, các hạng mục sau hoàn toàn độc lập với 8 model và có thể xây dựng ngay lập tức:

1. **Khung ứng dụng đa trang (`app/main.py`):**
   - Sử dụng `st.navigation` và `st.Page` cho 9 trang nghiệp vụ.
   - Trạng thái trang linh hoạt: Hiển thị `WAREHOUSE_NOT_READY` khi bảng vắng mặt, `PENDING_MODEL` tại các khu vực dự báo của BT1–BT8 mà không gây traceback/crash.
2. **Hệ thống xác thực & Phân quyền (`app/auth.py` + `config/roles.yaml`):**
   - Quản lý phiên làm việc, tự động đăng xuất khi hết hạn.
   - Băm mật khẩu Argon2id qua `argon2-cffi`. Script tạo tài khoản `scripts/create_user.py` tương tác an toàn qua CLI (không hiển thị mật khẩu plaintext).
   - Kiểm tra quyền truy cập 7 role phía server.
3. **Cấu hình mạng LAN đa thiết bị:**
   - Giữ `.streamlit/config.toml` ở localhost `127.0.0.1:8501`; chế độ LAN explicit override sang `0.0.0.0:8501` bằng script, không làm LAN thành mặc định.
   - `enableCORS = true`, `enableXsrfProtection = true`, giới hạn upload `maxUploadSize = 25` tiếp tục được giữ nguyên.
   - Script khởi động `scripts/start_streamlit_lan.ps1` và runbook hướng dẫn mở Windows Firewall thủ công.
4. **Mô phỏng & Kiểm định CSV Template (`app/views/entry.py` - Tab Preview):**
   - Tải template CSV canonical chuẩn 14 bảng (đặc biệt bảng HR với 11 cột canonical).
   - Tiếp nhận file CSV, kiểm tra cấu trúc header, kiểu dữ liệu, ràng buộc min/max từ `config/contract.yaml`.
   - Báo cáo chi tiết lỗi theo từng hàng/cột mà **không tạo bất kỳ transaction ghi nào vào database** (0 side-effects). Nút "Xác nhận ghi" tự động disabled khi kho dữ liệu chưa sẵn sàng.
5. **Khám phá & EDA dữ liệu lịch sử (`app/views/explorer.py`):**
   - Thiết lập giao diện đọc dữ liệu an toàn theo template queries được phê duyệt (không cho gõ SQL tự do để chống SQL injection và khai thác đọc file DuckDB).

---

## 6. MA TRẬN TRẠNG THÁI CÁC THÀNH PHẦN THEO S00–S12

| Bước | Thành phần | Trạng thái | Ghi chú & Phụ thuộc |
|---|---|---|---|
| **S00** | Môi trường, Git, Audit report, Baseline tests | **EXISTING** | Hoàn thành. 170 test pass, audit report đã tạo. |
| **S01** | Dependency (`argon2-cffi`, `plotly`), `roles.yaml`, app skeleton, `pytest.ini`, smoke tests | **COMPLETED** | Hoàn thành: Đã cài `argon2-cffi 25.1.0`, `plotly 7.1.0`, tạo `config/roles.yaml` (7 roles deny-by-default), scaffold `app/` (main, common, auth stub, views, services), `pytest.ini` (`.pytest_tmp`), 177/177 tests PASS. |
| **S02** | Khung App 9 trang không crash, component trạng thái | **COMPLETED** | 9 view đã đăng ký bằng `st.navigation`/`st.Page`, URL ổn định, public-safe placeholders, trạng thái dùng chung và auth guard deny-by-default. |
| **S03** | Auth Argon2id, 7 roles, local credential store, session và CLI account | **COMPLETED** | Login-only anonymous boundary, server-side session/rate-limit, atomic credential CLI và backend authorization đã triển khai; business permissions vẫn `PENDING_APPROVAL`. |
| **S04** | Chế độ LAN `0.0.0.0`, run script, runbook Windows Firewall | **COMPLETED (AUTOMATED) / MANUAL_VERIFY** | Default vẫn là `127.0.0.1`; script LAN override `0.0.0.0:8501`. Test cấu hình/script đã tự động hóa; firewall và hai thiết bị thật chờ nghiệm thu thủ công. |
| **S05** | Catalog readiness service, Trang Tổng quan (Overview lịch sử) | **MISSING** | Đọc metadata kho thật; phụ thuộc vào dữ liệu kho để hiển thị số liệu thực tế. |
| **S06** | Trang Truy vấn & EDA lịch sử (`explorer.py`), Template SQL | **MISSING** | Khám phá dữ liệu qua allowlisted tables & query templates. |
| **S07** | Tải template CSV canonical, Upload & Preview/Validate (0 DB writes) | **MISSING** | Có thể làm ngay dựa trên `config/contract.yaml`. |
| **S08** | Direct DuckDB INSERT transaction + audit (`entry_log`, `batch_status`) | **BLOCKED** | Phụ thuộc vào việc khởi tạo 14 bảng landing trên `rohlik.duckdb`. |
| **S09** | Lịch sử lô & Soft undo (`UNDONE` events, không DELETE) | **BLOCKED** | Phụ thuộc S08 và tầng Staging xử lý loại trừ lô bị undo. |
| **S10** | DE In-process Refresh (`stg -> core -> mart -> DQ`), Trang Vận hành | **BLOCKED** | Phụ thuộc vào code transform DE V4 (hiện chưa có trong repository). |
| **S11** | Hoàn thiện 9 trang (Lịch sử + `PENDING_MODEL` badges) | **PARTIAL** | Có thể làm khung UI trước (Gate A), chỉ hiển thị số liệu khi đạt Gate B. |
| **S12** | Test tự động DB tạm + Nghiệm thu thực tế trên 2 thiết bị LAN | **MISSING** | Cần viết bộ test fixtures cho `app/` và checklist nghiệm thu E2E. |

---

## 7. KẾT QUẢ KIỂM THỬ BASELINE VÀ PHÁT HIỆN KỸ THUẬT

### 7.1. Kết quả thực thi Test
- **Baseline S00:** Chạy qua lệnh thủ công `-p no:cacheprovider --basetemp=data/backups/pytest_tmp -q`:
  - **170 PASSED / 170 (100% PASS)** trong 47.85 giây.
- **Sau hoàn thành S01:** Chạy chuẩn hóa qua lệnh `pytest -q` (tự động đọc `pytest.ini`):
  - **177 PASSED / 177 (100% PASS)** trong 75.93 giây.
  - Bổ sung `tests/test_streamlit_scaffold.py` (7 tests, 100% PASS):
    - `test_app_imports_cleanly`: PASS
    - `test_common_datastatus_enum`: PASS
    - `test_common_config_loaders`: PASS
    - `test_roles_yaml_structure_and_roles_count`: PASS
    - `test_roles_deny_by_default_principles`: PASS
    - `test_roles_tables_match_contract`: PASS
    - `test_streamlit_scaffold_executes_safely_with_apptest`: PASS
  - 0 test regressions, 0 warnings.

### 7.2. Vấn đề kỹ thuật trên Windows đã phát hiện và xử lý
- **Lỗi PermissionError [WinError 5] khi chạy pytest mặc định:**
  - *Hiện tượng:* Khi chạy `pytest -q` mặc định, pytest cố gắng tạo thư mục tạm trong `C:\Users\win11\AppData\Local\Temp\pytest-of-win11` và ghi cache vào `.pytest_cache\v\cache\nodeids`, dẫn đến 152 lỗi `PermissionError: [WinError 5] Access is denied`.
  - *Giải pháp triệt để trong S01:*
    1. Tạo file `pytest.ini` tại thư mục gốc:
       ```ini
       [pytest]
       addopts = -p no:cacheprovider --basetemp=.pytest_tmp
       testpaths = tests
       ```
    2. **Quyết định an toàn dữ liệu:** Tuyệt đối **không** dùng `data/backups/` làm basetemp mặc định vì pytest sẽ tự động xóa sạch (purge) nội dung thư mục basetemp khi khởi động mỗi phiên test, có thể phá hủy các bản sao lưu database thật.
    3. Thư mục `.pytest_tmp/` được đặt ở root dự án và thêm vào `.gitignore` để cách ly hoàn toàn khỏi Git và kho dữ liệu.
    4. Giờ đây dev/CI chỉ cần gõ `pytest -q` là toàn bộ test suite chạy mượt mà trên Windows.

---

## 8. KẾT LUẬN VÀ TRẠNG THÁI TRIỂN KHAI

### 8.1. Trạng thái sau Bước S01 — Foundation (ĐÃ HOÀN THÀNH)
1. **Dependencies:** Đã cài đặt `argon2-cffi 25.1.0` và `plotly 7.1.0`. `requirements.txt` đã được cập nhật và kiểm tra `pip check` PASS 100%.
2. **Cấu trúc Scaffold `app/`:**
   - `app/main.py`: Điểm khởi chạy Streamlit 2.0 hiển thị sidebar thông tin môi trường, trạng thái kho dữ liệu `WAREHOUSE_NOT_READY` và auth guard.
   - `app/common.py`: Loaders an toàn cho `settings.yaml`, `roles.yaml`, `contract.yaml` và enum `DataStatus`.
   - `app/auth.py`: Auth stub chặn mọi truy cập dữ liệu trước khi có S03 (an toàn tuyệt đối cho Gate A).
   - `app/views/` và `app/services/`: Khởi tạo sẵn sàng cho các trang nghiệp vụ S02.
3. **Phân quyền UI (`config/roles.yaml`):**
   - Định nghĩa đủ 7 vai trò người dùng UI: `executive`, `sales`, `demand_planning`, `warehouse_ops`, `logistics`, `marketing`, `data_team`.
   - Tuân thủ nghiêm ngặt nguyên tắc **deny-by-default**: Chỉ `data_team` được cấp quyền `refresh` và full write; các vai trò khác ở chế độ chỉ đọc hoặc ghi giới hạn theo nghiệp vụ. Các quyền chưa phê duyệt được gắn cờ `PENDING_APPROVAL`.
4. **Streamlit Local Config (`.streamlit/config.toml`):**
   - Cấu hình chạy an toàn trên `address = "127.0.0.1"` và `port = 8501`.
   - Bật `headless = true`, `maxUploadSize = 25`, `enableCORS = true`, `enableXsrfProtection = true`.
   - Giữ nguyên localhost trong S01; chỉ mở LAN `0.0.0.0` sau khi hoàn tất xác thực Argon2id ở S03.
5. **An toàn dữ liệu tuyệt đối:**
   - Kho `data/warehouse/rohlik.duckdb` giữ nguyên trạng (12,288 bytes, 0 writes).
   - 7 file CSV raw (`data/raw/`) không bị chỉnh sửa.
   - Không có file nhạy cảm, secrets hay db nào bị track vào Git.
6. **Kiểm thử tự động:**
   - Đạt 177/177 tests PASS (100%), không có regression, không có warning.

### 8.2. Trạng thái sau Bước S02 — Khung giao diện 9 trang (ĐÃ HOÀN THÀNH)

1. **Navigation:** `app/main.py` dùng `st.navigation` và `st.Page`; registry tập trung tại `app/navigation.py`. Chín URL ổn định là `tong-quan`, `nhan-su-kho`, `tai-xe`, `nhu-cau-dat-hang`, `khuyen-mai`, `tang-truong`, `truy-van-eda`, `nhap-du-lieu`, `van-hanh-he-thong`.
2. **UI dùng chung:** `app/common.py` cung cấp shell dark theme, page heading, readiness banner, feature rows, disabled actions và 6 trạng thái chuẩn: `WAREHOUSE_NOT_READY`, `TABLE_NOT_AVAILABLE`, `DATA_READY`, `PENDING_MODEL`, `DQ_FAILED`, `REFRESH_REQUIRED`.
3. **Ranh giới bảo mật:** Mỗi view chỉ hiển thị mô tả công khai rồi gọi auth guard deny-by-default. Không view nào kết nối DuckDB, đọc raw CSV, import pipeline/model hoặc gọi service nghiệp vụ. Explorer, Entry và System chỉ có control disabled.
4. **Model-free:** Các vùng BT1–BT8 đều mang trạng thái `PENDING_MODEL`; không có KPI, forecast hoặc dữ liệu demo.
5. **Local-only:** `.streamlit/config.toml` vẫn giữ `127.0.0.1`, CORS và XSRF protection; chưa mở LAN.
6. **Kiểm thử S02:** Bổ sung `tests/test_streamlit_s02.py` để kiểm tra imports, registry/navigation, URL, empty-warehouse render, auth guard, disabled sensitive actions và không import data/model/pipeline backend. Full suite sau S02: **193/193 PASSED** trong 113.09 giây với `--basetemp=.pytest_tmp_s02_full_20261021` (thư mục `.pytest_tmp` mặc định bị Windows khóa như sự cố đã ghi nhận ở mục 7.2).

### 8.3. Thành phần còn chờ sau S02

- **S03:** Đã hoàn thành authentication/session/backend authorization. `config/roles.yaml` vẫn `PENDING_APPROVAL`, nên quyền bảng nghiệp vụ tiếp tục bị chặn.
- **S05:** Catalog/readiness service và KPI lịch sử từ dữ liệu đã xác thực.
- **S06:** Allowlisted EDA/query service; hiện không chạy truy vấn.
- **S07–S09:** CSV template, preview/validate, confirm transaction, audit và soft undo; hiện không nhận upload và không ghi DB.
- **S10:** DQ, lineage, run history và in-process refresh; mọi action hệ thống hiện bị khóa.
- **S11:** Ghép dữ liệu lịch sử và output BT1–BT8 sau handoff; mọi vùng model vẫn `PENDING_MODEL`.

### 8.4. Lệnh chạy và checklist nghiệm thu thủ công S02

Chạy tại root repository:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py `
  --server.address 127.0.0.1 --server.port 8501
```

Mở `http://127.0.0.1:8501`, sau đó kiểm tra:

- Sidebar hiển thị Rohlik Decision Hub, nhãn `LOCAL`, trạng thái `WAREHOUSE_NOT_READY` và đủ 3 nhóm menu.
- Cả 9 trang mở được bằng menu; refresh từng URL không lỗi hoặc đổi path.
- Anonymous chỉ thấy màn hình login; sau xác thực, mỗi trang có heading, mô tả và readiness state.
- Ops, Logistics, Demand, Pricing và Growth hiển thị đúng các vùng `PENDING_MODEL` liên quan BT1–BT8, không có số giả.
- Explorer không có SQL input hoạt động; nút chạy/xuất bị disabled.
- Entry không nhận file; preview/confirm bị disabled.
- System không cho init, refresh hoặc chạy model.
- Trên cửa sổ hẹp, các hàng chức năng xếp thành một cột, không tràn ngang.
- Dừng server bằng `Ctrl+C`; xác nhận không có file raw hoặc DuckDB nào thay đổi.

### 8.5. Trạng thái sau Bước S03 — Authentication & Authorization (ĐÃ HOÀN THÀNH)

1. **Credential store tách biệt:** `data/auth/users.json`, Git-ignored, không dùng
   DuckDB. Không có default admin/demo account. Password chỉ lưu dưới dạng
   Argon2id hash.
2. **Account CLI:** `scripts/create_user.py` hỗ trợ create, change-password,
   disable và list. Password nhập bằng `getpass`; JSON được ghi atomic và CLI
   harden Windows ACL.
3. **Anonymous boundary:** `app/main.py` yêu cầu xác thực trước khi tạo navigation;
   từng view cũng gọi guard ở đầu nên direct page render không lộ placeholder.
4. **Server-side session:** Browser session chỉ giữ opaque token. Identity, role,
   idle timeout, rate-limit và revoke state nằm trong resource dùng chung có lock.
   Account/role được kiểm tra lại trên mỗi rerun.
5. **Authorization:** `AuthorizationService` luôn phân giải token về identity phía
   server trước khi gọi `can_read`, `can_write`, `can_undo`, `can_refresh` hoặc
   `authorize`. Role gửi/giả mạo từ browser không được sử dụng.
6. **Pending policy:** Vì `roles.yaml.status=PENDING_APPROVAL`, mọi table read/write/
   undo đều deny. Chỉ policy `data_team.refresh` được nhận diện; S03 không chạy
   refresh thực tế.
7. **Cấu hình:** Idle timeout 30 phút; giới hạn theo account và browser session
   là 5/8 lần sai trong 15 phút, khóa 15 phút. Tất cả nằm trong `config/auth.yaml`.
8. **Runbook:** Xem `docs/authentication_runbook.md` để tạo account, login/logout,
   kiểm tra permissions/ACL và giới hạn trước LAN.
9. **Kiểm thử sau S03:** Full suite **211/211 PASSED** trong 75.84 giây;
   `pip check` trả về `No broken requirements found`. Hai file DuckDB chính thức
   giữ nguyên hash trước/sau kiểm thử.

### 8.6. Thành phần còn chờ sau S03

- **S04:** Chưa mở LAN. Vẫn bind `127.0.0.1`; cần HTTPS hoặc tunnel bảo mật cho
  dữ liệu thật vì HTTP LAN không mã hóa credential khi truyền.
- **Policy approval:** Business/DE phải phê duyệt matrix trong `config/roles.yaml`
  trước khi cho phép table read/write/undo.
- **S05–S11:** Catalog, data services, CSV flow, refresh/DQ và model integration
  vẫn chưa triển khai; S03 không gọi database, pipeline hoặc model.

### 8.7. Trạng thái sau Bước S04 — Local Wi-Fi/LAN Access (ĐÃ HOÀN THÀNH PHẦN CODE)

1. **Hai chế độ khởi động tách biệt:** `.streamlit/config.toml` tiếp tục bind
   `127.0.0.1:8501`. `scripts/start_streamlit_lan.ps1` mới override bằng CLI sang
   `0.0.0.0:8501`; LAN không trở thành mặc định.
2. **Một host process:** Script kiểm tra repository, Python `.venv`, entry point và
   listener TCP 8501 rồi chạy đúng một Streamlit process foreground. Nếu port bận,
   script báo PID và dừng; không kill process, không chạy Administrator và không tạo
   worker nền.
3. **Bảo mật giữ nguyên:** Không sửa auth S03. Argon2id, opaque server-side sessions,
   rate limiting, revalidation account/role, CORS và XSRF protection vẫn hoạt động.
   Không có guest/demo bypass hoặc secret trong script.
4. **Firewall có giới hạn:** `docs/streamlit_local_lan_runbook.md` cung cấp lệnh thủ
   công cho inbound TCP 8501 với `Profile=Private` và `RemoteAddress=LocalSubnet`,
   cùng lệnh disable sau demo. Script không sửa firewall hoặc Network Profile.
5. **Ranh giới dữ liệu/mô hình:** S04 không thêm DB connection, CSV writing, Undo,
   Refresh, init, model call, background model worker hoặc network share cho DuckDB.
   Client chỉ dùng browser và không mở file DuckDB trực tiếp.
6. **HTTP LAN:** Traffic không được mã hóa. Chỉ cho phép demo trên LAN tin cậy bằng
   account/data thử nghiệm; dữ liệu thật yêu cầu HTTPS qua reverse proxy nội bộ hoặc
   VPN/tunnel được quản trị phê duyệt. Không port forwarding ra Internet.
7. **Nghiệm thu vật lý:** Firewall host thật, IPv4/routing và hai browser/device với
   session độc lập được đánh dấu `MANUAL_VERIFY`; chưa có tuyên bố đã kiểm thử vật lý.

### 8.8. Bằng chứng kiểm thử S04

- Test mới `tests/test_streamlit_s04_lan.py` kiểm tra default localhost, CORS/XSRF,
  LAN override, preflight port/repo/venv, đúng một lệnh chạy Streamlit, không nâng
  quyền hoặc tự sửa firewall, và nội dung bắt buộc của runbook.
- Runbook nghiệm thu: `docs/streamlit_local_lan_runbook.md`.
- Full suite cuối: **216/216 PASSED** trong 127.54 giây bằng
  `--basetemp=.pytest_tmp_s04_final_20261021`; `pip check` trả về
  `No broken requirements found`.
- Lần chạy mặc định trước đó không phải kết quả hợp lệ vì `.pytest_tmp` cũ bị Windows
  khóa (`WinError 5`), đúng sự cố basetemp đã ghi ở mục 7.2. Chạy lại với basetemp
  S04 tách biệt đã loại bỏ lỗi môi trường này.
- Kiểm tra SHA-256 trước/sau xác nhận 10 file được bảo vệ không đổi: hai DuckDB, một
  SQLite và bảy raw CSV chính thức. Test S04 cũng kiểm tra script không gọi DB/init/
  ingest/refresh/model.
- Khi full suite làm lộ lỗi ACL có thật ở credential-store boundary, `_load_document`
  được vá tối thiểu để chuyển `PermissionError`/`OSError` thành `CredentialStoreError`;
  login trả lỗi chung thay vì crash. Một regression test được bổ sung; không thay đổi
  Argon2id, session, rate limiting hoặc authorization.
- Các bước vật lý vẫn phải giữ nhãn `MANUAL_VERIFY`.
- S04 dừng tại đây; không bắt đầu S05.
