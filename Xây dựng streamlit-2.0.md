# XÂY DỰNG STREAMLIT 2.0 — ROHLIK DECISION HUB

> **SUPERSEDED — 21/10/2026:** Phần UI/authentication trong tài liệu này đã được
> Streamlit v3.0 thay thế bằng single-admin, dashboard-only và read-only. Không triển khai
> 7-role RBAC, CSV Upload, Data Entry, Undo, CRUD hoặc pipeline/model execution từ UI.
> Nội dung Data Engineering chỉ còn giá trị tham khảo và không bị xóa bởi refactor này.
## Hướng dẫn step-by-step: Local-first, Wi-Fi/LAN, Data Engineering first, chưa cần 8 model

**Phiên bản:** 2.0 · **Ngày:** 21/10/2026  
**Phạm vi:** Streamlit UI + các điểm kết nối Data Engineering (DE) trên **một máy host Windows**, cho nhiều người dùng trên cùng mạng LAN qua trình duyệt.  
**Tài liệu đối chiếu:** `Xây dựng streamlit.md` (PHẦN III, D1–D7) và `Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.docx` (Phần I).  
**Trạng thái tài liệu:** kế hoạch triển khai và checklist nghiệm thu; **không khẳng định các module/lệnh chưa kiểm chứng đã có trong repository**.

> **QUYẾT ĐỊNH PHIÊN BẢN 2.0**
>
> 1. **Không dùng Streamlit Community Cloud, MotherDuck, GitHub Actions hoặc SQLite** trong giai đoạn này.
> 2. Một máy host chạy **Streamlit + backend Python + DuckDB local**. Laptop/điện thoại khác kết nối bằng `http://<HOST_IPV4>:8501` qua cùng Wi-Fi/LAN, **không truy cập file `.duckdb` trực tiếp**.
> 3. **Không cần 8 model, không cần 8 STUB, không cần `pred.*`** để nghiệm thu Streamlit MVP. Các khối phụ thuộc model ở trạng thái `PENDING_MODEL`, không hiển thị kết quả giả.
> 4. Streamlit thao tác thông qua các service DE chung (`entry`, `quality`, `transform`, `db`, `security`), không tạo cơ sở dữ liệu/luồng nhập liệu riêng.
> 5. Nhập liệu chính: **tải CSV template → upload → preview/validate → confirm → INSERT landing + audit cùng DuckDB transaction → refresh**. Undo mềm, giữ lịch sử.
> 6. Cần **một đầu mối điều phối ghi** trên máy host vì DuckDB là database dạng file, không phải database server nhiều tiến trình ghi đồng thời.
> 7. **Codex làm phần lập trình, kiểm thử, tài liệu và lệnh trên workspace. Người dùng thao tác Windows/Router/Firewall và kiểm thử thiết bị thật.**
>
> **Ranh giới nghiệm thu:** `STREAMLIT_MVP_READY` khác `DE_FULL_V4_READY`. DE V4 hoàn chỉnh có tiêu chí STUB/model riêng; không dùng sự chưa hoàn thành của 8 model để chặn màn hình nhập liệu.

---

# 0. Đọc trước khi triển khai

## 0.1. Hiện trạng và điều kiện phải kiểm tra

Theo tài liệu DE, repository mục tiêu là `rohlik-data-warehouse`, môi trường ưu tiên **Windows + PowerShell + VS Code + `.venv` Python 3.13 + DuckDB + DBeaver**. Task 08A có thể đã có `src/`, Source Registry, profiling, DQ ban đầu và database thử nghiệm `rohlik_bootstrap_dev.duckdb`; **đây không phải bằng chứng** rằng `pipeline/run.py`, 14 bảng landing chính thức và các service dashboard đã tồn tại.

**Không được Codex tự suy đoán trạng thái.** Trước khi sửa code, phải rà:
- `git status`, `requirements.txt`, cấu trúc `src/`, `rohlik/`, `app/`, `config/`, `pipeline/`, `tests/`;
- vị trí DB thật, CSV nguồn, `.gitignore`, script setup, các bài test hiện có;
- module có thật hay mới là interface trong tài liệu; lưu một báo cáo gap `docs/streamlit_implementation_audit.md`;
- tránh tạo hai chức năng song song giữa `src/` và `rohlik/`; không di chuyển code đang chạy chỉ để khớp tên V4.

**Cảnh báo dữ liệu:** không reset, không `CREATE OR REPLACE` 14 bảng landing đã nhận upload, không thay `rohlik_bootstrap_dev.duckdb` bằng DB chính thức, không commit dữ liệu gốc/DB/secrets. Mọi test có ghi dữ liệu phải dùng DB tạm/fixture hoặc một bản sao được tạo an toàn.

## 0.2. Có thể làm đến đâu trước 8 model?

| Hạng mục | Làm ngay không cần model? | Phụ thuộc thực sự |
|---|---|---|
| Khung app, routing, theme, trạng thái các trang | **Có** | Python, Streamlit |
| LAN: máy host phục vụ trình duyệt khác | **Có** | IP LAN, firewall, mạng cho phép thiết bị kết nối |
| Đăng nhập, role, menu | **Có** | `roles.yaml`, auth service/tài khoản |
| Xem Source Registry, 14 bảng landing, DQ | **Có** | bảng DE tương ứng đã tồn tại |
| Tổng quan lịch sử, 5 `mart.*`, EDA lịch sử | **Có** | `stg/core/mart` và query service |
| Download template, upload CSV, validate | **Có** | `contract.yaml`, DE entry validator; DB không bắt buộc cho preview |
| Confirm INSERT, audit, soft undo | **Có** | 14 bảng `src_*`, `meta.*`, writer coordinator |
| `refresh` stg/core/mart/DQ | **Có** | DE orchestrator/transform thực thi được |
| Frames / output contract readiness | **Có** | hợp đồng; **không chạy training** |
| 8 trang mô hình/kết quả forecast | **Khung, trạng thái chờ, UI test được** | kết quả FINAL/STUB đã được xác minh nếu cần số liệu |
| Backtest, forecast P50/P90, staffing, replenishment, markdown recommendations | **Chưa** | BT1–BT8/outputs đã xác nhận |

**Thứ tự ưu tiên:** `auth + LAN` → `DE overview/EDA` → `CSV preview` → `transaction/undo` → `refresh & DQ` → `model integration sau`.

## 0.3. Một LAN app không có nghĩa DuckDB là LAN database

```text
Laptop A (Browser) -----\
Laptop B (Browser) ------>  Wi-Fi/LAN --> Windows HOST:8501
Điện thoại (Browser) ---/                    |
                                   Streamlit server (1 process)
                                             |
                                    Auth + role + service API
                                             |
                                 Application write coordinator
                                             |
                                     DuckDB local file
                                data/warehouse/rohlik.duckdb
                                             |
                                 src_* -> stg -> core -> mart
                                             |
                                  pred.* [CHƯA CÓ MODEL]
```

- Máy khách **không cài Python, Codex, DuckDB hay Streamlit**; chỉ cần trình duyệt.
- File `.duckdb` chỉ ở đĩa máy host. Không dùng network share/SMB để nhiều máy cùng mở DuckDB.
- Trong MVP, chỉ chạy **một Streamlit server process**, xử lý các phiên sử dụng từ nhiều trình duyệt.
- Các lần write/refresh đi qua **cùng coordinator và transaction**, không để code từ các trang tự tạo nhiều writer độc lập.
- **Cực kỳ quan trọng:** nếu Streamlit đang duy trì kết nối ghi đến DuckDB, một lệnh `python -m pipeline.run refresh` được mở ở **process khác** có thể không lấy được lock DuckDB, dù đã có file lock ngoài. Bản 2.0 **không đặt subprocess CLI làm đường chạy chuẩn từ dashboard**. Giải pháp MVP: gọi service refresh trong **cùng server process** và điều phối độc quyền; nếu cần chạy CLI/DBeaver writer độc lập, chuyển sang **maintenance mode, đóng kết nối rồi dừng server**, mới chạy CLI.
- DuckDB cho phép nhiều connection/threads trong một process theo cơ chế phù hợp; tuy nhiên phải tránh chia sẻ bừa một `duckdb.Connection` giữa các session. Service cấp connection cho từng tác vụ, đóng sau khi dùng và kiểm soát thay đổi DDL/transaction.
- Backup bằng cơ chế an toàn khi không còn ghi; tránh copy nóng file đang có writer.

## 0.4. Source of truth từ DE — tuyệt đối không đổi tự tiện

**7 nguồn vật lý:** 5 CSV Kaggle gốc + 2 CSV giả định.

```text
data/raw/orders/train.csv
data/raw/sales/sales_train.csv
data/raw/sales/inventory.csv
data/raw/sales/calendar.csv
data/raw/sales/test_weights.csv
data/raw/assumptions/cost_params.csv
data/raw/assumptions/workforce_params.csv
```

`orders/train_calendar.csv` thuộc lịch sử Task 08A, **không active/downstream** ở V4.

