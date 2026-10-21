# Rohlik Decision Hub — V4 Local-first

## Streamlit v3.0 — Admin-only dashboard

Ứng dụng chính thức tại `app/main.py` hiện là dashboard **admin-only, dashboard-only,
read-only**. Chỉ account cấu hình `admin_local` được đăng nhập; Argon2id, rate limiting,
opaque server-side sessions, timeout và logout được giữ nguyên. RBAC 7 role, Data Entry,
CSV Upload, Undo, CRUD và pipeline/model execution đã bị loại khỏi Streamlit.

Dashboard có đúng 8 trang và chỉ đọc năm allowlisted `mart.*` qua DuckDB read-only.
Warehouse/mart/model chưa sẵn sẽ hiển thị readiness tương ứng, không tạo dữ liệu giả và
không tự chạy pipeline. Xem [Dashboard Runbook](docs/dashboard_v3_runbook.md),
[Authentication Runbook](docs/authentication_runbook.md) và
[Local/LAN Runbook](docs/streamlit_local_lan_runbook.md).

```powershell
# Localhost mặc định
.\.venv\Scripts\python.exe -m streamlit run app/main.py

# LAN opt-in; HTTP chỉ dành cho mạng tin cậy/dữ liệu không nhạy cảm
.\scripts\start_streamlit_lan.ps1
```

Các mô tả Streamlit upload/write phía dưới là lịch sử DE/V4 hoặc kế hoạch 2.0 đã bị
Streamlit v3.0 supersede; chúng không mô tả runtime UI hiện tại.

Source of truth hiện hành: [Rohlik DE Local-first V4](Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md).
Task **V4-01 Source Registry & Business Contract Foundation** đã triển khai cấu hình,
validation và read-only preflight; chưa tạo/nạp Warehouse. Xem
[V4 Source Registry](docs/source_registry.md), [settings](config/settings.yaml),
[7-source registry](config/sources.yaml) và [14-table contract](config/contract.yaml).

Hướng dẫn setup và vận hành chính của Data Engineering:
[Living Setup Tutorial & Technical Handover](docs/setup_tutorial.md).
Tài liệu phân biệt hạ tầng đã kiểm chứng, xác nhận DBeaver của người dùng và roadmap chưa triển khai.

Dự án đã có Python, DuckDB infrastructure V4-02, V4 registry/contract/preflight,
V4-03 initial landing bootstrap và Task08A provisional historical bootstrap trong
DuckDB thử nghiệm riêng. V4-03 có thể tạo đúng 14 bảng landing trên một database cô lập
được chọn rõ ràng; production ingestion vẫn bị chặn. STG/Core/Mart, model integration,
direct-DuckDB CSV Upload và dashboard nghiệp vụ chưa được triển khai. SQLite
code/docs/tests được giữ làm lịch sử nhưng không còn thuộc critical path V4. Repository chính thức:
https://github.com/MckhueVanPhuc/rohlik-data-warehouse (`main`).

## Yêu cầu và tech stack

Kiến trúc V4 đã chốt: **Streamlit upload/preview/validate/confirm → DuckDB landing +
audit trong cùng transaction**. Backend phải kiểm quyền/schema/keys/types/DQ và giữ
lịch sử batch/soft undo. Initial historical CSV bootstrap đã được triển khai ở V4-03;
upload/entry của người dùng và soft undo vẫn **PLANNED**. [CSV Upload Contract cũ](docs/csv_upload_contract.md) đã được đánh dấu
superseded/legacy. Raw gồm 5 Kaggle CSV + 2 assumptions CSV, đều read-only.

- Windows 11, PowerShell, VS Code, Git.
- Python **3.13** (môi trường hiện tại: **3.13.15**) và virtual environment `.venv`.
- DuckDB, Pandas, PyArrow: công cụ xử lý dữ liệu cho giai đoạn sau.
- PyYAML, Pydantic: cấu hình và kiểm tra dữ liệu cho giai đoạn sau.
- Streamlit: giao diện dự kiến; Pytest: kiểm thử.
- Danh sách thư viện nằm trong `requirements.txt`; hiện không khóa phiên bản.

## Tạo môi trường trên Windows

Chạy trong thư mục gốc dự án. Chỉ tạo `.venv` nếu chưa có:

```powershell
py -3.13 -m venv .venv
```

