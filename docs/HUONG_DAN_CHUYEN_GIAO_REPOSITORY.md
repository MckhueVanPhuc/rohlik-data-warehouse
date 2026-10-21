# HƯỚNG DẪN CHUYỂN GIAO REPOSITORY ROHLIK DECISION HUB

**Đối tượng nhận:** thành viên mới tiếp quản Data Engineering, vận hành môi trường local, phối hợp với nhóm Dashboard/Model.  
**Repo:** https://github.com/MckhueVanPhuc/rohlik-data-warehouse (private)  
**Nhánh được kiểm tra:** main — commit **bc9bbd5aae05d1296743ecab6b5efcc7e8f65214**  
**Thời điểm đối chiếu GitHub:** 22/10/2026 (giờ Việt Nam)  
**Nền tảng đã được dự án chọn:** Windows 11, PowerShell, Python 3.13 64-bit, DuckDB file local, Streamlit v3.0.

> **Mục tiêu:** một người chưa tham gia từ đầu phải hiểu repository, clone được source, thiết lập môi trường và chạy đúng những phần **đã có**, đồng thời biết điều kiện nào còn thiếu để tiếp tục phát triển. Không coi kế hoạch trong tài liệu V4 là chức năng hiện hữu. Không được đưa raw CSV, database, mật khẩu hoặc token lên GitHub.

---

## 0. ĐỌC TRƯỚC TRONG 5 PHÚT: PHẠM VI THỰC TẾ

### 0.1. Dự án giải quyết vấn đề gì?

Rohlik Decision Hub định hướng kết hợp dữ liệu kinh doanh (đơn hàng, SKU, giá, khuyến mãi, vận hành kho, lịch, thời tiết, thông số giả định tài chính/nhân sự), chuẩn bị dữ liệu có kiểm soát cho các bài toán BT1–BT8 và hiển thị thông tin qua dashboard nội bộ. Thiết kế V4 đầy đủ mô tả tuyến **raw CSV → Landing (src_*) → STG → Core → Mart → Model → Prediction → Streamlit**.

**Hiện trạng đã triển khai KHÔNG tương đương tuyến end-to-end trên.** Đây là hai thành phần độc lập ở thời điểm bàn giao:

1. **Data Engineering foundation / V4-01 đến V4-03:** source registry, 14 business contracts thuộc 9 schema, preflight, DuckDB safety, metadata, nhập 7 CSV vào **14 Landing tables ở database thử nghiệm cô lập**. Có dry-run, ghi có điều kiện và xác minh NO_OP trên batch đã hoàn thành. **Chưa tạo STG/Core/Mart chính thức trên kho production, chưa có cập nhật dữ liệu từ người dùng.**
2. **Streamlit v3.0:** shell dashboard **admin-only, dashboard-only, read-only**, có xác thực local, 8 trang, lớp báo cáo chỉ đọc 5 tên Mart được phép. Dashboard hiện hiển thị trạng thái readiness khi warehouse hoặc Mart còn thiếu; **không chạy model, không tự động tạo KPI/forecast giả**.

Cả 8 model BT1–BT8 chưa được xác nhận có package handover/integration hợp lệ trong repo. **Nghiệm thu “code và test chạy” khác hoàn toàn nghiệm thu “hệ thống đưa ra quyết định kinh doanh end-to-end”.**

### 0.2. Ma trận khả năng chạy sau khi clone

| Mức | Tài nguyên cần ngoài Git | Làm được ngay? | Kết quả đúng |
| --- | --- | --- | --- |
| A. Đọc code và chạy automated tests | Python, dependencies | Có | Chạy pytest trên fixtures và DuckDB tạm |
| B. Mở trang đăng nhập Streamlit | Python, dependencies | Có | Mở màn hình login ở localhost |
| C. Đăng nhập dashboard | File local data/auth/users.json + mật khẩu được bàn giao riêng | Có điều kiện | Vào 8 trang; thiếu warehouse vẫn có readiness |
| D. Kiểm tra V4 source/raw | Đúng 7 CSV đối chiếu với registry | Có điều kiện | Chạy source validation và dry-run |
| E. Nạp Landing V4-03 | 7 CSV, DB cô lập, quyền ghi, đủ tài nguyên | Có điều kiện, **chỉ dev/acceptance** | Tạo 14 src_* landing, audit/metadata; chưa có Mart |
| F. Dashboard có KPI thật | Warehouse đã được kiểm định và publish 5 Mart | **Chưa có sẵn từ repo** | Chỉ khả thi sau khi có warehouse hợp lệ |
| G. Model BT1–BT8/decision hub end-to-end | Handoff notebook, artifact, schema, adapters, publisher, DQ | **Chưa hoàn thành** | Không khẳng định chạy được |

### 0.3. Quy tắc tiếp nhận

- Đọc **README.md**, **docs/setup_tutorial.md**, rồi tài liệu này.
- **Không chạy V4 “init/refresh/models” theo tài liệu thiết kế:** package pipeline.run hiện chưa tồn tại.
- Không dùng **app_smoke.py** làm dashboard chính; entry point hiện tại là **app/main.py**.
- Không dùng tài liệu Streamlit 2.0 (7 roles/Upload/Undo) như hiện trạng v3.0.
- Không ghi vào **data/warehouse/rohlik.duckdb** chính thức chỉ để thử. Không đổi tên database Task08A hoặc landing dev thành production.
- Với bất kỳ thao tác ghi DuckDB nào: dừng Streamlit, đóng DBeaver/client, ghi qua CLI/service có lock và transaction; lưu log, đối chiếu DQ.
- Hai file tham số cost/HR là **ASSUMED**, không phải số liệu Rohlik đã xác minh.

---

## 1. THỨ TỰ ĐỌC TÀI LIỆU — DÀNH CHO NGƯỜI MỚI