**14 bảng landing thuộc 9 schema (không tạo bảng thứ 15):**

| Schema | Bảng |
|---|---|
| `src_sales` | `orders_daily`, `sku_sales_daily` |
| `src_marketing` | `prices`, `promotions`, `mov_changes` |
| `src_ops` | `availability`, `ops_events` |
| `src_category` | `product_master` |
| `src_planning` | `calendar` |
| `src_digital` | `user_activity` |
| `src_external` | `weather` |
| `src_finance` | `sku_weights`, `cost_params` |
| `src_hr` | `workforce_params` |

DE downstream: **14 `stg` → 6 `core` → 5 `mart`**:
`mart.sales_orders_day`, `mart.ops_warehouse_day`, `mart.category_sku_day`, `mart.marketing_promo_day`, `mart.exec_kpi_month`.

**HR:** File raw có 11 cột, backend/template canonical dùng 5 đổi tên:
`wage_eur_per_hour → hourly_wage_eur`,
`morning_share → morning_shift_ratio`,
`overtime_cap → overtime_cap_ratio`,
`shortage_penalty → shortage_penalty_multiplier`,
`rule_buffer → legacy_rule_buffer_ratio`.
Các tham số HR 7 kho và cost 3 nhóm hàng là **ASSUMED**, không trình bày như quan sát thực tế. `test_weights` là trọng số đánh giá, **không phải kg/giá vốn**.

**Giai đoạn tương lai**: 8 BT, 14 bảng `pred` nghiệp vụ + 2 bảng history (`fc_orders_hist`, `fc_sku_hist`) theo hợp đồng khi đã chốt; **không tạo dữ liệu giả làm dự báo thật**.

---

# 1. Phân công: Codex làm gì, bạn tự làm gì?

| Công việc | Codex (trong repo/workspace) | Bạn (máy thật) |
|---|---|---|
| Audit repo, lập gap report | **Làm** | Mở đúng repo, đọc và duyệt báo cáo |
| Cấu trúc app, trang, UI, Python code | **Làm** | Chạy app và nhận xét UX |
| Dependency, config, `.gitignore`, tests | **Làm** | Cho phép cài gói/chạy lệnh khi cần |
| Data contracts và kết nối service DE | **Làm**, nếu code DE đã có; thiếu thì báo dependency | Xác nhận rule/key/role; tránh lệch DE |
| CSV validator, audit, undo, refresh | **Làm code + test DB tạm** | Nghiệm thu trên DB có kiểm soát |
| Cấu hình Streamlit listen LAN | **Làm file config** | Khởi chạy máy host và lấy địa chỉ IPv4 |
| Windows Firewall/network profile/router | Chỉ **hướng dẫn lệnh** | **Tự thực hiện với quyền admin** |
| Tạo tài khoản, đặt mật khẩu thật | Tạo công cụ + chỉ dẫn | **Tự nhập mật khẩu**, không gửi Codex/chat |
| Kiểm thử đa thiết bị cùng Wi-Fi | Viết checklist | **Tự chạy thật** với 2 thiết bị |
| Model training & prediction | Chưa nằm trong scope MVP | Chờ handoff BT1–BT8 |

**Định nghĩa Codex xong việc:** code thay đổi đã được kiểm thử, không làm hỏng chức năng DE hiện tại, có danh sách file sửa, lệnh chạy, test results và điểm đang chờ. Không chấp nhận câu “đã xong” chỉ vì Codex tạo file.

---

# 2. Roadmap triển khai: 2 cổng nghiệm thu

**Gate A — UI-ONLY (chưa có kho chính thức):**
- Streamlit chạy localhost và LAN; login/role hoạt động;
- trang dữ liệu hiển thị `WAREHOUSE_NOT_READY`/`TABLE_NOT_AVAILABLE`, **không crash**;
- download template/validate CSV bằng contract đã có, chưa INSERT khi kho chưa sẵn sàng;
- các khu vực model hiển thị `PENDING_MODEL`.

**Gate B — DATA-READY (không cần 8 model):**
- DE nạp 7 CSV vào 14 landing và build `stg/core/mart`;
- overview/EDA có dữ liệu lịch sử và phân quyền;
- CSV confirm ghi trực tiếp DuckDB, audit, undo, refresh, DQ chạy thật;
- 2 máy khách cùng LAN truy cập, cùng đăng nhập bằng 2 tài khoản, ghi có điều phối;
- tests pass và không overwrite dữ liệu khi init lại.

**Không lấy Gate B làm điều kiện để bắt đầu Gate A.** Những bước phụ thuộc DE sẽ được triển khai interface và test với DB tạm, sau đó kiểm thử tích hợp.

---

# 3. Các bước thực hiện — mỗi bước có Codex prompt, thao tác của bạn và điều kiện đạt

## Bước S00 — Mở đúng repository và kiểm tra trạng thái (BẠN + CODEX)

**Bạn thực hiện trên Windows PowerShell tại thư mục repo:**

```powershell
pwd
git status --short
git branch --show-current
.\.venv\Scripts\python.exe --version
```

Nếu `.venv` **chưa tồn tại** (không chạy lại để ghi đè nếu đã có):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

Nếu đã có `requirements.txt`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

**Prompt Codex — dùng ngay:**

```text
Bạn đang ở repository hiện tại của Rohlik Decision Hub. Mục tiêu: chuẩn bị
Streamlit local + LAN, chưa có 8 model. Trước khi viết code, hãy:
1. Audit repo, branch, git status, dependencies, app/, src/, rohlik/,
   config/, pipeline/, tests/ và đường dẫn DuckDB thật.
2. Kiểm tra tồn tại và API thực tế của contract.yaml, roles.yaml,
   rohlik/de/entry.py, db.py, transform.py, quality.py, pipeline.run;
   phân biệt EXISTING / PARTIAL / MISSING / BLOCKED.
3. Viết docs/streamlit_implementation_audit.md: hiện trạng, gap, reuse,
   tasks theo thứ tự, rủi ro DuckDB multiprocess và DB safety.
4. Chỉ audit, KHÔNG reset/migrate DB, KHÔNG chạy init/models,
   KHÔNG sửa raw CSV hoặc code chính khi chưa xong báo cáo.
5. Báo rõ kết quả tests baseline và vấn đề tồn tại trước chỉnh sửa.
Đối chiếu tài liệu Streamlit 2.0 và DE V4, không giả định code trong tài liệu
đã tồn tại trong repo.
```

**Đạt khi:** có gap report và biết chính xác sẽ reuse module DE nào. Nếu project có thay đổi chưa commit, Codex không xóa/đè.

## Bước S01 — Chốt dependency, config, cấu trúc app (CODEX)

Đề xuất **cấu trúc logic** (điều chỉnh linh hoạt theo repo thực tế; không bắt buộc tạo package trùng):

```text
app/
  main.py
  common.py                  # adapter cho UI, không chứa SQL write
  views/
    overview.py              # lịch sử + DQ, chưa cần pred
    ops.py                   # phần lịch sử; forecast pending
    logistics.py             # pending model nếu chưa có data độc lập
    demand.py                # historical SKU; replenishment pending
    pricing.py               # historical discounts; BT5/BT7 pending
    growth.py                # historical monthly KPI; projection pending
    explorer.py              # filtered tables, EDA + approved queries
    entry.py                 # upload flow, batch history, undo
    system.py                # source/DQ/runs, refresh
  services/
    access.py                # role / queries allowlisted
    coordinator.py           # lock + connection per task + maintenance
    catalog.py               # check table existence / status
    refresh.py               # invoke DE refresh IN PROCESS
  auth.py                    # argon2 verify, rate-limit, sessions
config/
  settings.yaml              # data/warehouse/rohlik.duckdb
  contract.yaml              # DE owns
  roles.yaml                 # DE owns
.streamlit/
  config.toml                # tracked, no secrets
  secrets.toml               # PRIVATE, gitignored
tests/
  test_streamlit_*           # unit/integration temporary DB
docs/
  streamlit_implementation_audit.md
  streamlit_local_lan_runbook.md
```

**Nguyên tắc module:** `app/services/` chỉ làm **adapter** nếu DE đã có implementation phù hợp; logic validate/append/undo/refresh **không được duplicate** bản thứ hai chỉ để phục vụ UI.

**Các dependency có thể cần:** `streamlit`, `duckdb`, `pandas`, `plotly`, `pyyaml`, `argon2-cffi`, `pytest`; không cài toàn bộ ML packages chỉ để chạy UI. Cho Codex pin phiên bản **đã kiểm thử với Python 3.13** vào requirements (hoặc file requirement UI độc lập phù hợp cách quản trị repo).

**Prompt Codex:**

```text
Triển khai S01 trong repository hiện hành. Reuse hạ tầng DE đang có; bổ sung
Streamlit local-only cùng modules cho UI/services mà KHÔNG duplicate DE logic.
Chỉ thêm requirements cần thiết đã tương thích Python 3.13, config host,
settings warehouse local, .gitignore. Giữ mọi đường dẫn DB qua config;
không hard-code ổ đĩa Windows. Mọi file có dữ liệu hoặc secrets phải bị
gitignore. Viết tests import/smoke và hướng dẫn chạy.
Không tích hợp MotherDuck, Streamlit Cloud, GitHub Actions hay SQLite.
Không dùng model output giả. Chạy pip check và pytest, báo rõ pass/fail.
```