Tại máy hiện tại, launcher `py` chưa nhận bản Python đã cài. Có thể dùng đường dẫn đã xác nhận trong cấu hình `.venv` (máy khác cần điều chỉnh đường dẫn):

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
```

Chọn `.venv\Scripts\python.exe` bằng **Python: Select Interpreter** trong VS Code. Có thể kích hoạt bằng ` .\.venv\Scripts\Activate.ps1`; nếu PowerShell chặn script, dùng trực tiếp Python trong `.venv` như các lệnh dưới đây.

## Cài thư viện

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Kiểm tra môi trường

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print('Virtual environment:', sys.prefix != sys.base_prefix)"
.\.venv\Scripts\python.exe -c "import duckdb, pandas, pyarrow, yaml, streamlit, pydantic, pytest; print('All imports OK')"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m streamlit --version
.\.venv\Scripts\python.exe -c "import duckdb; c=duckdb.connect(':memory:'); print(c.execute('SELECT 42').fetchone()); c.close()"
git --version
git status --short
git ls-files
git check-ignore -v -- .venv/Scripts/python.exe sales_test.csv data/raw/orders/train.csv data/warehouse/probe.duckdb .env .streamlit/secrets.toml
```

Truy vấn trên chỉ chạy trong bộ nhớ, không tạo database vật lý. Các đường dẫn `probe` chỉ dùng kiểm tra quy tắc ignore, không cần tạo file.

## Cấu trúc thư mục hiện tại

```text
rohlik-data-warehouse/
├── .git/                     # repository cục bộ
├── .venv/                    # môi trường Python, được ignore
├── config/
├── data/
│   ├── raw/
│   │   ├── orders/            # CSV gốc hiện có
│   │   └── sales/             # CSV gốc hiện có
│   ├── warehouse/
│   ├── published/
│   ├── backups/
│   └── exports/
├── docs/
├── logs/
├── src/
│   ├── models/
│   └── services/
├── tests/
├── .gitignore
├── README.md
└── requirements.txt
```

Thư mục gốc còn có CSV `sales_test.csv`, `test.csv`, `test_calendar.csv` cùng các tài liệu MD, DOCX và TSV có sẵn. CSV được ignore; dữ liệu và tài liệu gốc được giữ nguyên. Các thư mục trống không được Git lưu tự động.

## Phân công dự kiến sau khi A1 được phê duyệt

| Vai trò | Phạm vi dự kiến |
| --- | --- |
| E1 Data Engineer | Xác nhận nguồn dữ liệu, phụ trách xử lý dữ liệu và kho dữ liệu sau khi chốt yêu cầu. |
| Streamlit | Xây giao diện sử dụng đầu ra dữ liệu đã được thống nhất. |
| ML | Xác định bài toán và xây mô hình sau khi dữ liệu, mục tiêu và tiêu chí đánh giá được phê duyệt. |

Phạm vi A1 kết thúc ở setup và kiểm tra môi trường. Chờ phê duyệt trước khi chuyển sang phần tiếp theo.

## Quy tắc Git và dữ liệu cục bộ

`.gitignore` bỏ qua môi trường, cache, CSV, database, đầu ra dữ liệu, log và các tên file secrets phổ biến. File nhạy cảm có tên khác cần được rà soát trước khi stage; ignore không tự loại file đã được theo dõi khỏi Git history. Chỉ stage từng file đã kiểm tra. Remote `origin` trỏ tới repository chính thức nêu trên.

## SQLite Setup — SUPERSEDED/LEGACY

Không dùng SQLite làm tầng nhập liệu V4. Hạ tầng lịch sử dùng thư viện chuẩn `sqlite3`:
database cục bộ `data/input.db`, WAL,
busy timeout 5000 ms và foreign keys bật cho mỗi connection Python mới. Chưa tạo bảng
nghiệp vụ; schema chờ bằng chứng dữ liệu và quyết định nghiệp vụ được duyệt. Workflow
Data Contract BT1–BT8 đã RETIRED. Các phần mô tả A1 phía trên là mốc setup ban đầu.

```powershell
.\.venv\Scripts\python.exe -m src.init_sqlite
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.db.backup
```

Khởi tạo có thể chạy lại, không xoá dữ liệu. Module dùng chung cho backend/Streamlit
nằm tại `src/db/sqlite.py`; backup dùng SQLite Backup API và kiểm tra integrity.
Hướng dẫn DBeaver, transaction, backup và xử lý lỗi: [SQLite Setup](docs/sqlite_setup.md).
Database nằm trên máy chủ cục bộ; người dùng truy cập ứng dụng qua LAN.
Hoàn thành giai đoạn này thì chờ nghiệm thu, chưa chuyển sang Data Warehouse.