| Thứ tự | File/link trong repo | Dùng để làm gì? | Độ tin cậy cho runtime hiện tại |
| --- | --- | --- | --- |
| 1 | [README.md](../README.md) | Điểm bắt đầu, lệnh chính, tình trạng v3/V4 | Hiện hành |
| 2 | [docs/setup_tutorial.md](setup_tutorial.md) | Setup máy khác từ đầu, venv, auth, data, troubleshooting | Hiện hành, chi tiết nhất về setup |
| 3 | **Tài liệu bạn đang đọc** | Chuyển giao toàn repo, sơ đồ phụ thuộc, quyết định/rủi ro/roadmap | Đối chiếu với main tại mốc ghi trên |
| 4 | [docs/v4_03_landing_handover.md](v4_03_landing_handover.md) | Phạm vi Landing, 14 bảng, batch semantics, bằng chứng nghiệm thu thực | Hiện hành cho V4-03 |
| 5 | [docs/source_registry.md](source_registry.md) + [config/sources.yaml](../config/sources.yaml) + [config/contract.yaml](../config/contract.yaml) | 7 file nguồn, SHA-256, cột, key, kiểu, 14 bảng, update policy | Config/code là nguồn quyết định |
| 6 | [docs/duckdb_setup.md](duckdb_setup.md) | DB initialization, writer lock, backup, ingestion isolation | Hiện hành cho DB |
| 7 | [docs/dashboard_v3_runbook.md](dashboard_v3_runbook.md) + [docs/authentication_runbook.md](authentication_runbook.md) | Streamlit v3, read-only reporting, admin credential | Hiện hành cho UI |
| 8 | [docs/model_handover_checklist.md](model_handover_checklist.md) + [docs/model_integration_contract.md](model_integration_contract.md) | Yêu cầu nhận BT1–BT8 và nguyên tắc tích hợp | Tài liệu kế hoạch, chưa chứng minh model có sẵn |
| 9 | [Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md](../Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md) | Kiến trúc V4 mục tiêu ban đầu (STG/Core/Mart/8 BT/entry/undo) | **Thiết kế tham chiếu**, không phải trạng thái code |
| 10 | [docs/bootstrap_sources.md](bootstrap_sources.md), [docs/source_registry_task08a.md](source_registry_task08a.md), [docs/sqlite_setup.md](sqlite_setup.md) | Truy nguyên Task08A và SQLite cũ | Lịch sử/compatibility |
| 11 | [Xây dựng streamlit-2.0.md](../Xây%20dựng%20streamlit-2.0.md), [docs/streamlit_implementation_audit.md](streamlit_implementation_audit.md) | Quyết định và UI trước refactor | **Superseded** khi mâu thuẫn với v3 |

**Nếu tài liệu mâu thuẫn:** kiểm tra code/config/tests ở commit đang checkout → README/setup hiện hành → runbook chuyên đề → tài liệu V4/historical. Tài liệu cũ đôi khi ghi “PLANNED” cho thứ đã được triển khai sau đó; kiểm tra git history và code trước khi kết luận.

---

## 2. GIẢI THÍCH KIẾN TRÚC — CÁI ĐÃ CÓ VÀ CÁI CHƯA CÓ

~~~text
7 CSV trên máy (không commit lên Git)
   ├─ 5 file Kaggle gốc
   └─ 2 file giả định Finance/HR (ASSUMED)
          |
          v
config/sources.yaml + config/contract.yaml
          |
          v
src.validate_source_registry    (preflight read-only)
          |
          v
src.ingest_landing               (dry-run hoặc --execute trên DB cô lập)
          |
          v
14 bảng Landing tại 9 schema src_*  +  metadata/audit
          |
          |        [STG / Core / Mart CHƯA được triển khai chính thức]
          X -------> STG (14) -> Core (6) -> Mart (5)
                                        |
                                        X ----> Model adapter BT1...BT8 / pred
                                        |
                                        X ----> reporting marts đã publish
                                                   |
                                                   v
Streamlit app/main.py -- ReportingService (read-only)
    ^                              |
    |                              +-- tối đa 5 tên Mart allowlisted
    |
admin_local -> data/auth/users.json (local credential, không ở Git)
~~~

**Hai đường hoạt động riêng:** đăng nhập/UI v3 có thể chạy mà chưa có database báo cáo; V4-03 ingest có thể chạy trên DB thử nghiệm mà không tạo bất kỳ Mart nào cho UI. Không nối hai đường bằng cách cho Streamlit chạy trực tiếp lệnh ghi DB.

### Những thuật ngữ cần hiểu

- **Raw:** CSV nguồn chỉ đọc; không thay giá trị để “cho qua test”.
- **Source Registry:** danh sách nguồn được duyệt, đường dẫn, hash, header, type, grain và thông tin kiểm định.
- **Contract:** mô tả bảng đích, key, cột canonical, nullable, domain, thông tin provenance, trạng thái update policy.
- **Landing:** bản chiếu dữ liệu gốc vào bảng theo phòng ban, kèm nguồn và batch; **chưa phải dữ liệu sạch hay model-ready**.
- **STG:** tầng làm sạch/chọn bản ghi hợp lệ; trong full V4 là yêu cầu mục tiêu, hiện chưa hiện thực ở repo.
- **Core:** facts/dimensions/parameters tích hợp; hiện chưa có trong code.
- **Mart:** view báo cáo theo nhu cầu dashboard; ReportingService biết tên nhưng **không tự tạo view**.
- **Batch:** một lượt nạp có ID/source/timestamp/actor/status và audit; NO_OP phải chứng minh trạng thái đã hoàn thành chứ không chỉ so số dòng.
- **STUB/FINAL:** cách gọi trong thiết kế V4 về plug-in mô hình; **không có nghĩa repo hiện đã triển khai 8 stub**.

---

## 3. CẤU TRÚC REPO — GIẢI THÍCH CÁC THƯ MỤC VÀ FILE CHÍNH