**Đạt khi:** import app không lỗi, các file secret/DB/raw không xuất hiện trong `git ls-files`; tồn tại page placeholder với thông báo rõ trạng thái.

## Bước S02 — Tạo app chạy local, 9 trang không crash (CODEX)

**Chức năng đầu tiên:**
- `st.set_page_config(...)`; `st.navigation` + `st.Page`; sidebar gồm tài khoản, role, chế độ local, trạng thái dữ liệu, nút reload/logout.
- Nếu thiếu bảng: `DATA_NOT_READY` / `TABLE_NOT_AVAILABLE`; nếu thiếu model: `PENDING_MODEL`. **Không bắt `pred.*` phải có khi app khởi động**.
- Các trang dựa vào nguồn lịch sử hiển thị khi `mart.*` có; phần model chờ thì ghi rõ “Chưa tích hợp BT<n>; không có dự báo”.
- `st.session_state` chỉ dành cho trạng thái UI của từng phiên; không dùng session làm nơi xác nhận quyền tin cậy duy nhất.
- View không tự mở DB hoặc tự ghép SQL tùy ý.

**Prompt Codex:**

```text
Làm S02: ứng dụng Streamlit với st.navigation/st.Page và 9 trang đúng tên
trong tài liệu gốc, nhưng hoạt động ngay cả khi không có pred.* và chưa
có 8 model. Tạo component trạng thái:
WAREHOUSE_NOT_READY, DATA_READY, PENDING_MODEL, DQ_FAILED, REFRESH_REQUIRED.
Giữ trang có model nhưng ẩn/disable khối dự báo; không tạo số giả và
không coi thiếu pred là lỗi toàn hệ thống. Mọi view dùng common/service.
Tạo smoke tests (import/routing/empty DB).
```

**Bạn chạy khi code đã tồn tại:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py `
  --server.address 127.0.0.1 --server.port 8501
```

Trên máy host mở `http://localhost:8501`. Dừng server bằng `Ctrl+C`. Chưa mở LAN ở bước này.

**Đạt khi:** 9 trang hiển thị đúng trạng thái; không traceback vì `pred.fc_orders` chưa tồn tại.

## Bước S03 — Đăng nhập và phân quyền thật (CODEX + BẠN)

Giữ **7 vai trò UI** theo tài liệu cũ:
`executive`, `sales`, `demand_planning`, `warehouse_ops`, `logistics`, `marketing`, `data_team`.
**Không nhầm 7 vai trò UI với 9 schema/phòng ban của DE.**

**Quy tắc 2.0:**
1. **Bỏ fallback tài khoản demo cố định (`rohlik2024`)**, kể cả trên LAN.
2. **Bỏ mật khẩu SHA-256 đơn thuần**; dùng Argon2id (`argon2-cffi`) có salt và tham số lưu trong hash. `secrets.toml` chỉ lưu hash/role/name hoặc một store cục bộ riêng được bảo vệ.
3. Người dùng chưa đăng nhập không được vào các page đọc/ghi dữ liệu.
4. Backend `can_read/can_write/can_undo/can_refresh` kiểm lại trên **server**, không tin bảng/role từ browser.
5. Định danh tài khoản gắn `entered_by`; login/logout, failed logins, imports và undo có audit vừa đủ; không ghi mật khẩu/file nguyên bản vào log.
6. Giới hạn thử mật khẩu theo account + session/source theo mức phù hợp, timeout phiên, session logout.
7. Không tự cho `executive` quyền ghi tất cả bảng hoặc chạy pipeline; chốt bảng quyền rõ ràng với DE. Với MVP, **chỉ `data_team`** được thực thi refresh; các vai trò nghiệp vụ chỉ upload theo bảng được cấp.
8. Credentials trên **HTTP LAN không được mã hóa khi truyền**. Chỉ demo trên LAN đáng tin cậy với dữ liệu demo; dữ liệu nhạy cảm yêu cầu HTTPS/reverse proxy hoặc đường hầm bảo mật trước triển khai thật.

**Prompt Codex:**

```text
Làm S03: tạo auth/roles thật cho 7 UI roles, không demo fallback. Hash
mật khẩu Argon2id (không SHA-256 trần), người dùng do server xác thực,
role mapping từ config/roles.yaml được kiểm backend cho mọi query/write/
undo/refresh. Viết scripts/create_user.py hỏi mật khẩu bằng getpass,
KHÔNG nhận mật khẩu trực tiếp qua CLI argument, KHÔNG log plaintext.
Tạo tests anonymous denial, cross-role access, invalid password, logout,
session expiry, role tampering. Mọi secret ở file bị gitignore.
Chỉ role data_team được refresh trong MVP.
```

**Bạn tự làm:** đặt mật khẩu riêng cho từng account qua script Codex tạo, không gửi mật khẩu cho Codex. Xác nhận matrix quyền với nhóm.

**Đạt khi:** người chưa xác thực không mở URL trang con; user `marketing` không ghi `src_hr.workforce_params` kể cả khi gọi trực tiếp service.

## Bước S04 — Chạy LAN thật trên máy Windows host (CODEX config + BẠN hạ tầng)

### S04.1. Cấu hình Streamlit

Codex tạo `.streamlit/config.toml` (hoặc config tương đương):

```toml
[server]
address = "0.0.0.0"
port = 8501
headless = true
maxUploadSize = 25
enableCORS = true
enableXsrfProtection = true

[browser]
gatherUsageStats = false
```

**Giải thích:** `0.0.0.0` nghĩa là lắng nghe trên mọi IPv4 interface của máy host, **không phải địa chỉ để người khác gõ vào browser**. 25 MB là **giới hạn MVP đề xuất**, không phải giá trị bắt buộc DE; có thể đổi sau khi kiểm thử nhu cầu. Không tự tắt XSRF/CORS chỉ để “cho LAN chạy”.

### S04.2. Tìm IPv4 của host (BẠN)

Trên máy host PowerShell:

```powershell
ipconfig
Get-NetConnectionProfile
```

Tìm IPv4 của card **Wi-Fi/Ethernet đang cùng mạng với người nhập**, thường dạng `192.168.x.x` hoặc `10.x.x.x`. Ví dụ minh họa `192.168.1.23` **không phải IP máy bạn**.

### S04.3. Chạy server (BẠN)

Tại project root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py `
  --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

Trên **máy host**, thử `http://localhost:8501`. Trên **máy khác** cùng Wi-Fi/LAN, mở:

```text
http://192.168.1.23:8501
```

Thay `192.168.1.23` bằng **IPv4 thật của host**.

### S04.4. Cho phép cổng Windows Firewall (BẠN, PowerShell chạy Administrator)

**Chỉ làm khi đang ở mạng đáng tin và Windows Network Profile là `Private`**. Có thể cần hỏi quản trị mạng nếu dùng Wi-Fi trường/đơn vị.

```powershell
New-NetFirewallRule `
  -DisplayName "Rohlik Streamlit LAN" `
  -Direction Inbound -Action Allow -Protocol TCP `
  -LocalPort 8501 -Profile Private -RemoteAddress LocalSubnet