## DuckDB Infrastructure Setup

Đã có database rỗng `data/warehouse/rohlik.duckdb`, module đọc/ghi và transaction
riêng tại `src/db/duckdb.py`. Chưa tạo schema/bảng nghiệp vụ hoặc nạp CSV.

```powershell
.\.venv\Scripts\python.exe -m src.init_duckdb
.\.venv\Scripts\python.exe -m pytest tests/test_duckdb.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

CLI có thể chạy lại; file đã có được xác minh read-only. V4-02 bổ sung shared
cross-process writer lock, transaction guard, verified backup và metadata v1. Quy tắc
một tiến trình ghi, kiểm tra kết nối, backup offline và lỗi
thường gặp: [DuckDB Setup](docs/duckdb_setup.md). Streamlit dự kiến đọc published
snapshots; exporter và Warehouse Bronze/Silver/Gold/Mart chưa triển khai.

## Model Integration — hướng dẫn và bàn giao kỹ thuật (PLANNED)

- [Model Integration Guide BT1–BT8](docs/model_integration_contract.md): ranh giới DE/ML/người tích hợp, input/output, execution và phụ thuộc tham khảo chưa xác nhận.
- [Model Handover Checklist](docs/model_handover_checklist.md): notebook và toàn bộ file liên quan, thông tin môi trường và bảng theo dõi nhận bàn giao.

Đây là tài liệu kỹ thuật DRAFT; xác minh trực tiếp từ notebook/source/output/artifact,
không yêu cầu biểu mẫu Data Contract riêng. Chưa có Model Runner, chuyển đổi notebook,
training hoặc tích hợp Streamlit. Gold/Data Mart và dataset chính thức vẫn chờ xác nhận.

## Task 06 — Source Profiling, Dictionary và V3 Gap Analysis

Đã có CLI chỉ phân tích sáu CSV lịch sử bằng DuckDB `:memory:`, không mở SQLite
hoặc DuckDB nghiệp vụ, không sửa nguồn và không đọc CSV test Kaggle:

```powershell
.\.venv\Scripts\python.exe -m src.profile_sources
.\.venv\Scripts\python.exe -m pytest tests/test_profile_sources.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Summary JSON được ghi vào `data/exports/source_profiling/profile.json` (được ignore);
mọi đường dẫn nguồn tính từ vị trí project root. CLI báo SUCCESS sau kiểm tra hash
nguồn trước/sau; thiếu/lỗi nguồn báo FAILED/exit 1, không âm thầm bỏ qua.
Đã chạy đầy đủ trên dữ liệu hiện tại; 10 test profiling và 38 test toàn bộ PASS.

- [Data Dictionary: 64 cột thực tế](docs/data_dictionary.md).
- [Profiling Report và gap với v3](docs/data_profiling_report.md).
- [Mapping 14 Source Tables](docs/source_mapping.md): 12 bảng có source fields,
  Finance cost/HR workforce MISSING; tất cả schema nghiệp vụ còn cần xác nhận.
- [Data Quality rule specifications](docs/data_quality_rules.md): thiết kế cho pipeline sau này.

Ở mốc Task 06 chưa tạo Source Registry, Source Tables, ETL hoặc Warehouse nghiệp vụ.
Nội dung Task06 là evidence lịch sử; kiến trúc nhập liệu SQLite trong tài liệu cũ đã
được V4 thay bằng direct DuckDB transaction.

## Task V4-01 — Source Registry & Business Contract Foundation

[config/sources.yaml](config/sources.yaml) mô tả đúng 7 nguồn active (5 Kaggle + 2
assumptions); [config/contract.yaml](config/contract.yaml) mô tả đúng 14 bảng tại 9
schema `src_*`. Loader PyYAML/Pydantic và DuckDB `:memory:` preflight nằm tại
`src/config/`. Nó không mở/ghi warehouse và không tạo Source Tables.

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only --json
.\.venv\Scripts\python.exe -m pytest tests/test_source_registry.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

CLI mặc định kiểm đủ tồn tại/hash/BOM/header/type/row count/key/duplicates/ranges của
7 file; `--metadata-only` chỉ kiểm cấu hình. Finance/HR hiện diện và được đánh dấu
`ASSUMED`; toàn bộ update policy vẫn `PENDING_CONFIRMATION`. Task08A lịch sử dùng
adapter/config v1 riêng và vẫn chạy trên fixture. Hướng dẫn: [Source Registry V4](docs/source_registry.md)
và [config README](config/README.md). Direct DuckDB upload/entry vẫn PLANNED; YAML
không phải hệ thống phân quyền hoặc implementation ETL.