| Thành phần | Vai trò và nơi bắt đầu | Trạng thái |
| --- | --- | --- |
| **.github/workflows/tests.yml** | Windows GitHub Actions, Python 3.13, cài requirements và chạy pytest trên push/PR | Đã có |
| **.gitignore** | Chặn venv, raw CSV, credential, .duckdb, WAL, log, backup, secret | Đã có; không sửa tùy tiện |
| **.streamlit/config.toml** | Streamlit theme, localhost/XSRF/CORS và cấu hình server | Đã có |
| **README.md** | Tổng quan vận hành, các cấp độ setup và README đầu vào | Đã có |
| **requirements.txt**, **pytest.ini** | Dependencies root và pytest settings; **chưa pin phiên bản package** | Đã có; cần cải thiện tái lập |
| **config/settings.yaml** | Raw dir, DB mặc định, 14-day horizon, SKU scope, runner local | Đã có |
| **config/sources.yaml** | 7 nguồn V4 active với fingerprint, headers, keys, checks | Đã có |
| **config/contract.yaml** | 14 bảng tại 9 src_* schemas, raw-to-canonical mapping, policy | Đã có; update policies chưa phê duyệt |
| **config/auth.yaml** | Đường dẫn credential, admin username, rate limit, password policy; không có password | Đã có |
| **config/sources_task08a.yaml** | Source Registry cũ, bảo toàn khả năng tái hiện Task08A | Historical |
| **config/README*.md** | Ghi chú cấu hình V4/Task08A | Tài liệu |
| **src/config/source_registry.py** | Load YAML an toàn, validate contracts, read-only source preflight | Đã có |
| **src/config/source_registry_task08a.py** | Adapter registry lịch sử | Historical |
| **src/validate_source_registry.py** | CLI metadata-only hoặc kiểm 7 CSV thật | Đã có |
| **src/profile_sources.py** | Thu thập bằng chứng profiling từ source | Đã có |
| **src/bootstrap_sources.py** + **src/ingestion/source_bootstrap.py** | 08A provisional source bootstrap, dry-run/execute/validate riêng | Historical/dev, không dùng thay V4-03 |
| **src/db/duckdb.py** | Chọn DB path, mở read-only, điều phối writer, transaction/lock | Đã có |
| **src/db/duckdb_metadata.py** | Schema metadata/batch/audit version v1 | Đã có |
| **src/db/backup.py** | Backup DB có kiểm soát | Đã có |
| **src/init_duckdb.py** | CLI khởi tạo file DuckDB rỗng; **không tạo business schema** | Đã có |
| **src/ingestion/landing.py** + **src/ingest_landing.py** | Ingest 7 file vào 14 bảng Landing, preflight/transaction/reconciliation | Đã có, ghi dev cô lập |
| **src/db/sqlite.py**, **src/init_sqlite.py** | Hạ tầng SQLite của giai đoạn trước | Historical; không dùng làm write path mới |
| **src/models/.gitkeep**, **src/services/.gitkeep** | Placeholder; không phải model/service có thể chạy | Chưa tích hợp |
| **app/main.py** | Entry point Streamlit v3 | Đã có |
| **app/auth.py** | Bắt đăng nhập admin, logout và session guard cho UI | Đã có |
| **app/services/identity.py** | Argon2id, credential store, session, rate limiter, revoke/timeout | Đã có |
| **app/services/reporting.py** | Chỉ đọc 5 Mart, introspect cột, filter, tổng hợp và phân trang an toàn | Đã có |
| **app/navigation.py** | Registry **8 trang** của Streamlit | Đã có |
| **app/common.py** | Khung UI chung, readiness, báo cáo/chart và EDA | Đã có |
| **app/views/** | Renderer từng trang: overview, ops, logistics, demand, pricing, growth, explorer, system | Đã có |
| **scripts/create_user.py** | CLI status, change-password, enable/disable cho admin có sẵn | Đã có; **không bootstrap admin mới** |
| **scripts/start_streamlit_lan.ps1** | LAN opt-in sau khi kiểm tra localhost; không mở Firewall tự động | Đã có |
| **app_smoke.py** | Entry point demo cũ | Historical; không dùng để chạy v3 |
| **tests/** | Bộ test nguồn, V4 landing/DB, SQLite lịch sử, Streamlit auth/nav/reporting/LAN | Đã có |
| **docs/** | Setup, dữ liệu, DQ, kiến trúc và runbook theo giai đoạn | Có cả hiện hành và lịch sử |
| **data/** | Thư mục local: raw, auth, warehouse, backup, acceptance; không lên Git | Cần tạo/bàn giao riêng |

### 3.1. Mười bốn bảng Landing thật ở V4-03

| Schema/phòng ban | Tên bảng | Nguồn |
| --- | --- | --- |
| src_sales | orders_daily | orders/train.csv |
| src_sales | sku_sales_daily | sales/sales_train.csv |
| src_marketing | prices | sales/sales_train.csv |
| src_marketing | promotions | sales/sales_train.csv |
| src_marketing | mov_changes | orders/train.csv |
| src_ops | availability | sales/sales_train.csv |
| src_ops | ops_events | orders/train.csv |
| src_category | product_master | sales/inventory.csv |
| src_planning | calendar | sales/calendar.csv |
| src_digital | user_activity | orders/train.csv |
| src_external | weather | orders/train.csv |
| src_finance | sku_weights | sales/test_weights.csv |
| src_finance | cost_params | assumptions/cost_params.csv |
| src_hr | workforce_params | assumptions/workforce_params.csv |

Tổng: **14 logical tables, 9 schemas, nhưng chỉ 7 physical CSV sources**. Một nguồn CSV có thể chiếu sang nhiều bảng, không được tính thành nhiều nguồn vật lý. Mọi bảng Landing có provenance **_batch_id, _source, _loaded_at, _entered_by**. Chi tiết key/grain/type/nullability cần đọc trực tiếp **config/contract.yaml** hoặc bảng đầy đủ trong **docs/v4_03_landing_handover.md**.

### 3.2. Tám trang Streamlit v3 và Mart tương ứng

| Trang | Renderer | Mart phục vụ dữ liệu lịch sử | Phần model đang chờ |
| --- | --- | --- | --- |
| Tổng quan | app/views/overview.py | mart.sales_orders_day | Dự báo P50/P90 |
| Nhân sự kho | app/views/ops.py | mart.ops_warehouse_day | BT1, BT2 |
| Tài xế | app/views/logistics.py | mart.ops_warehouse_day | BT2 |
| Nhu cầu & Đặt hàng | app/views/demand.py | mart.category_sku_day | BT3, BT4, BT6 |
| Khuyến mãi | app/views/pricing.py | mart.marketing_promo_day | BT5, BT7 |
| Tăng trưởng | app/views/growth.py | mart.exec_kpi_month | BT8 |
| Truy vấn & EDA | app/views/explorer.py | Năm Mart allowlisted, không SQL tự do | Không yêu cầu model |
| Vận hành hệ thống | app/views/system.py | Trạng thái read-only, không tự ghi DB | Chỉ trạng thái |

ReportingService chỉ nhận **mart.sales_orders_day, mart.ops_warehouse_day, mart.category_sku_day, mart.marketing_promo_day, mart.exec_kpi_month**. Nếu Mart chưa tồn tại, UI trả **TABLE_NOT_AVAILABLE**; chưa có DB: **WAREHOUSE_NOT_READY**; output model chưa xác minh: **PENDING_MODEL**. Khi Mart có thật: **DATA_READY**. Dashboard **không được fallback sang raw CSV** và không được hiển thị dữ liệu model tạo giả.

### 3.3. Các bài toán BT1–BT8 — chức năng định hướng, không phải code có sẵn

| BT | Bài toán dự kiến | Phụ thuộc/đầu ra phải xác nhận |
| --- | --- | --- |
| BT1 | Dự báo số đơn theo kho | Phân vị và horizon; dự kiến cung cấp cho BT2/BT4 |
| BT2 | Xếp ca nhân sự kho và tài xế | Dự báo đơn + tham số nhân sự ASSUMED |
| BT3 | Ước lượng nhu cầu/lượng doanh số bị mất | Sales, availability, giá, business grain |
| BT4 | Dự báo nhu cầu theo SKU | Đầu vào dự báo kho, demand; **chưa chốt phân vị output** |
| BT5 | Hiệu ứng khuyến mãi | Pricing/promotions và quy tắc đánh giá có bằng chứng |
| BT6 | Đề xuất lượng đặt hàng | Forecast SKU, lost demand, cost assumptions |
| BT7 | Markdown cho hàng sắp hết hạn | Forecast SKU, promo, replenishment, shelf life |
| BT8 | Phân tích/kịch bản tăng trưởng kho | Dữ liệu lịch sử kho và mô hình đã bàn giao |

Bảng là **định hướng theo V4**, không khẳng định nhóm Model đã/ chưa làm notebook riêng. Repo hiện **chưa có model adapters/runner được nghiệm thu**. Không tạo p20…p90, artifact hoặc kết quả BT bằng suy đoán cho đủ schema.

---

## 4. THỰC HÀNH SETUP MÁY NHẬN TỪ SỐ 0 — WINDOWS/POWERSHELL

### Bước 1 — Xin quyền và kiểm tra công cụ

Người nhận phải được cấp **Read** (để clone) hoặc **Write** (để tiếp tục phát triển) trên GitHub private repo. Không dùng tài khoản GitHub của người bàn giao; tự đăng nhập bằng Git Credential Manager/gh CLI của mình. Cài:

- Git for Windows và PowerShell (Windows 11).
- Python **3.13 64-bit**, không buộc gỡ Python phiên bản khác.
- VS Code + Python extension (khuyến nghị); DBeaver (chỉ để kiểm DB khi các writer đã đóng).

Mở **PowerShell** và chạy:

~~~powershell
git --version
py -0p
py -3.13 --version
py -3.13 -c "import sys, struct; print(sys.executable); print('bits:', struct.calcsize('P') * 8)"
~~~

Kỳ vọng **Python 3.13.x**, **bits: 64**. Nếu thiếu lệnh py launcher, xem hướng dẫn chọn đường dẫn python.exe trong docs/setup_tutorial.md, đừng mặc định python global là đúng.

### Bước 2 — Clone chính xác repo

~~~powershell
Set-Location -LiteralPath "$env:USERPROFILE\Documents"
git clone https://github.com/MckhueVanPhuc/rohlik-data-warehouse.git
Set-Location -LiteralPath .\rohlik-data-warehouse
git switch main
git pull --ff-only origin main
git status --short --branch
git log -1 --oneline
~~~

Nếu GitHub báo 404 hoặc repository not found: thường là **chưa có quyền/đăng nhập sai GitHub**, không tự đổi URL sang repository khác. Nếu máy đã clone: mở root, kiểm **git remote -v** và **git status**, chỉ pull khi working tree sạch. Không chạy reset/clean trên thư mục có dữ liệu chưa backup.

### Bước 3 — Tạo virtual environment của riêng máy mới

~~~powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys, struct; print(sys.executable); print('venv:', sys.prefix != sys.base_prefix); print('bits:', struct.calcsize('P') * 8)"
.\.venv\Scripts\python.exe -m pip --version
~~~

Kỳ vọng **venv: True**. Không copy .venv từ máy người khác vì chứa binary và đường dẫn cục bộ. Trong VS Code: Ctrl+Shift+P → **Python: Select Interpreter** → chọn **<repo>\\.venv\\Scripts\\python.exe**. Không bắt buộc Activate.ps1: dùng interpreter theo đường dẫn trực tiếp sẽ tránh lỗi execution policy.

### Bước 4 — Cài dependencies

~~~powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import argon2, duckdb, pandas, plotly, pyarrow, yaml, streamlit, pydantic, pytest; print('All imports OK')"
.\.venv\Scripts\python.exe -m streamlit --version
~~~

Root requirements hiện gồm duckdb, pandas, pyarrow, pyyaml, streamlit, pydantic, pytest, argon2-cffi, plotly và **chưa pin version**. Không tự cài thêm Prophet/XGBoost/Torch hoặc thư viện model BT vào root venv; môi trường ML phải tách sau khi model owner bàn giao version/wheel/artifact.

**Cảnh báo về reproducibility:** log GitHub Actions của commit main này đã cài DuckDB 2.0.0, trong khi docs/duckdb_setup.md ghi môi trường local khác từng dùng DuckDB 1.5.6. Đây là bằng chứng **dependency drift khi unpinned**, không khẳng định một bản là bắt buộc. Lưu **pip freeze** khi nghiệm thu, sau đó nhóm chốt lockfile dựa trên kiểm thử tương thích.

### Bước 5 — Chạy kiểm thử, chưa cần dữ liệu thật

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
git diff --check
~~~

Không cần 7 CSV, database production hay password cho bộ test synthetic. **Bằng chứng trên GitHub:** commit **bc9bbd5** có workflow **success**, 207 passed trên Windows/Python 3.13 tại [run 39646101119](https://github.com/MckhueVanPhuc/rohlik-data-warehouse/actions/runs/39646101119). Đây là **CI synthetic**, không thay thế việc người nhận chạy trên máy mình và cũng không chứng minh dashboard có live data. Nếu số test khác sau commit mới, lấy điều kiện **0 failed** làm ngưỡng chính thay vì buộc đúng 207.

Nếu thư mục pytest temp bị Windows lock, xem README; có thể dùng basetemp mới:

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp_handover
~~~

### Bước 6 — Kiểm tra các file bị Git ignore

~~~powershell
git check-ignore -v -- data/auth/users.json
git check-ignore -v -- data/raw/orders/train.csv
git check-ignore -v -- data/warehouse/rohlik.duckdb
git check-ignore -v -- .env
git check-ignore -v -- .streamlit/secrets.toml
git status --short
~~~

Các mục này **phải** bị ignore. Không sửa .gitignore để đẩy raw/data/credential. Không chèn token hoặc password vào PowerShell history, source hay tài liệu.

### Bước 7 — Chạy Streamlit ở chế độ shell/login

~~~powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
~~~

Mở **http://127.0.0.1:8501**. Sau clone lần đầu, trang login có thể xuất hiện nhưng **đăng nhập chưa thành công vì thiếu users.json**. Đây là trạng thái đúng. Không dùng app_smoke.py.

Để đăng nhập, chủ tài khoản bàn giao **data/auth/users.json** qua kênh bảo mật đã được nhóm duyệt và **mật khẩu qua kênh khác**. Đây là file hashed credentials (Argon2id), vẫn là bí mật nhạy cảm. Người nhận đặt file vào đúng đường dẫn:

~~~powershell
New-Item -ItemType Directory -Force -Path .\data\auth | Out-Null
.\.venv\Scripts\python.exe -m scripts.create_user status
.\.venv\Scripts\python.exe -m scripts.create_user change-password
~~~

Đổi password thực hiện trên máy nhận qua hidden prompt. Username duy nhất được allowlist là **admin_local**. Các lệnh CLI hiện có: **status**, **change-password**, **disable**, **enable**. **Không có first-time create user**: nếu users.json chưa được chuyển, lệnh status/change-password báo lỗi; không dùng mật khẩu mặc định hay tự sửa JSON/hash bằng tay. Tắt app với Ctrl+C.

Sau login, kỳ vọng đúng **8 trang**, sidebar LOCAL, logout/idle timeout, và readiness trạng thái đúng; **không có Upload, Entry, Undo, CRUD hay nút chạy model**. Đừng đánh giá “lỗi” chỉ vì KPI chưa xuất hiện trong kho chưa publish.

### Bước 8 — Chỉ khi cần chạy trên LAN

Kiểm tra login/logout trên localhost trước. Sau đó dừng server và (chỉ trong mạng tin cậy, dữ liệu không nhạy cảm):

~~~powershell
.\scripts\start_streamlit_lan.ps1
~~~

Tra IP của máy host theo docs/streamlit_local_lan_runbook.md. LAN sử dụng HTTP, script **không tự mở Firewall**. Không port-forward trực tiếp lên Internet, không tự sửa firewall/corporate security để test cho nhanh.

---

## 5. BÀN GIAO DỮ LIỆU NGUỒN CHO DATA ENGINEERING

### 5.1. Bộ file phải đặt đúng nơi

~~~text
data/
  raw/
    orders/
      train.csv
    sales/
      sales_train.csv
      inventory.csv
      calendar.csv
      test_weights.csv
    assumptions/
      cost_params.csv
      workforce_params.csv
~~~

Người nhận cần nhận 7 file qua kênh dữ liệu có quyền truy cập, **không phải qua Git commit**. Đây là 5 CSV Kaggle và 2 CSV giả định. Định dạng, hash SHA-256, cột và số dòng chính thức nằm trong config/sources.yaml; không chỉnh header hoặc sửa registry để “hợp thức hóa” dữ liệu khác.

| Source | Số dòng theo registry / acceptance | Lưu ý |
| --- | ---: | --- |
| orders/train.csv | 7,340 | Đơn theo kho-ngày |
| sales/sales_train.csv | 4,007,419 | Dữ liệu lớn; chiếu sang nhiều bảng |
| sales/inventory.csv | 5,432 | Danh mục sản phẩm/SKU |
| sales/calendar.csv | 23,016 | Calendar chính thức của V4 |
| sales/test_weights.csv | 5,390 | **Weight đánh giá**, không phải kg/giá vốn |
| assumptions/cost_params.csv | 3 | Finance; **ASSUMED** |
| assumptions/workforce_params.csv | 7 | HR theo warehouse; **ASSUMED** |

**Không đưa orders/train_calendar.csv vào 7 active sources V4.** File này thuộc Task08A/historical. Registry V4 không dùng nó để tạo bảng mới. Hai file assumptions có thể thay đổi khi nhóm duyệt tham số; thay file cần version/hash/contract mới, không tự sửa dưới cùng một fingerprint.

### 5.2. Mapping HR phải nắm

Raw HR có 11 cột; khi đưa vào canonical Landing, chính xác **5** tên thay đổi:

| CSV header | Canonical trong Landing |
| --- | --- |
| wage_eur_per_hour | hourly_wage_eur |
| morning_share | morning_shift_ratio |
| overtime_cap | overtime_cap_ratio |
| shortage_penalty | shortage_penalty_multiplier |
| rule_buffer | legacy_rule_buffer_ratio |

Sáu tên còn lại không đổi. Đừng đổi raw CSV gốc cho giống canonical; logic mapping nằm trong contract/ingest. Finance chỉ có **L1_category_name_en, cost_ratio, shelf_life_days, waste_handling_cost_ratio**; không tự đổi sang **disposal_cost_ratio**.

### 5.3. Chạy V4 read-only validation trước

~~~powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only --json
.\.venv\Scripts\python.exe -m src.validate_source_registry --json
.\.venv\Scripts\python.exe -m src.ingest_landing
~~~

- **--metadata-only**: kiểm registry/contract, không yêu cầu raw file tồn tại.
- **validate ... --json**: preflight 7 CSV, kiểm path/hash/header/kiểu/số dòng/keys; chỉ đọc nguồn, không ghi warehouse.
- **ingest_landing** không có --execute: **dry-run/preflight** mặc định, không ghi.
- Validator exit **0** nếu hợp lệ, **1** với config lỗi, **2** với source lỗi. Xem log trước khi chạy bất kỳ thao tác ghi nào.

Các bất thường có bằng chứng cần **giữ nguyên, báo rõ**: Sales có 52 NULL trong sales, 52 NULL trong total_orders; 32 **cells** discount âm (27 type_0, 1 type_4, 4 type_6); Orders có 270 NULL precipitation và 270 NULL snow. Không coi NULL=0, không clip discount vào [0,1] hoặc drop row ngầm. Xử lý mỗi bất thường cho model thuộc quyết định của model owner.

### 5.4. Thử Landing ingestion trên DB CÔ LẬP (không phải production)

Trước khi chạy, **dừng Streamlit, đóng DBeaver**, bảo đảm đủ dung lượng RAM/ổ đĩa và tất cả CSV đã qua preflight. Tạo DuckDB test riêng; không dùng đường dẫn database chính:

~~~powershell
New-Item -ItemType Directory -Force -Path .\data\warehouse | Out-Null
.\.venv\Scripts\python.exe -m src.init_duckdb --database .\data\warehouse\rohlik_landing_dev.duckdb
.\.venv\Scripts\python.exe -m src.ingest_landing --execute --database .\data\warehouse\rohlik_landing_dev.duckdb --entered-by "developer:nguoi-tiep-nhan"
~~~

Nạp lần đầu đúng nguồn có thể trả trạng thái **COMPLETED**; chạy lại cùng nguồn/DB hợp lệ kỳ vọng **NO_OP** sau khi đối chiếu dữ liệu, provenance và metadata. **NO_OP không có nghĩa chỉ thấy đủ 14 bảng là xong.** Mọi action ghi theo transaction; lỗi phải rollback. Chạy trên một DB mới/fixture nhỏ trước khi dùng full 4M+ Sales rows.

Tài liệu V4-03 ghi một lần acceptance nguồn thật tại DB cô lập với 7 batch COMPLETED, 14 table loads/landing tables, 9 schemas; thời gian và bộ nhớ phụ thuộc máy. Exact reconciliation có thể tạo spill trên ổ đĩa và tiêu tốn tài nguyên. Đây là bằng chứng benchmark lịch sử, không cam kết máy nhận sẽ có cùng kết quả.

**Điểm chặn quan trọng:** cả **14 update_policy = PENDING_CONFIRMATION**. Production ingestion bị chặn cố ý. Không bypass gate, không tự chỉnh policy thành “approved”, không chạy --execute vào data/warehouse/rohlik.duckdb và không dùng --database trỏ Task08A dev DB. **Landing test không tạo STG/Core/Mart.**

### 5.5. Xem DB bằng DBeaver/SQL và đóng trước khi ghi

DBeaver là công cụ quan sát, không phải migration manager. Dùng read-only connection hoặc shared read-only helper khi app/CLI có thể hoạt động. Ví dụ query trên DB landing dev đã nạp:

~~~sql
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name LIKE 'src_%'
ORDER BY schema_name;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema LIKE 'src_%'
ORDER BY table_schema, table_name;

SELECT source_id, status, batch_id
FROM meta.source_batches
ORDER BY source_id;
~~~

Nếu chưa chạy ingest, các bảng sẽ chưa có; không chạy query rồi tự tạo thủ công bằng DBeaver. Batch current status canonical là **meta.source_batches.status**. **meta.batch_status_events** và **meta.entry_audit_events** dùng audit bất biến; không tự đoán bản mới nhất theo timestamp/UUID. Sau khi xong, ngắt kết nối DBeaver.

### 5.6. Phân biệt 3 database/loại dữ liệu

1. **data/warehouse/rohlik.duckdb:** warehouse local chính theo settings; hiện chưa được publish 5 reporting marts. Không ghi production kiểu thử nghiệm.
2. **data/warehouse/rohlik_landing_dev.duckdb** (tên ví dụ do người nhận tạo): DB cô lập dùng kiểm thử V4-03; chỉ có Landing/metadata, không thay thế kho chính.
3. **data/warehouse/rohlik_bootstrap_dev.duckdb:** DB lịch sử Task08A (6 Bronze + provisional projections); không đồng nhất với V4-03 và không tự reset/migrate.

Ngoài ra còn SQLite lịch sử **data/input.db** theo hạ tầng cũ; không phải tầng nhập liệu của kiến trúc local-first mới.

---

## 6. VẬN HÀNH DASHBOARD VÀ KIỂM TRA KẾT NỐI DATA

### 6.1. Workflow đúng hôm bàn giao

1. Chạy automated tests và xác minh admin credential.
2. Streamlit app/main.py có thể khởi chạy trước khi có data để kiểm navigation/readiness.
3. DE làm ingestion và chuẩn hóa/publish dữ liệu **ngoài UI**, trên DB thử nghiệm và có test.
4. Chỉ khi có 5 Mart hợp lệ trong warehouse chính, đóng các writer/client, chạy dashboard read-only để kiểm filter/KPI.
5. Với BT1–BT8, chỉ hiển thị kết quả sau khi model được owner bàn giao, schema/output được xác minh và dữ liệu publish đúng version.

### 6.2. Cơ chế bảo vệ hiện có

- **Authentication:** local admin_local, Argon2id, password policy, lockout/rate limiting, session phía server, idle timeout/logout; không phải SSO/production auth.
- **Reporting:** mọi read gọi require_admin; chỉ 5 Mart allowlisted; schema introspection, kiểm cột hợp lệ, bind parameter, query read-only, phân trang giới hạn (UI thường 250 rows, backend tối đa 500).
- **Warehouse:** không cho tùy tiện mở DB writable cùng Streamlit; có writer lock, transaction, backup, path guard và versioned metadata cho phần DE.
- **Lưu ý:** local admin auth không ngăn được người có quyền hệ điều hành truy cập trực tiếp file .duckdb. Không mô tả đây là bảo mật production/multiuser.

### 6.3. Lỗi phổ biến và nguyên nhân đúng

| Biểu hiện | Nguyên nhân thường gặp | Thao tác đầu tiên |
| --- | --- | --- |
| Clone repo lỗi/404 | Repo private, account chưa được cấp quyền | Xác minh account/permission; không dùng token chia sẻ |
| Python 3.11/3.14 hoặc pip sai venv | Nhiều interpreter | Chạy py -0p và dùng .venv\\Scripts\\python.exe |
| No module named ... | Chưa cài requirements vào đúng venv | python -m pip install -r requirements.txt bằng venv |
| Không activate PowerShell | Execution policy chặn Activate.ps1 | Gọi trực tiếp interpreter, không hạ policy hệ thống |
| Login thất bại trên máy clone mới | Thiếu users.json/password hoặc account disabled | scripts.create_user status, bàn giao secure store |
| TABLE_NOT_AVAILABLE | Mart chưa publish | Không tạo view giả; phát triển/publish DE thật |
| WAREHOUSE_NOT_READY | Thiếu DB/file đang bị khóa/không mở được | Kiểm DB path và client; không xóa DB/WAL |
| PENDING_MODEL | Thiếu output BT có kiểm định | Nhận model handover, không fake prediction |
| DuckDB lock | Streamlit/DBeaver/writer khác đang giữ file | Dừng/đóng client, chờ lock; không xóa .wal hoặc lock bừa |
| Port 8501 bận | Có Streamlit process khác | Kiểm Get-NetTCPConnection; không kill PID không xác định |
| Nguồn CSV fail preflight | Sai header/hash/type/row count/path | So với config/sources.yaml, xin source đúng phiên bản |
| Full-data ingest chậm/khó cấp RAM | Sales 4M+ rows, NO_OP EXCEPT ALL | Dùng DB cô lập, theo dõi tài nguyên, không bỏ kiểm tra chính xác |

Tham khảo troubleshooting đầy đủ trong README, docs/setup_tutorial.md, docs/duckdb_setup.md.

---

## 7. TÌNH TRẠNG CỤ THỂ: ĐÃ LÀM, CHƯA LÀM, CÒN RỦI RO

### 7.1. Đã có thể bàn giao dưới dạng code

- Source profiling/data dictionary/source mapping và kiểm tra dữ liệu; V4 registry 7 active sources; contract 14 tables/9 schema.
- Preflight chặt với hash, type, headers, key, duplicate và nguồn ASSUMED; các bất thường nguồn được ghi chứ không âm thầm chữa.
- Task08A provisional bootstrap để truy vết lịch sử; V4-02 DuckDB safety/metadata/backup/writer control.
- V4-03 Landing ingestion trên DB cô lập, batch metadata, idempotent NO_OP đối chiếu đầy đủ, rollback atomic; có synthetic regression và ghi nhận acceptance nguồn thật.
- Streamlit v3 auth/admin shell, 8 pages, ReportingService read-only, trạng thái readiness; support localhost, LAN opt-in được cấu hình.
- Pytest và GitHub Actions synthetic trên Windows/Python 3.13.

### 7.2. Chưa có hoặc chưa nghiệm thu — KHÔNG được tuyên bố hoàn thành

- 14 STG, 6 Core, 5 Mart chính thức trên warehouse; DQ gates end-to-end sau transform.
- Một pipeline.run thống nhất với init/refresh/models/all/status/evaluate và snapshot publication như bản thiết kế V4.
- Direct CSV upload/preview/confirm vào DuckDB, user entry, update/merge policy, soft Undo, phân quyền theo phòng ban. Tất cả **ngoài scope UI v3 hiện tại**.
- Tám model BT1–BT8 tích hợp, artifact/adapter/runner, 14 prediction outputs + 2 history, output contracts đã được owners xác nhận.
- Dashboard đưa ra kết quả kinh doanh thật từ Mart + Model, không chỉ readiness.
- Cloud production: MotherDuck, GitHub Actions làm scheduler, Streamlit Cloud; hiện không phải tiêu chí local.
- Fresh-machine **first-time admin provisioning không cần users.json**; script chỉ quản lý account có sẵn.
- Dependency lockfile và quy trình build tái lập chính xác giữa máy; xác minh trực tiếp UI đa trình duyệt/thiết bị và network firewall ở máy nhận.

### 7.3. Điểm chưa chốt về nghiệp vụ/dữ liệu

- Toàn bộ 14 update policies vẫn **PENDING_CONFIRMATION**; cần chính sách conflict, full-row/patch, retry và người có quyền Undo.
- Các trường Sales NULL, discount âm, weather NULL: mỗi BT phải phê duyệt xử lý, không “clean cho hết WARN”.
- Cần xác minh đơn vị và ý nghĩa đo lường các trường, đặc biệt **orders** (Orders CSV) khác **total_orders/order_index** từ SKU; tránh JOIN nhân dòng và leakage thời gian.
- Cost/HR assumptions cần được duyệt và phân tích sensitivity; HR 5 column renames đã được code/contracts xử lý, không đồng nghĩa các giả định đã chính xác thực tế.
- Bài toán BT4 có bất nhất schema phân vị giữa tài liệu V4 và handoff mẫu; không điền phân vị thiếu bằng tính toán tùy ý.
- Metadata v1 không có signed external audit ledger; kẻ có quyền sửa phối hợp cả source rows và metadata có thể vượt khả năng kiểm chứng; mutate-and-restore trong một lần read CSV là rủi ro tồn dư. Cần xác định mức rủi ro chấp nhận.

### 7.4. Quyết định phạm vi cần xác nhận với nhóm khi tiếp tục

Có **hai hướng phát triển**, không gộp như thể đã được duyệt cả hai:

**Hướng A — Tiếp tục từ điểm dừng V4-03 (được mô tả ở docs/v4_03_landing_handover.md):** tiếp nhận handoff BT1–BT8; mỗi model có adapter **read-only** đọc đúng batch Landing đã xác minh, thực hiện cleaning/feature engineering đặc thù có xác nhận, ghi output có version/validation; sau đó thiết kế publisher + reporting Mart cần cho dashboard. Không cần tự động triển khai toàn bộ STG/Core như thiết kế ban đầu nếu nhóm duyệt scope rút gọn.

**Hướng B — Xây đầy đủ kiến trúc V4 local-first ban đầu:** phát triển STG/Core/5 Mart, shared six frames, 21+ DQ checks, plug-in model orchestration, upload/undo và audit theo tài liệu V4. Đây là **mở rộng phạm vi**, cần quyết định mới về nguồn lực, model contract, tests và cách vận hành; không suy ra rằng code tương ứng đã có.

Khuyến nghị nghiệp vụ: nhóm phải chốt hướng A hay B trước khi giao người mới viết transform và model adapters, tránh xây hai luồng song song dùng hai nghĩa khác nhau cho grain/KPI.

---

## 8. ROADMAP PHÁT TRIỂN TIẾP — ƯU TIÊN CÓ ĐẦU RA KIỂM CHỨNG

| Ưu tiên | Việc cụ thể | Cần ai xác nhận | Done khi nào? |
| --- | --- | --- | --- |
| P0 | Onboard máy nhận, checkout main, CI/local pytest, đăng nhập admin, đọc safety runbooks | Người bàn giao + người nhận | Có log versions/tests/login (không lộ password) |
| P0 | Nhận đủ 7 nguồn đúng hash; chạy metadata/source preflight | DE + data owner | 7/7 active, 14 contracts, warnings được ghi |
| P0 | Chạy V4-03 trên DB cô lập và NO_OP, kiểm rows/batches/audit | DE | Test pass; DB chính/raw/Task08A không đổi |
| P0 | Nhận/kiểm chứng file BT1–BT8, môi trường ML, input/output/metrics | Mỗi model owner + integrator | Handoff checklist có link, version, người nhận, evidence |
| P0 | Chốt scope **A rút gọn** hay **B V4 full** và contract cho model/Mart | Nhóm trưởng, DE, Model, Dashboard | ADR/issue có quyết định rõ |
| P1 | Xây adapter input có verified dataset version/grain/null/as_of cho BT được duyệt | DE + model owner | Fixture parity + validation tests |
| P1 | Tạo output staging/validator/publisher theo run_id, xử lý fail atomic | Integrator + DE | Output lỗi bị chặn; không ghi prediction dở |
| P1 | Publish 5 reporting marts với định nghĩa business được duyệt | DE + Dashboard | Query chính xác, grain/key, DQ, UI chuyển DATA_READY |
| P1 | Kiểm UI trên máy người nhận với dữ liệu thật đã publish | Dashboard + QA | 8 pages, filter/aggregate/pagination; không fake model |
| P1 | Pin/lock dependencies cho runtime tương thích | Owner môi trường | Setup máy mới lặp lại được, CI xanh |
| P2 | Nếu nhóm chọn full V4: STG/Core/frames/orchestrator/entry/undo/role policies | Nhóm trưởng/DE | Test E2E độc lập theo design đã duyệt |
| P2 | Bảo mật triển khai nhiều máy/cloud, secret lifecycle, monitoring/scheduler | Hạ tầng/Bảo mật | Thiết kế server/multi-writer và nghiệm thu riêng |

**Quy tắc mỗi PR tiếp theo:** ghi thay đổi schema/key/grain/source, nguồn quyết định, ảnh hưởng tới tests và các model; chạy CI; không tự đánh dấu ASSUMED thành actual hay PENDING thành approved. Với nguồn/warehouse, test luôn dùng DB cô lập; chỉ áp migration lên DB thật sau backup và sự đồng ý của người sở hữu dữ liệu.

---

## 9. CÁCH LÀM VIỆC GIT VÀ BÀN GIAO THAY ĐỔI

~~~powershell
git status --short --branch
git remote -v
git switch main
git pull --ff-only origin main
git switch -c docs/or-feature-cua-ban
~~~

Tạo commit đúng phần thay đổi, không stage mọi thứ tùy tiện khi có file local:

~~~powershell
git add docs/<TEN_FILE_DUOC_SUA>.md
git diff --cached --check
git diff --cached --stat
git commit -m "docs: update Rohlik handover"
git push -u origin docs/or-feature-cua-ban
~~~

Tạo PR để review trước khi merge; không force-push main, không upload data/credentials. Khi sửa logic: chạy **python -m pytest -q**, pip check, diff check và kiểm fingerprint ảnh hưởng tới data. Không chỉnh source file trực tiếp nếu registry không cùng version. Đối với code của chủ model khác, chỉ nhận artifact/contract và tạo adapter sau khi đã review; đừng “sửa thuật toán cho khớp dashboard”.

---

## 10. CHECKLIST NGHIỆM THU BÀN GIAO HAI CHIỀU

### Người bàn giao cung cấp

- [ ] URL repo và quyền GitHub cho người nhận; ghi commit SHA/tag chuẩn.
- [ ] Bản hướng dẫn này, README, setup tutorial, V4-03 handover và tài liệu model.
- [ ] Xác nhận rõ phạm vi hiện tại **Landing V4-03 + Streamlit v3 shell**, không claim end-to-end.
- [ ] Nếu cần dashboard login: chuyển users.json **qua kênh bảo mật**, mật khẩu qua kênh khác; không viết vào repo.
- [ ] Nếu cần DE: chuyển 7 CSV gốc/assumed theo quy trình dữ liệu, kèm hash/source owner.
- [ ] Nếu cần dữ liệu dashboard: bàn giao warehouse **đã publish, nghiệm thu**, nếu có; không dùng DB landing dev thay thế.
- [ ] Danh sách BT notebooks/artifacts đã nhận/thực tế chưa nhận, người phụ trách và blocking decisions; không tự điền “done”.
- [ ] Log baseline CI; thông báo known anomalies, update_policy PENDING, limits CPU/RAM và quyền ghi.
- [ ] Mọi file nhạy cảm/binary không nằm trong Git.

### Người nhận phải tự chạy và ghi bằng chứng

- [ ] Clone đúng remote/private repo và main; lưu git log -1, git status sạch.
- [ ] Python 3.13 x64, venv riêng đúng interpreter, pip check và import thành công.
- [ ] Chạy pytest trên máy nhận không lỗi; lưu kết quả.
- [ ] Git ignore hoạt động với raw/auth/database/.env.
- [ ] Mở login shell Streamlit; nếu đã nhận credential thì đăng nhập/logout, 8 trang hoạt động.
- [ ] Phân biệt WAREHOUSE_NOT_READY/TABLE_NOT_AVAILABLE/DATA_READY/PENDING_MODEL.
- [ ] Nếu tiếp nhận DE: 7 file pass validation; V4-03 dry-run thành công.
- [ ] Nếu được phép test ingest: tạo DB cô lập, COMPLETED lần đầu, NO_OP lần sau, không sửa raw/production/Task08A.
- [ ] Xác minh policy chưa approved và chưa có STG/Core/Mart/models/entry/undo chính thức.
- [ ] Lưu versions, result tests, hash/data manifest và danh sách vấn đề cần hỏi owners **không chứa secret**.
- [ ] Nhóm thống nhất scope A hoặc B trước khi người nhận bắt đầu nhiệm vụ mới.

### Mẫu biên bản nghiệm thu ngắn (tự điền)

~~~text
Ngày bàn giao: ______________________
Người bàn giao / người nhận: ________
Repo/branch/commit: _________________
Windows / Python / DuckDB: __________
pip check: __________________________
pytest: _____________________________
GitHub CI run: ______________________
Login local (pass/fail/not provided): _
7 CSV registry (pass/not received): __
V4 Landing dry-run (pass/not run): ___
Isolated ingest & NO_OP (pass/not run):_
5 Mart readiness: ___________________
Model handover BT1–BT8: _____________
Risks / pending decisions: __________
Scope next phase A/B: _______________
Links evidence (không secret): ______
Người nhận xác nhận: ________________
~~~

---

## 11. NGUỒN KIỂM CHỨNG VÀ GIỚI HẠN CỦA TÀI LIỆU

- **Nguồn trực tiếp:** commit main **bc9bbd5**, README, cấu trúc git tree, code **src/**, **app/**, **config/**, **tests/**, các runbooks và PR #1.
- **Bằng chứng CI:** [Windows synthetic tests success tại bc9bbd5 — 207 passed](https://github.com/MckhueVanPhuc/rohlik-data-warehouse/actions/runs/39646101119).
- **Bằng chứng initial Landing:** [V4-03 landing handover](v4_03_landing_handover.md) và [PR #1](https://github.com/MckhueVanPhuc/rohlik-data-warehouse/pull/1). Real-data acceptance và benchmark là kết quả được ghi trong runbook/PR lịch sử; không phải thử nghiệm mới thực hiện trên máy người nhận trong lần soạn tài liệu này.
- **Thiết kế ban đầu:** [Rohlik Data Engineering Local-first V4](../Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md) mô tả mục tiêu rộng hơn code hiện tại; không dùng số test/feature mẫu của V4 làm bằng chứng repo đã có.
- **Bộ dữ liệu:** đường dẫn, định danh, counts và SHA phải kiểm lại với config/sources.yaml trên máy nhận; file raw và users.json không tồn tại trên GitHub.
- **Giới hạn kiểm chứng:** tài liệu này dựa vào source, docs, PR và CI trên GitHub; không trực tiếp thao tác máy người nhận, không sử dụng credential thật và không xác nhận rằng production data đã có 5 marts.

**Điều kiện bàn giao đạt:** người nhận chạy được code/tests và Streamlit shell theo đúng trạng thái thực tế; có khả năng kiểm nguồn và chạy Landing V4-03 **trên database cô lập**, hiểu rõ giới hạn, owner và next steps. Không yêu cầu trình diễn mô hình/BI end-to-end khi outputs chưa được bàn giao và kiểm định.