```

Quy tắc này mở TCP/8501 cho **local subnet** trên Private profile; nếu cần chặt hơn, thay `LocalSubnet` bằng CIDR LAN thật do bạn/IT xác nhận. **Không mở port trên router, không port-forward ra Internet, không mở trên mạng Public.**

Kiểm tra host đang nghe:

```powershell
Get-NetTCPConnection -LocalPort 8501 -State Listen
Test-NetConnection -ComputerName 127.0.0.1 -Port 8501
```

Từ máy Windows khác có thể kiểm tra:

```powershell
Test-NetConnection -ComputerName <HOST_IPV4> -Port 8501
```

Nếu không kết nối: xác nhận app vẫn chạy, đúng địa chỉ subnet, firewall/antivirus, hai máy cùng LAN, Wi-Fi không bật `AP isolation`/`Client isolation`, không dùng guest Wi-Fi cô lập khách. Nếu IP host đổi do DHCP, link LAN cũng đổi; có thể cấu hình DHCP reservation trên router khi được phép.

### S04.5. Nghiệm thu LAN

- [ ] Host mở `localhost:8501`.
- [ ] Máy thứ hai mở `<HOST_IPV4>:8501`.
- [ ] Hai browser đăng nhập **hai tài khoản khác nhau**, không chia sẻ session.
- [ ] Người chưa login không xem dữ liệu.
- [ ] Tắt server → client không vào được; server hoạt động **chỉ khi máy host bật và tiến trình đang chạy**.
- [ ] Không thể truy cập từ mạng ngoài LAN theo cấu hình demo.

**Prompt Codex cho S04:**

```text
Chuẩn bị chế độ triển khai Streamlit 2.0 cho LAN Windows: .streamlit/
config.toml, scripts/start_streamlit_lan.ps1, docs/streamlit_local_lan_runbook.md.
Script chỉ chạy 1 server, kiểm tra venv/port, in hướng dẫn tìm IPv4, không tự
mở firewall/public Internet, không chứa password. Tạo phần troubleshooting:
bind 0.0.0.0, IPv4, Firewall Private/LocalSubnet, AP isolation, DHCP IP,
CORS/XSRF/WebSocket, và security warning HTTP. Không triển khai cloud.
```

**Đạt khi:** 2 máy truy cập được app trên LAN. **Từ đây mới bắt đầu nhập liệu từ thiết bị khác.**


## Bước S05 — Kiểm tra DE readiness và trang Tổng quan dữ liệu (CODEX)

**Mục tiêu:** app **không phụ thuộc model** mà vẫn hiển thị đúng pipeline thực tế.

**Trạng thái có thứ tự:**

| Trạng thái | Khi nào | UI |
|---|---|---|
| `WAREHOUSE_NOT_READY` | Chưa có `rohlik.duckdb` chính thức hoặc kết nối không thành công | Thông báo chưa khởi tạo; chỉ có auth / hướng dẫn |
| `SOURCES_READY` | Nhận diện các CSV/config nhưng chưa có đủ landing | Trang source registry và preflight |
| `LANDING_READY` | Đủ 14 bảng `src_*` | Cho phép khám phá các bảng có quyền; upload chỉ bật khi entry backend đã sẵn |
| `MART_READY` | Có stg/core và 5 mart đã kiểm thử | Bật Tổng quan / EDA lịch sử |
| `DQ_FAILED` | DQ có ERROR chưa xử lý | Cảnh báo rõ, chặn quảng bá số liệu hoặc chạy downstream theo policy |
| `REFRESH_REQUIRED` | Có ACTIVE/UNDONE batch nhưng mart chưa phản ánh phiên mới | Badge trạng thái ở các trang liên quan |
| `PENDING_MODEL` | Chưa có pred/BT FINAL được duyệt | Tạm tắt các khối dự báo, không ảnh hưởng dữ liệu lịch sử |

**Trang `overview.py` — hiện tại (không dùng BT1):**
- Thông tin **DB chính thức đang mở**, môi trường `local`, thời điểm truy vấn.
- 7 nguồn active, fingerprint / byte size / trạng thái nhập nguồn (nếu metadata DE có).
- 14 bảng landing và số bảng hiện diện; 14 stg, 6 core, 5 mart: số đã tạo / thiếu.
- Tổng đơn gần nhất, phân bổ đơn theo kho, chuỗi đơn theo ngày/tuần, **chỉ khi `mart.sales_orders_day` có và DQ cho phép**; phải ghi rõ đơn vị, ngày lịch sử, không phải dự báo.
- Số PASS/WARN/FAIL của DQ lấy từ `meta.quality_report` **trên phiên chạy thật**, không hard-code “21/21”.
- Thời điểm `refresh` thành công gần nhất, trạng thái lô mới, nguồn ASSUMED.
- Không giả lập MAPE, forecast horizon, accuracy hay số đơn tương lai.

**Quy tắc phân biệt dữ liệu:** nhãn “Actual/historical” khác “Forecast”; `max(date)` phải lấy từ dữ liệu, không áp ngày hiện tại của năm 2026 để giả định dữ liệu Kaggle đã được cập nhật.

**Prompt Codex:**

```text
Làm S05: tạo catalog/readiness service và overview về DE, chỉ đọc nguồn
lịch sử có thật: 7 source fingerprints, 14 landing, 14 stg, 6 core, 5
mart, DQ report, pipeline_runs, freshness, đơn hàng lịch sử. Mọi bảng
có thể thiếu hoặc chưa khởi tạo: trạng thái rõ, không catch mọi lỗi rồi
coi là 'thiếu model'. Query giới hạn row/aggregate tại DuckDB (không
đưa hàng triệu dòng vào pandas). Không đọc pred.* ở khối lịch sử.
Tạo tests cho empty DB, partial DB, missing table, populated fixture,
DQ FAIL và data-date không bằng hôm nay.
```

**Đạt khi:** toàn bộ trang overview có thể chạy **khi `pred` trống**; các chỉ số lịch sử lấy từ `mart`, không tính sai grain hay JOIN nhân dòng.

## Bước S06 — Truy vấn/EDA không cần model (CODEX)

Trang `app/views/explorer.py` nên chia **hai tab triển khai ngay**, tab thứ ba trì hoãn có điều kiện:

1. **Xem & lọc dữ liệu:** chọn bảng **trong allowlist theo role**, chọn warehouse / date / category / SKU (nếu cột có), phân trang, tải CSV với giới hạn. Show row count và thời gian nguồn.
2. **EDA:** null ratio, thống kê mô tả, histogram số liệu, số đơn theo ngày/kho, discount/availability ở dữ liệu lịch sử, top category, kiểm tra trùng key từ báo cáo DQ.
3. **SQL nâng cao:** **không cho người dùng gõ SQL tự do trong MVP**. Chỉ danh sách query templates đã định nghĩa và parameter binding. Nếu thực sự cần ad hoc SQL sau này, phải có policy/SQL AST allowlist, limit tài nguyên và chống DuckDB table functions có thể đọc file; regex chỉ kiểm chữ `SELECT` **không đủ an toàn**.

**Kỹ thuật:**
- Server-side pagination (`LIMIT/OFFSET` hoặc cursor theo key), truy vấn có điều kiện; không `SELECT *` toàn bảng 4+ triệu dòng rồi lọc trong pandas.
- Chọn bảng/cột qua allowlist từ contract/catalog, **không nội suy tên bảng từ text người dùng**; giá trị dùng bind parameters.
- Chặn bảng `src_*`, `stg`, `meta` nếu role không được phép, không chỉ ẩn khỏi dropdown.
- Nếu liên quan dữ liệu nhạy cảm, áp row/column rules từ backend; không tự suy diễn mọi role được xem tất cả bản ghi.
- Data export cũng kiểm role và chống **CSV formula injection** khi mở trong Excel.
- Cache `st.cache_data` có TTL ngắn (~30–60 giây cho MVP) hoặc version key; invalidate sau mọi commit/undo/refresh thành công; session browser khác không tự động cập nhật ngay nếu không reload.

**Prompt Codex:**

```text
Làm S06 Explorer/EDA cho dữ liệu lịch sử. Chỉ query allowlisted tables &
columns theo role tại backend; bind query parameters; server-side limit/
pagination; row cap exports; tối ưu tránh load toàn bộ sales_train lớn.
Xây EDA: missing rate, descriptive, charts daily/warehouse/category,
DQ anomalies. Tab SQL chỉ có templates approved, không chạy arbitrary SQL,
COPY/ATTACH/read_csv/read_parquet/unsafe functions. Test injection table
name, permission bypass, file export formula injection, huge table,
nullable values, cache invalidation.
```

**Đạt khi:** EDA hoạt động không cần pred; Marketing không thể tải dữ liệu HR nếu không được cấp quyền.

## Bước S07 — CSV template và preview/validate (CODEX; CHƯA GHI)

Đây là **phần ưu tiên nhất**. Có thể viết ngay cả khi DuckDB chính thức chưa có đủ bảng, miễn `contract.yaml` đã được xác định.

**Giao diện nhập liệu tối thiểu:**

```text
[Chọn phòng/14 bảng mà role được ghi]
[Tải template CSV đúng schema_version]
[Chọn CSV để upload]
=> Đọc header; hiển thị 10-100 dòng đầu; số dòng; checksum; schema_version
=> Lỗi cụ thể theo dòng/cột và nguyên nhân
=> Thống kê New keys / Existing keys / Duplicate keys / Warnings
[ ] Tôi xác nhận các bản ghi là full-row replacement
[Xác nhận ghi batch]         (chỉ bật khi tất cả validations và DB sẵn sàng)
```

**Hợp đồng nhập theo DE V4:**
- CSV template dùng **tên canonical**. HR template phải có `hourly_wage_eur`, `morning_shift_ratio`, `overtime_cap_ratio`, `shortage_penalty_multiplier`, `legacy_rule_buffer_ratio`, **không dùng header raw khác tên**.
- Mỗi dòng upload chứa business keys + **đủ các editable fields bắt buộc** của bảng; mặc định **full-row replacement**, không patch trống “giữ giá trị cũ”.
- Với bản ghi đã có key trong landing, backend **append một phiên bản mới**; phiên bản ACTIVE mới nhất xuất hiện trong stg sau refresh, theo thứ tự có tie-break ổn định.
- Kiểm file size, extension/CSV parser (không tin extension), encoding UTF-8/UTF-8 BOM, delimiter, header thiếu/thừa/trùng, required/null, schema_version, dtype (date/number), range, key null, trùng key trong file, duplicate payload/hash, invalid values.
- Checks theo 14 bảng lấy từ DE contract; không tự thay đổi rule raw anomalous. Với dữ liệu lịch sử có sales NULL/discount âm, đưa ra DQ anomaly rõ ràng; không tự `COALESCE` hoặc clip.
- Preview không tự tạo transaction ghi; **không mutate raw CSV**.
- Preview phải tạo `upload_id` hoặc preview token có thời hạn, gắn actor/table/version/payload checksum; khi Confirm backend **đọc và validate lại chính payload đó**, chống sửa nội dung file/role trong phiên.

**Ví dụ HR template canonical (chỉ phần header minh họa, không đại diện dữ liệu):**

```csv
warehouse,hourly_wage_eur,items_per_order,picks_per_hour,shift_hours,morning_shift_ratio,overtime_multiplier,overtime_cap_ratio,shortage_penalty_multiplier,legacy_rule_buffer_ratio,orders_per_driver_shift
```

**Không dùng uploader làm công cụ upload lại cả `sales_train.csv`** hàng triệu dòng. User-entry MVP là **các lô cập nhật nhỏ có giới hạn đã cấu hình**; ingest raw CSV lớn thuộc pipeline DE, không thuộc app upload.

**Prompt Codex:**

```text
Làm S07: render input page: choose allowed logical table, download CSV
template canonical from contract.yaml, upload/preview/validate with reusable
DE entry.validate (hoặc implement đúng service DE được thống nhất sau audit).
Full-row update; 14 logical tables; HR canonical 11 columns (5 renames);
schema_version; file fingerprint; nullability; key dup; datatype; ranges;
clear row/column diagnostics. Preview phải 0 side effects. Confirm disabled
khi không có warehouse hoặc backend validation chưa sẵn. Tests: bad headers,
missing fields, duplicate keys, malformed csv, bad dates, invalid discounts,
HR rename, cost assumption ranges, empty file, modified payload.
KHÔNG implement insert ở bước này.
```

**Đạt khi:** download template + preview CSV hợp lệ/lỗi có thể demo ngay, không có model và **không làm thay đổi bất kỳ bảng nào**.

## Bước S08 — Confirm ghi trực tiếp DuckDB + audit + chống upload trùng (CODEX + DE READY)

**Chỉ thực hiện sau khi đã có DB đúng phiên bản / landing / meta service sẵn sàng.** Có thể test từ sớm trên temp DB.

**Transaction bắt buộc** (pseudocode, không phải SQL copy-paste):

```text
backend receives confirmed preview token
  -> verify identity, role, table, preview checksum and schema_version
  -> validate again against contract and current DB
  -> acquire application write coordinator (bounded wait)
  -> connect to local DuckDB as writer in Streamlit host process
  -> BEGIN TRANSACTION
      INSERT full-row records INTO src_x.table
        + _batch_id, _source, _loaded_at UTC, _entered_by
      INSERT meta.entry_log / batch metadata
      INSERT meta.batch_status_events(ACTIVE) or equivalent
     COMMIT
  -> release connection/lock
  -> invalidate cache and mark mart REFRESH_REQUIRED
  -> show batch_id, affected rows, actor, status