## Task V4-02/V4-03 — DuckDB Safety và Initial Landing Bootstrap

V4-02 cung cấp read-only connection, shared cross-process writer lock, transaction,
backup an toàn và metadata v1. V4-03 dùng hạ tầng đó để preflight 7 CSV và bootstrap
đúng 14 bảng tại 9 schema `src_*` vào database cô lập. CLI mặc định chỉ dry-run:

```powershell
.\.venv\Scripts\python.exe -m src.ingest_landing
```

Write cần `--execute --database <isolated.duckdb>` rõ ràng. Target production
`data/warehouse/rohlik.duckdb` bị từ chối trong V4-03; mọi `update_policy` vẫn
`PENDING_CONFIRMATION`. Rerun chỉ NO_OP sau khi metadata, batch-owned row counts và
nội dung canonical cùng khớp; dòng thuộc batch nhập tay khác không bị xóa hoặc thay thế.
Chưa có production load, user-facing upload/entry, STG/Core/Mart hoặc soft-undo command.
Handover và đề xuất dừng DE sau V4-03 được ghi riêng tại
[V4-03 Landing handover](docs/v4_03_landing_handover.md); tài liệu V4 gốc vẫn được giữ
nguyên để truy vết và đề xuất này không được coi là hoàn thành toàn bộ pipeline V4.

## Task 08A — Provisional Historical Source Bootstrap

Sáu CSV lịch sử của registry v1 có thể nạp nguyên trạng vào database thử nghiệm
`data/warehouse/rohlik_bootstrap_dev.duckdb`. Bootstrap tạo sáu Bronze raw tables,
12 Source projections trực tiếp và metadata run/lineage/DQ; không ghi SQLite hoặc
`data/warehouse/rohlik.duckdb`. Finance/HR `MISSING` chỉ là trạng thái lịch sử của
Task08A, không phải trạng thái production V4.

```powershell
.\.venv\Scripts\python.exe -m src.bootstrap_sources --dry-run
.\.venv\Scripts\python.exe -m src.bootstrap_sources --execute --provisional
.\.venv\Scripts\python.exe -m src.bootstrap_sources --validate-only
.\.venv\Scripts\python.exe -m pytest tests/test_bootstrap_sources.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Tại mốc hoàn thành Task 08A: dry run, execute, validate và rerun no-op đều SUCCESS;
21 test Task 08A và 109 test toàn bộ khi đó PASS. Báo cáo JSON/database đều được ignore. Xem
[Historical Source Bootstrap](docs/bootstrap_sources.md) cho bảng, row counts,
calendar rule, DBeaver queries, recovery và ranh giới Task 08B/09.

## Task 05 — Streamlit Infrastructure Smoke Test

Task 05 cung cấp cấu hình localhost-only ở `.streamlit/config.toml` và ứng dụng kiểm tra
read-only `app_smoke.py`. Ứng dụng xác minh runtime cùng `SELECT 42` trên SQLite/DuckDB;
không tạo database, schema, dữ liệu, dashboard nghiệp vụ hoặc chạy ETL/model.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app_smoke.py
.\.venv\Scripts\python.exe -m pytest tests/test_streamlit_smoke.py -q
```

Truy cập `http://127.0.0.1:8501`, dừng bằng `Ctrl+C`. Xem
[Streamlit Infrastructure Setup](docs/streamlit_setup.md) để biết trạng thái, xử lý lỗi
và ranh giới với ứng dụng chính thức. LAN/public hosting chưa bật.

## Quyết định quy trình và bước tiếp theo

Workflow Data Contract BT1–BT8 đã **RETIRED** từ 19/10/2026. Source Bootstrap không
còn phụ thuộc việc điền biểu mẫu riêng. DE sử dụng sáu CSV, profiling, dictionary,
mapping, registry, DQ rules và bằng chứng kỹ thuật thực tế. Việc bỏ workflow không
tự phê duyệt schema/mapping, không xác nhận model đã tích hợp và không bật ingestion.

Bước tiếp theo dự kiến là Task 08A — provisional historical bootstrap trong môi trường
thử nghiệm tách biệt, chỉ sau khi phạm vi được phê duyệt. Task 08B — finalization chính
thức vẫn chờ schema, mapping, chính sách dữ liệu và nguồn Finance/HR được duyệt.
