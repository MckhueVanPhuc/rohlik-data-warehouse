# Rohlik Decision Hub — setup môi trường (A1)

Hướng dẫn setup và vận hành chính của Data Engineering:
[Living Setup Tutorial & Technical Handover](docs/setup_tutorial.md).
Tài liệu phân biệt hạ tầng đã kiểm chứng, xác nhận DBeaver của người dùng và roadmap chưa triển khai.

Dự án chuẩn bị nền tảng cho công việc dữ liệu Rohlik Decision Hub. Đã có setup môi trường, SQLite/DuckDB infrastructure, profiling sáu CSV lịch sử và Source Registry/validator; dữ liệu nghiệp vụ chuẩn cuối cùng chưa được chốt. Pipeline, schema nghiệp vụ, Data Warehouse, giao diện và mô hình ML chưa được triển khai.

## Yêu cầu và tech stack

Phương thức nhập liệu chính đã thống nhất: nhân viên **upload CSV qua Streamlit**,
chọn phòng ban/bảng theo quyền, tải template, xem trước và xác nhận trước khi lưu.
Luồng dự kiến: **Streamlit → SQLite → DuckDB (Bronze/Silver/Gold/Mart) → Parquet Snapshots → Streamlit**.
Backend kiểm tra schema/keys/types/DQ; ghi records hợp lệ bằng INSERT/UPSERT theo
chính sách đã duyệt, audit và metadata batch cùng transaction. Sau lưu là
`PENDING_SYNC`; DE chủ động đồng bộ và chỉ publish snapshot sau kiểm định thành công.
Không bắt buộc form từng record. Toàn bộ chức năng này **PLANNED, chưa triển khai**.
Chi tiết và các chính sách còn chờ chốt: [CSV Upload Contract](docs/csv_upload_contract.md).
Giữ nguyên sáu CSV Kaggle gốc; Finance/HR chỉ nhận CSV sau khi schema/giá trị được duyệt.

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

`.gitignore` bỏ qua môi trường, cache, CSV, database, đầu ra dữ liệu, log và các tên file secrets phổ biến. File nhạy cảm có tên khác cần được rà soát trước khi stage; ignore không tự loại file đã được theo dõi khỏi Git history. Chỉ stage từng file đã kiểm tra. Setup không commit, push hay cấu hình remote.

## SQLite Setup

Hạ tầng SQLite dùng thư viện chuẩn `sqlite3`: database cục bộ `data/input.db`, WAL,
busy timeout 5000 ms và foreign keys bật cho mỗi connection Python mới. Chưa tạo bảng
nghiệp vụ; schema chờ Data Contract BT1–BT8. Các phần mô tả A1 phía trên là mốc setup ban đầu.

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

CLI có thể chạy lại; file đã có được xác minh read-only. Hiện có 14 ca DuckDB và
14 ca SQLite. Quy tắc một tiến trình ghi, kiểm tra kết nối, backup offline và lỗi
thường gặp: [DuckDB Setup](docs/duckdb_setup.md). Streamlit dự kiến đọc published
snapshots; exporter và Warehouse Bronze/Silver/Gold/Mart chưa triển khai.

## Model Integration — thiết kế và bàn giao (PLANNED)

- [Model Integration Contract BT1–BT8](docs/model_integration_contract.md): ranh giới DE/ML/người tích hợp, input/output, execution và phụ thuộc tham khảo chưa xác nhận.
- [Model Handover Checklist](docs/model_handover_checklist.md): notebook và toàn bộ file liên quan, thông tin môi trường và bảng theo dõi nhận bàn giao.

Đây là tài liệu thiết kế DRAFT; chưa có Model Runner, chuyển đổi notebook, training
hoặc tích hợp Streamlit. Gold/Data Mart và dataset chính thức vẫn chờ xác nhận.

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
Giữ nguyên kiến trúc CSV Upload → SQLite → DE batch DuckDB → Parquet → Streamlit.

## Task 07 — Source Registry & Configuration

[config/sources.yaml](config/sources.yaml) mô tả 14 bảng logic thuộc 9 phòng ban,
dựa trên metadata đã profile của sáu CSV. Loader PyYAML/Pydantic nằm tại `src/config/`.
Chỉ validate cấu hình, paths, keys/mappings/status và kiểm tra hash file nếu yêu cầu;
không nạp CSV, kết nối database hoặc tạo Source Tables.

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only --json
.\.venv\Scripts\python.exe -m pytest tests/test_source_registry.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

CLI mặc định kiểm sáu file tồn tại và hash khớp; `--metadata-only` không yêu cầu CSV
trên máy nhận. Config VALID có thể vẫn có quyết định pending. Finance cost/HR workforce
MISSING đúng thiết kế; mọi schema/mapping/upload approval vẫn PENDING_CONFIRMATION,
upload disabled. **Task 08: NOT_READY**, không phải cho phép bootstrap/ingestion.
Hướng dẫn cấu trúc, API, lỗi, phê duyệt và bàn giao: [Source Registry](docs/source_registry.md)
và [config README](config/README.md). CSV Upload→SQLite audit→DE batch→DuckDB→Parquet
vẫn PLANNED; YAML không phải hệ thống phân quyền hoặc implementation ETL.