```

**Quy tắc:**
- Cùng một transaction chứa landing + audit, `ROLLBACK` toàn bộ nếu một khâu lỗi.
- Insert qua **parameterized SQL**; table/column names chỉ do server lookup từ contract allowlist; không cho người dùng gửi SQL.
- Chống double-click/retry: idempotency key gồm payload checksum, table, identity, schema_version và policy nghiệp vụ; trạng thái batch rõ, không tạo hai batch do refresh/trang reload.
- Không dùng `CREATE OR REPLACE` landing, không DELETE history.
- Hạn chế concurrent writers bằng `threading` lock/queue trong **cùng host process** và service độc quyền. Giao diện cần báo “Đang có giao dịch khác; thử lại” (không tự retry vô hạn).
- **External-process warning:** file lock cho subprocess không giải quyết được việc process khác đang giữ DuckDB open. DBeaver chỉ mở trên snapshot read-only/DB an toàn, không giữ writer trên DB đang phục vụ web.
- Nếu có nhiều thiết bị trên LAN, các yêu cầu của chúng đều đi vào **cùng server process**; không phải “mỗi máy một DuckDB writer”.
- Không set `read_only=True` ở một connection trong lúc process đang dùng DB cùng đường dẫn với config ghi khác biệt nếu thư viện từ chối mixed config; thực thi phép SELECT tại data access layer hạn chế quyền, và test thực tế cách quản lý connections DuckDB. Không thể dựa vào `read_only` Python flag như toàn bộ hệ thống phân quyền.

**Prompt Codex:**

```text
Làm S08 trên backend DE chung. Dùng DuckDB local direct write, 1 host
process writer coordination, short connection per task, parameter binding,
atomic transaction INSERT landing + entry_log + batch_status_events.
Preserve raw and historical landing; return batch id. Idempotent retry/
double click. Verify actor/role/payload hash/schema_version server-side
at confirm. On failure rollback ALL changes; no partial audit/data.
Use temp DuckDB in tests, do not write to rohlik.duckdb during tests.
Never spawn independent CLI process from Streamlit to perform write.
Implement concurrency tests for 2 parallel web requests/sessions.
```

**Đạt khi:** một CSV update nhỏ được ghi vào `src_*` và audit cùng batch; lỗi cố ý ở audit khiến **không một dòng landing nào được commit**.

## Bước S09 — Lịch sử batch và Undo mềm (CODEX)

**Trang `entry.py` có bảng lịch sử:**
- batch_id, bảng, actor, thời gian UTC, số rows, checksum rút gọn, trạng thái hiện tại, trạng thái refresh, người/điều kiện undo.
- filter theo bảng/user/time; chỉ admin/data_team được xem tất cả nếu chính sách cho phép.

**Undo mềm:**
- User chọn batch, nhập lý do, server check `can_undo`, trạng thái ACTIVE, quyền sở hữu hoặc vai trò;
- ghi **event UNDONE mới** vào `meta.batch_status_events` cùng transaction; giữ nguyên bản ghi `src_*` và event history cũ;
- query effective status từ **event mới nhất mỗi batch**, không JOIN toàn bộ event history gây nhân dòng;
- `refresh` sau undo khiến stg chọn lại bản ACTIVE trước đó (nếu tồn tại), core/mart phản ánh lại;
- Undo lặp lại trả `ALREADY_UNDONE`, không xóa/undo nhầm batch khác.

**Prompt Codex:**

```text
Làm S09: batch history + soft undo với check can_undo ở backend.
Append immutable UNDONE event, never DELETE landing data. Resolve latest
batch status deterministically, prove stg excludes UNDONE and falls back
to previous active version after refresh. Tests repeated undo, unauthorized
undo, concurrent confirm vs undo, audit failure, old record preserved.
```

**Đạt khi:** sau Undo và refresh, giá trị mart quay về phiên hợp lệ trước; landing/history vẫn có chứng cứ phiên bị undo.

## Bước S10 — Refresh DE và trang Vận hành, KHÔNG chạy model (CODEX + DE READY)

Đây là nơi phải **khác tài liệu gốc**. File cũ khuyến nghị nhấn nút Streamlit chạy `subprocess.Popen(python -m pipeline.run ...)`, dựa vào `.run.lock`. **Không coi đây là phương án mặc định an toàn** khi server Streamlit giữ DuckDB file mở. Thiết kế lại:

### Cách refresh chuẩn của Streamlit 2.0

```text
Bấm “Refresh dữ liệu lịch sử” [data_team]
   -> backend kiểm role / maintenance / DQ policy
   -> acquire cùng coordinator với CSV upload
   -> gọi DE refresh service trong process host (không CLI subprocess)
   -> stg(14) -> core(6) -> marts(5) -> quality checks
   -> transaction hoặc publish staging/swap an toàn
   -> cập nhật meta.pipeline_runs, freshness, audit và run status
   -> invalidate query cache; đổi REFRESH_REQUIRED -> DATA_READY
```

**Refresh chỉ là `src_* → stg → core → mart → DQ`**:
- không tự re-ingest 7 raw CSV;
- không chạy `BT1..BT8`;
- không tạo `pred` giả;
- không thông báo “thành công” khi có ERROR;
- nếu transform/DQ fail, giữ bộ mart hợp lệ trước đó nếu kiến trúc atomic publish cho phép và đánh dấu failure.
- Nếu DE module hiện chỉ hỗ trợ `pipeline.run` CLI, Codex cần **refactor business logic ra hàm callable/reusable**; CLI chỉ là wrapper. Tránh gọi subprocess từ web trước khi giải quyết xung đột DB giữa process.

**MVP đơn giản:** admin/data_team nhấn Refresh, UI hiển thị `st.spinner` trong lúc một service worker đang thực thi (có timeout/thông báo). Nếu lâu hơn giới hạn chấp nhận, triển khai hàng đợi **trong cùng process**, có job_id, progress/status từ `meta.pipeline_runs`. Không tự mở nhiều server worker processes hoặc background CLI writer.

**Trang `system.py` hiện tại gồm:**
1. Data readiness / Source Registry / 14 landing / 5 mart.
2. Pipeline run logs và trạng thái bước `init` (DE/CLI maintenance), `refresh` (web), `models` (**disabled**).
3. DQ report: PASS/WARN/FAIL, check_id, bảng, reason, violation examples phù hợp policy.
4. Data freshness: ngày dữ liệu nguồn, lần ingest, lần batch/refresh.
5. Writer state: ID job hiện tại, queue/busy, maintenance mode.
6. Models registry: chỉ trạng thái `NOT_AVAILABLE` hoặc `PENDING`; không báo STUB đã chạy khi chưa chạy.
7. Backup/maintenance instructions; UI **không** có “reset DB” cho người dùng nghiệp vụ.

**Prompt Codex:**

```text
Làm S10: refactor DE refresh logic thành callable service trong cùng
Streamlit host process, dùng same writer coordinator của entry/undo.
Refresh only stg/core/mart/DQ, không init/raw ingest, không chạy models.
Add run logs, status and DQ report in system.py; only data_team triggers
refresh. Atomic publish/rollback where feasible; do not claim success
if DQ ERROR. No subprocess.Popen runner for web workflow. Preserve CLI
interface for offline/maintenance use AFTER server shutdown.
Tests: concurrent upload/refresh serialized; failure rollback; mart
remains consistent; no pred writes; stale cache invalidation.
```

**Đạt khi:** sau nhập liệu, bấm Refresh trên trang System, mart thay đổi đúng; 8 BT không bị gọi.

## Bước S11 — Triển khai 9 trang theo 2 lớp, không phụ thuộc model (CODEX)

Tài liệu gốc có **9 trang**; phiên bản 2.0 **giữ tên, URL và ý nghĩa** để dễ ghép khi BT1–BT8 có kết quả. Phân loại từng phần như sau:

| Trang (file) | Phần có thể làm ngay | Phần chờ model |
|---|---|---|
| Tổng quan `overview.py` | KPI lịch sử, source status, DQ, freshness, runs | P50/P90 forecast, MAPE/coverage |
| Nhân sự kho `ops.py` | Đơn thực tế theo kho/ngày, biểu đồ lịch sử | BT1 forecast, BT2 staffing/cost plan |
| Tài xế `logistics.py` | Hiển thị assumptions HR `orders_per_driver_shift` **nếu role được đọc**; giải thích tham số | BT2 driver plan |
| Nhu cầu & Đặt hàng `demand.py` | SKU sales/availability/category/giá lịch sử | BT3 lost demand, BT4 forecast, BT6 replenishment |
| Khuyến mãi `pricing.py` | Discount/price theo thời gian, coverage ngành hàng | BT5 lift effects, BT7 markdown recommendation |
| Tăng trưởng `growth.py` | `mart.exec_kpi_month`, số đơn qua các tháng | BT8 fitted growth/projected new warehouse |
| Truy vấn & EDA `explorer.py` | Toàn bộ historical allowlisted query/EDA | Không phụ thuộc BT |
| Nhập dữ liệu `entry.py` | Template, validate, confirm, audit, undo | Không phụ thuộc BT |
| Vận hành `system.py` | DQ/source/run/refresh/permissions | Models/evaluate disabled đến khi có handoff |

**UI nhãn hiển thị cần chuẩn hóa:**
- `LỊCH SỬ / ACTUAL`: lấy từ Kaggle raw + nguồn nhập đang active/đã refresh.
- `GIẢ ĐỊNH / ASSUMED`: tham số Finance/HR; không suy ra là giá/nhân sự thực tế.
- `CHỜ MÔ HÌNH / PENDING_MODEL`: không có output, không tính chỉ số.
- `STUB — CHỈ KIỂM THỬ`: chỉ sử dụng sau nếu **STUB thực sự chạy**, có `model_status=stub` được xác nhận.
- `FINAL`: chỉ dùng khi đã được kiểm định trên contract/run lineage.

**Prompt Codex:**

```text
Làm S11: hoàn thiện 9 trang hiện hữu theo bảng MVP vs PENDING_MODEL.
Không cần pred.*; khối lịch sử đọc mart/core có quyền, khối model hiển thị
trạng thái chờ đúng lý do, không chế số. Dùng common status banners và
read-only catalog. Giữ page URL, labels và role menu theo config.
Render an toàn khi history missing/empty/null, biểu đồ không crash.
Tests role visibility + each page smoke with pred missing.
```

**Đạt khi:** 9 trang có nội dung phù hợp, nhưng các phần dự báo vẫn là **chờ**.

## Bước S12 — Kiểm thử tự động + nghiệm thu hai thiết bị LAN (CODEX + BẠN)

### S12.1. Codex chạy tests với **DB tạm**, không dùng DB thật

| Nhóm | Điều phải chứng minh |
|---|---|
| UI/auth | 7 roles, login/logout, session timeout, chặn direct service access |
| Empty/readiness | Không có warehouse/pred vẫn không crash; trạng thái đúng |
| Source/contract | 7 nguồn, 14 logical tables; HR 5 rename, cost/HR ASSUMED |
| Query/EDA | Role allowlist, SQL injection attempts, limits, nulls, exports |
| CSV preview | Header/encoding/types/keys/duplicate/negative tests |
| Batch transaction | Insert + audit atomic, error → full rollback, retry idempotent |
| Undo | Không DELETE landing, latest status, previous active comes back |
| Refresh | stg/core/mart update; 0 model calls; DQ failures appropriately blocked |
| Concurrency | 2 users upload cùng lúc không tạo double write/lost audit |
| Cache | User B thấy dữ liệu mới sau invalidation/reload; không cached stale KPI |
| LAN config | Bind address/port đúng, firewall hướng dẫn rõ, no exposed secrets |
| Regression DE | Existing unit/integration tests không bị phá |

Lệnh kiểm thử tại repo root (khi Codex đã tạo test/scripts):

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
git ls-files | Select-String -Pattern '(^|/|\\)(\.env|secrets\.toml|data/raw|data/warehouse|.*\.duckdb)'
```

Nếu kết quả `git ls-files` cho thấy raw/database/secrets đã **bị tracked từ trước**, cần kế hoạch tách track được duyệt, **không tự `git rm`/xóa file**.

### S12.2. Bạn kiểm thử E2E thực tế trên LAN

Dùng 2 laptop hoặc 1 laptop + 1 điện thoại, trên cùng Wi-Fi.

**Case E2E-01 — Khởi động và đăng nhập**
1. Start Streamlit ở host; mở host và client qua IP.
2. Đăng nhập 2 user khác nhau, xem menu và các quyền.
3. Truy cập trực tiếp URL trang bị cấm bằng user không có quyền; phải từ chối.

**Case E2E-02 — Preview trước khi ghi**
1. Tải `src_ops.availability` template (hoặc bảng được quyền).
2. Upload CSV valid, xem key/field/row summary; **chưa ghi gì**.
3. Upload một file invalid (sai header/availability > 1), xác nhận không thể bấm Commit.

**Case E2E-03 — Nhập và refresh**
1. Upload bản hợp lệ dùng **DB thử nghiệm/snapshot an toàn**, xác nhận và ghi lại `batch_id`.
2. Kiểm `src_ops.availability`/`meta.entry_log`/event trạng thái ACTIVE trong DBeaver **sau khi ngừng writer hoặc trên bản snapshot**, hoặc thông qua trang System/query được kiểm soát.
3. Trước Refresh có trạng thái `REFRESH_REQUIRED`.
4. User `data_team` chạy Refresh.
5. Explorer/Overview trên **máy thứ hai** hiển thị dữ liệu có hiệu lực mới, không cần chạy BT.

**Case E2E-04 — Undo**
1. Undo batch qua role có quyền.
2. Refresh.
3. Stg/core/mart thể hiện giá trị cũ; source landing vẫn còn cả hai phiên; event `UNDONE` có audit.

**Case E2E-05 — Concurrency / failure**
1. Máy A và B đồng thời submit, không lỗi DB lock không giải thích và không nhân đôi batch.
2. Kích hoạt test lỗi audit trên **DB tạm**; toàn bộ transaction rollback.
3. Nếu DE đang Refresh, uploader nhận busy/queue có hướng dẫn; không mất dữ liệu người dùng.

**Case E2E-06 — Restart/recovery**
1. Stop/restart Streamlit, đăng nhập lại.
2. Batches và audit vẫn tồn tại trên DuckDB; cache làm mới, không mất thay đổi.
3. Thử `init` lại **chỉ qua quy trình DE đã test**: phải NO_OP theo fingerprint và không xóa nhập liệu (không thử reset trên kho thật).

### S12.3. Báo cáo bàn giao

Codex tạo `docs/streamlit_mvp_acceptance.md` có:
- commit hash, thời điểm test, Python/Streamlit/DuckDB versions;
- 7 nguồn active & checksums nếu đã preflight; 14/14/6/5 status thực;
- số test pass/fail/skip và lỗi DQ thực tế, không báo số cố định từ V4;
- ảnh/screenshots hoặc log của 2 client LAN nếu bạn cung cấp;
- bằng chứng transaction, Undo, Refresh, xử lý 2 users;
- mục chưa hoàn thành: BT1–BT8, pred.*, model-backed cards;
- các giới hạn an toàn HTTP LAN, single-host, DuckDB file concurrency.

**Prompt Codex:**

```text
Làm S12: pytest fixtures sử dụng temporary DuckDB only; complete
unit/integration tests for auth/roles, no-model readiness, EDA, upload,
atomic audit, soft undo, refresh/DQ, double submit and concurrent sessions.
Prepare docs/streamlit_mvp_acceptance.md with actual commands/results,
not invented pass numbers. Do not run destructive tests on live warehouse.
Prepare checklist two real LAN browsers; mark MANUAL_VERIFY for physical
Wi-Fi, Windows firewall and mobile checks you cannot perform.
```

**Đạt khi:** Gate A + Gate B đạt những mục đã đủ dependency; items chưa sẵn từ DE được đánh dấu `BLOCKED_BY_DE`, **không báo Done giả**.

## Bước S13 — Chỉ khi 8 model được bàn giao (HOÃN, không làm bây giờ)

**Không nằm trong checklist MVP.** Khi BT1–BT8 có handoff:

1. Đối chiếu `frames.SCHEMA`, `output_contract.yaml`, notebook/model card; đặc biệt BT4 (phân vị P10/P50/P90 vs P20…P90 + point) và HR fields.
2. Chốt 14 output contracts và 2 history tables, không đổi contract chỉ vì cần demo UI.
3. Mỗi model được kiểm bằng `check_model.py` trên fixture, so outputs, dtype/key/horizon, đơn vị, `model_status`.
4. Pipeline models chạy độc lập khỏi transaction dashboard dài; khi tích hợp phải quản lý exclusive DB access; không tự chạy model khi user bấm Refresh.
5. Chỉ mở visualization dựa trên bảng `pred.*` đã tồn tại và `status` hợp lệ; hiển thị rõ `STUB/FINAL`.
6. Model failure không phá dữ liệu lịch sử/landing/mart, không publish output dở.

**Không đổi sang Cloud/MotherDuck chỉ vì có model; online là quyết định triển khai riêng.**

---

# 4. Chi tiết kỹ thuật Codex cần tuân thủ

## 4.1. Backend interface đề xuất

Tùy repository hiện có, Codex định nghĩa **interface nhỏ nhất**, không nhất thiết đúng tên dưới đây. Đặc biệt phải reuse DE source of truth:

```python
# PSEUDOCODE CONTRACT — KHÔNG PHẢI implementation đã có

catalog.status() -> DataReadiness
catalog.allowed_tables(user, action="read" | "write") -> list[str]
catalog.get_contract(logical_table) -> Contract
query_service.query_template(user, template_id, params, limit) -> DataFrame
entry_service.make_template(user, logical_table) -> bytes
entry_service.preview(user, logical_table, csv_bytes) -> PreviewResult
entry_service.commit(user, preview_id, expected_hash) -> BatchReceipt
entry_service.undo(user, batch_id, reason) -> UndoReceipt
run_service.refresh(user) -> RunReceipt
run_service.status(user) -> list[RunStatus]
quality_service.current_report(user) -> DataFrame
```

**Không** đưa raw connection DuckDB, SQL string hoặc role được nhận từ browser xuống các service viết. Backend xác định bảng qua contract.

## 4.2. Writer coordination chính xác với DuckDB

**MVP deployment constraint: một process web + một file warehouse trên local disk.**

- Shared singleton lock/queue cấp server-process (có thể xây bằng `@st.cache_resource` trả về coordinator thread-safe); không tạo một lock khác nhau cho mỗi session.
- Dùng connection ngắn trong mỗi tác vụ, close trong `finally`; không cache một global DuckDB connection chia sẻ tùy tiện.
- Dùng transaction bao trọn mỗi batch. Với refresh có DDL/materialization, phải quyết định atomic publish dựa trên hỗ trợ thực tế của DuckDB và test rollback — không chỉ ghép nhiều `CREATE OR REPLACE` rồi coi là atomic.
- Không gọi đồng thời DB từ một tiến trình Python CLI khác đang mở DuckDB file với chế độ write trong khi Streamlit đang chạy.
- Nếu cần chạy DE `init`/data migration/full backfill thủ công: chuyển app **maintenance/read-only mode**, ngừng tác vụ, đóng mọi connection, **tắt web server**, backup an toàn, chạy CLI ngoài; khởi động lại server.
- Nếu muốn hoạt động liên tục với nhiều người nhập thật + workers đa process, cần **đánh giá chuyển sang một DB server (ví dụ PostgreSQL) hoặc write service chuyên dụng**; đó là roadmap riêng, không lén thay DuckDB/SQLite trong MVP.

**Không xử lý DB lock bằng:** retry vô hạn, xóa file `.lock` bằng tay, `kill` process ngẫu nhiên, copy file `.duckdb` nóng, hoặc mở DBeaver writer vào DB live.

## 4.3. Security tối thiểu cho HTTP LAN

**LAN là môi trường mạng, không phải authentication.**
- Bắt buộc username/password cho dữ liệu có quyền kiểm soát, mật khẩu hash Argon2id; không auto-login tài khoản admin/demo.
- Không đặt raw CSV, secrets, DB ở thư mục web public; không ghi `st.secrets` vào log.
- HTTPS chưa có thì **chỉ chạy demo với dữ liệu không nhạy cảm trên Wi-Fi trusted**. Người trên cùng mạng có thể quan sát HTTP nếu hạ tầng không bảo vệ phù hợp; môi trường thực tế yêu cầu HTTPS/reverse proxy/VPN.
- Không port-forward router và không expose `0.0.0.0:8501` trực tiếp tới public Internet.
- Định danh từng người nhập (không dùng chung tài khoản) nếu cần audit chính xác.
- Role check luôn ở backend. Page hidden **không** là permission check.
- CSV không được phép điều khiển path, SQL, Python code; đặt size/row limit/timeout.
- Nếu data thực chứa cá nhân/thông tin nội bộ, xem lại quy định chia sẻ trước khi bật LAN.

## 4.4. Data correctness không được hi sinh để UI trông đẹp

- Streamlit không được tự tính “forecast 14 ngày” từ dữ liệu lịch sử rồi giả làm BT1.
- Số liệu Kaggle có thời gian lịch sử; không gọi `last 90 days relative to now()` nếu dataset không trải tới hiện tại. Lấy `max(date)` có data và hiển thị đó là **as-of date**.
- Không coi `orders` (Orders competition) và `order_index` (median total_orders từ Sales) là cùng biến; giữ ý nghĩa DE.
- Không coi sales/discount bất thường là 0 chỉ vì chart không hiển thị đẹp; theo DQ policy.
- Tính top-SKU/kho tại đúng grain; filter/time-bounds và joins không nhân dòng.
- Giá, lương, nhân sự giả định và output mô hình phải có nhãn rõ, không trình bày là actual.
- Không tự suy luận rằng `meta.model_registry` tồn tại khi chưa có models; graceful read.
- Mọi báo cáo/metric phải có query nguồn, thời điểm refresh, và lý do `not available` khi thiếu.

## 4.5. Quy tắc cache và realtime trên LAN

- `st.cache_data` **chỉ dùng cho dữ liệu đọc**, keyed theo parameters và preferably warehouse generation/version; TTL có giới hạn.
- Sau insert/undo/refresh: service trigger invalidation / version bump và thông báo “cần làm mới” trên các session khác.
- Cần phân biệt **đã ghi landing** với **đã refresh mart**; chỉ sau refresh mới kỳ vọng mart thay đổi.
- Không dùng cache để giữ session auth/shared login. Không cache writer/transaction state như dữ liệu.
- Nếu app deploy nhiều process trong tương lai, in-process cache/lock không còn đủ; cần thiết kế lại.
- Streamlit rerun khi widget đổi không có nghĩa transaction được chạy lại: chỉ `st.form_submit_button`/confirm action đã bind idempotency mới gọi commit.

## 4.6. Lưu ý version/kiểm thử thư viện

Tài liệu này là **spec**, không có quyền truy cập laptop của bạn. Codex phải cài và kiểm thử các phiên bản thực tế cho Python 3.13, DuckDB và Streamlit rồi mới pin vào repository. Không chép code ví dụ cũ có tham số deprecated nếu runtime báo lỗi. Nếu API Streamlit đã đổi, giữ hành vi thay vì ép đúng một cú pháp từ tài liệu.

---

# 5. Bảng thay đổi so với `Xây dựng streamlit.md`

| Điểm tài liệu cũ | Quyết định 2.0 | Vì sao |
|---|---|---|
| Streamlit Community Cloud + MotherDuck | **Streamlit localhost/LAN + DuckDB file** | Đúng DE local-first đã chốt |
| Dashboard phát triển trên 8 STUB có sẵn | **Không chờ STUB/FINAL; pred có thể vắng hoàn toàn** | Chưa có 8 model đã chạy |
| Trang overview tập trung BT1/MAPE | **Data readiness + historical KPIs + DQ** | Model-free MVP |
| D3 dùng `subprocess.Popen` runner | **In-process DE service + centralized coordinator** | Tránh DuckDB cross-process file-lock |
| “Refresh & run models” cho các phòng | **Chỉ Refresh, role data_team; model button disabled** | Đúng scope hiện tại |
| Ba kiểu nhập, incl. data_editor và demo next-day | **CSV template/preview/validate/confirm là đường chính** | Khớp DE append-only contract |
| `entry.append_rows()` chưa thể hiện atomic audit | **Transaction dữ liệu + entry_log + status events** | Không mất lineage khi lỗi |
| Hủy lô kiểu xóa physical | **Soft undo qua UNDONE event** | Giữ lịch sử và traceability |
| Mật khẩu SHA-256, fallback demo | **Argon2id và không fallback** | An toàn hơn khi mở LAN |
| Free SQL `SELECT/WITH` qua regex | **Templates allowlisted; tùy chọn AST hardening về sau** | Tránh SQL/file access bypass |
| `st.cache_data(ttl=600)` cố định | **Cache ngắn/versioned + invalidation** | Có nhiều user cùng nhập |
| D7 thử xóa/rename bảng pred | **Test DB tạm/fixture; không phá live** | Không có pred và không làm hỏng warehouse |
| “Sẵn sàng chuyển Cloud chỉ qua token” | **Online về sau cần đánh giá lại architecture** | DuckDB LAN multiuser có giới hạn riêng |

---

# 6. Thứ tự prompt Codex để bạn dùng thực tế

**Không dán toàn bộ 13 prompts một lần.** Làm theo checkpoint, xem code/test và chạy app sau từng bước.

| Lần làm việc với Codex | Prompt cần đưa | Bạn kiểm tra đầu ra trước khi tiếp tục |
|---|---|---|
| 1 | **S00** | Audit repo, gap report, baseline tests |
| 2 | **S01 + S02** | `streamlit run app/main.py` trên localhost; không có pred vẫn chạy |
| 3 | **S03** | Auth + role backend, không tài khoản demo |
| 4 | **S04** | Config LAN; bạn mở trên máy khách thực tế |
| 5 | **S05 + S06** | Data overview, EDA lịch sử, missing DB handling |
| 6 | **S07** | CSV template/preview, 0 DB writes |
| 7 | **S08** | Atomic import + audit, tests DB tạm |
| 8 | **S09** | Soft undo + audit, tests DB tạm |
| 9 | **S10** | DE refresh in-process, no models, DQ |
| 10 | **S11 + S12** | 9 pages hoàn thiện, E2E LAN, acceptance report |
| *Sau này* | **S13** | Đối chiếu handoff BT1–BT8 |

### Mẫu mở đầu nên thêm vào mỗi yêu cầu Codex

```text
NGUYÊN TẮC BẮT BUỘC:
- Làm trên repo hiện tại; không tạo repo khác và không rewrite cấu trúc DE đã chạy.
- Dùng tài liệu Xây dựng streamlit-2.0.md và bản DE local-first làm source of truth.
- Chưa có 8 model: pred.* và model registry có thể chưa tồn tại.
- Local DuckDB only, no SQLite/MotherDuck/Cloud/GitHub Actions.
- Không reset/overwrite/populate DB thật bằng dữ liệu demo; test bằng temp DB.
- Giữ 7 CSV gốc, 14 landing, 14 stg, 6 core, 5 mart, HR canonical mapping.
- Backend role checks, atomic transactions, audit, soft undo, writer coordination.
- Mỗi lần chỉ implement phạm vi bước được yêu cầu; viết tests và chạy tests.
- Nếu thiếu dependency/service DE, trả rõ BLOCKED_BY_DE với đường dẫn/hàm cần có.
- Kết thúc: nêu files changed, commands run, test output, manual steps, risks.
```

---

# 7. Quick start — khi Codex đã hoàn thành S00–S04

**1. Mở PowerShell từ project root.**

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
```

**2. Tạo tài khoản bằng `scripts/create_user.py` mà Codex đã triển khai.**

```powershell
.\.venv\Scripts\python.exe scripts/create_user.py
```

Nhập mật khẩu tại prompt riêng; **không gửi password vào chat**. Nếu script chưa tồn tại, đây là **lệnh mục tiêu**, không phải lệnh bảo đảm chạy ngay.

**3. Chạy Streamlit trên host.**

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py `
  --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

**4. Mở trình duyệt:**
- Host: `http://localhost:8501`
- Laptop/điện thoại khác cùng Wi-Fi: `http://<HOST_IPV4>:8501`

**5. Đăng nhập và kiểm tra menu, role, trạng thái dữ liệu.** Nếu DE chưa sẵn, bắt đầu ở Gate A; đừng bấm bất kỳ lệnh reset/ingest nào để “cho dashboard có dữ liệu”.

**6. Khi DE có DB chính thức, chạy Gate B:** EDA → tải template → preview → confirm → audit → refresh → undo → refresh.

**7. Kết thúc demo:** dừng Streamlit bằng `Ctrl+C`. Backup đúng quy trình; không copy nóng DuckDB. Nếu cần tạm thời đóng quyền LAN, disable rule Firewall do bạn đã tạo:

```powershell
Disable-NetFirewallRule -DisplayName "Rohlik Streamlit LAN"
```

Lệnh này cần PowerShell Administrator. Khi cần dùng lại, có thể bật rule sau khi kiểm tra mạng đáng tin.

---

# 8. Definition of Done của Streamlit 2.0

- [ ] Không có 8 BT và không có `pred.*` vẫn khởi động, đăng nhập và thao tác UI.
- [ ] Trên LAN có ít nhất 2 client browser truy cập **một máy host**.
- [ ] 7 roles và quyền đọc/ghi được backend kiểm; mật khẩu Argon2id, không demo fallback.
- [ ] Không dùng Cloud/MotherDuck/SQLite, không mở database file qua LAN.
- [ ] 7 raw CSV, 14 landing, 14 stg, 6 core, 5 mart giữ đúng hợp đồng DE nếu các tầng đã sẵn.
- [ ] `mart`/overview/EDA chỉ hiển thị dữ liệu lịch sử thật với as-of date đúng.
- [ ] 14 bảng có template đúng canonical; HR có 11 cột/5 đổi tên; Finance/HR ASSUMED.
- [ ] Preview không ghi; validation rõ lỗi theo hàng/cột; confirm idempotent.
- [ ] INSERT landing + audit + ACTIVE event atomic; lỗi rollback toàn batch.
- [ ] Soft undo giữ nguyên historical landing, cập nhật status bằng sự kiện mới.
- [ ] Refresh không ingest raw, không chạy BT, có DQ và run logs; writer được serialize.
- [ ] Cache được làm mới sau write/undo/refresh, UI có nhãn trạng thái dữ liệu.
- [ ] Test dùng DB tạm; báo cáo nghiệm thu có bằng chứng thật và đánh dấu dependency chưa sẵn.
- [ ] Các vùng BT1–BT8 hiển thị `PENDING_MODEL`, không thể nhầm với STUB/FINAL.

**Điểm dừng hợp lệ hiện nay:** Nếu DE chỉ mới có Task 08A mà chưa build 14 bảng chính thức, có thể đạt **Gate A**, đồng thời Codex vẫn làm xong logic validator/entry/undo/refresh trên fixture riêng. Để đạt **Gate B** phải hoàn thành dependency DE tương ứng. **Không cần chờ train 8 model.**

---

# 9. Tài liệu nguồn và ghi chú

1. `Xây dựng streamlit.md` (tệp người dùng cung cấp): phạm vi PHẦN III, `st.navigation`, 9 pages, account/roles, views, explorer, entry, system, D1–D7. **Các đoạn code cũ là minh họa, không được mặc nhiên coi là code repo đã chạy.**
2. `Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.docx` (tệp người dùng cung cấp): kiến trúc Phần I; local-first; 7 raw CSV → 14 `src_*` → 14 `stg` → 6 `core` → 5 `mart`; direct DuckDB entry + transaction + soft undo; config/contract/quality; model STUB/FINAL là hợp đồng phụ thuộc riêng.
3. Quy định bảo mật / kiến trúc bổ sung của **bản 2.0**: Argon2id, LAN host-only, không fallback demo, app query templates, cùng process coordinator, no-model MVP. Đây là **đề xuất thiết kế nâng cấp**, không phải khẳng định các mục này đã có trong nguồn.
4. Không thể kiểm chứng trên máy thật: IP host, router, Windows Firewall, phiên bản thư viện, trạng thái code/DB và kết quả chạy test. Các mục này **phải có bằng chứng do Codex tại repo hoặc người dùng xác minh**.

**Trạng thái hoàn thành của bản tài liệu:** `IMPLEMENTATION_GUIDE_READY`; trạng thái ứng dụng thực tế: `NOT_VERIFIED_IN_REPOSITORY`.
