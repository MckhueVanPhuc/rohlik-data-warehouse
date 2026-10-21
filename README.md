# Rohlik Decision Hub — V4 Local-first

Rohlik Decision Hub là repository kết hợp Data Engineering V4 và ứng dụng Streamlit
v3.0 phục vụ dashboard nội bộ. Runtime Streamlit hiện tại là **admin-only,
dashboard-only và read-only**.

> Hướng dẫn này dành cho Windows 11, PowerShell và Python 3.13 64-bit. Người clone mới
> có thể cài môi trường, chạy test và mở ứng dụng chỉ bằng các bước bên dưới. Credential,
> raw data và DuckDB thật không nằm trên Git và phải được bàn giao riêng khi cần.

## Trạng thái hiện tại

### Streamlit v3.0

- Entry point chính thức: `app/main.py`.
- Chỉ username local `admin_local` được đăng nhập.
- Argon2id, rate limiting, opaque server-side sessions, idle timeout và logout.
- Đúng 8 dashboard pages.
- Chỉ đọc 5 reporting marts được allowlist qua DuckDB read-only.
- Không có 7-role RBAC, CSV Upload, Data Entry, Undo, CRUD hoặc pipeline/model execution.
- BT1–BT8 chưa sẵn sàng; UI hiển thị `PENDING_MODEL`, không tạo forecast giả.
- Localhost là mặc định; LAN chỉ bật thủ công sau khi auth local đã được nghiệm thu.

### Data Engineering V4

- Source registry V4: 7 active sources.
- Business contract: 14 landing tables trong 9 schema `src_*`.
- Có DuckDB safety layer, writer lock, transaction, backup và metadata.
- Có initial landing ingestion vào database cô lập.
- STG/Core/5 Mart chính thức và model adapters chưa hoàn tất.
- Production ingestion vẫn fail closed khi update policies còn chờ xác nhận.

### Dashboard readiness

| Trạng thái | Ý nghĩa |
| --- | --- |
| `WAREHOUSE_NOT_READY` | File warehouse chưa tồn tại hoặc không mở read-only được. |
| `TABLE_NOT_AVAILABLE` | Warehouse tồn tại nhưng mart của trang chưa được publish. |
| `DATA_READY` | Mart tồn tại; filter, aggregate và pagination đọc dữ liệu thật. |
| `PENDING_MODEL` | Output BT1–BT8 chưa được bàn giao/kiểm định. |

Warehouse chính hiện chưa có đủ 5 reporting marts. Việc ứng dụng hiển thị readiness
thay vì KPI là hành vi đúng, không phải lỗi setup.

## Ba mức sử dụng repository

| Mục tiêu | Chỉ cần Git? | Thành phần bổ sung |
| --- | --- | --- |
| Chạy code và test | Có | Không. Test dùng file/database tạm. |
| Mở màn hình login | Có | Không. |
| Đăng nhập dashboard | Không | `data/auth/users.json` và password `admin_local`. |
| Xem dashboard có dữ liệu | Không | Credential và `rohlik.duckdb` đã publish đủ marts. |
| Làm Data Engineering | Không | 7 raw sources đúng registry, bàn giao qua kênh riêng. |

## 1. Điều kiện máy nhận

### Bắt buộc

- Windows 11;
- PowerShell;
- Git for Windows;
- Python 3.13 64-bit;
- mạng để clone repository và tải dependencies;
- quyền đọc/ghi thư mục làm việc.

### Tùy chọn

- VS Code và Microsoft Python extension;
- DBeaver để kiểm tra DuckDB sau khi writer đã đóng;
- Codex hoặc công cụ phát triển khác, không bắt buộc cho runtime.

Kiểm tra công cụ:

```powershell
git --version
Get-Command git -ErrorAction Stop
Get-Command py -ErrorAction SilentlyContinue
Get-Command python -All -ErrorAction SilentlyContinue
where.exe python
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) { py -0p } else { Write-Output 'Python Launcher chưa được cài/nhận diện.' }
```

`py -0p` liệt kê các Python mà launcher nhận diện. Nếu `python --version` đang là 3.11,
3.12 hoặc 3.14, không cần gỡ phiên bản đó; cài thêm Python 3.13 64-bit và dùng riêng cho
repository này.

## 2. Clone repository

### Máy chưa có repository

```powershell
Set-Location -LiteralPath "$env:USERPROFILE\Documents"
git clone https://github.com/MckhueVanPhuc/rohlik-data-warehouse.git
Set-Location -LiteralPath .\rohlik-data-warehouse
git switch main
git pull --ff-only origin main
git status --short --branch
git log -1 --oneline
```

Kỳ vọng branch là `main` và working tree sạch. Nếu repository private, người nhận cần
được cấp quyền GitHub trước. Không lưu GitHub token trong repository, `.env`, tài liệu
hoặc script.

### Máy đã có repository

Không chạy `git clone` đè lên thư mục cũ. Mở đúng root rồi kiểm tra trước:

```powershell
# Thay đường dẫn ví dụ bằng vị trí repository thực tế.
Set-Location -LiteralPath 'C:\duong-dan\rohlik-data-warehouse'
Test-Path -LiteralPath .\.git
git remote -v
git status --short --branch
```

Nếu có thay đổi local, không pull/checkout đè lên chúng; commit, stash có chủ đích hoặc
trao đổi với người sở hữu thay đổi trước. Chỉ khi working tree sạch và remote đúng:

```powershell
git switch main
git pull --ff-only origin main
```

## 3. Chọn đúng Python

```powershell
py -0p
py -3.13 --version
py -3.13 -c "import sys, struct; print(sys.executable); print(sys.version); print('bits:', struct.calcsize('P') * 8)"
```

Chỉ tiếp tục khi output là Python `3.13.x` và `bits: 64`.

### Nếu máy chỉ có Python phiên bản khác

Giữ nguyên Python đang dùng cho dự án khác. Cài thêm Python 3.13 64-bit side-by-side từ
nguồn chính thức của Python, đóng terminal/VS Code cũ, mở lại và chạy `py -0p`. Không
thay interpreter toàn hệ thống nếu `py -3.13` đã hoạt động.

### Nếu không có `py` launcher

Kiểm tra vị trí cài theo user:

```powershell
$python313 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
Test-Path -LiteralPath $python313
& $python313 --version
& $python313 -c "import struct; print(struct.calcsize('P') * 8)"
```

Nếu Python nằm ở vị trí khác, dùng đường dẫn `python.exe` thực tế đã xác minh. Không dùng
Microsoft Store alias chỉ để vượt qua bước này.

## 4. Tạo virtual environment

### Clone mới, chưa có `.venv`

```powershell
py -3.13 -m venv .venv
```

Hoặc khi không có launcher:

```powershell
& $python313 -m venv .venv
```

Không copy `.venv` từ máy khác. Virtual environment chứa đường dẫn interpreter và binary
phụ thuộc máy cục bộ.

### Repository đã có `.venv`

Kiểm tra trước khi sử dụng:

```powershell
Test-Path -LiteralPath .\.venv\Scripts\python.exe
Get-Content -LiteralPath .\.venv\pyvenv.cfg
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys, struct; print(sys.executable); print(sys.base_prefix); print('bits:', struct.calcsize('P') * 8)"
```

Nếu không phải Python 3.13 64-bit, đóng process đang dùng venv và giữ bản cũ ngoài repo:

```powershell
$projectRoot = (Resolve-Path -LiteralPath .).Path
$venvPath = (Resolve-Path -LiteralPath .\.venv -ErrorAction Stop).Path
if ($venvPath -ne (Join-Path $projectRoot '.venv')) { throw 'Sai đường dẫn .venv; dừng thao tác.' }
$savedVenv = Join-Path $env:TEMP ("rohlik-venv-backup-" + [guid]::NewGuid().ToString('N'))
Move-Item -LiteralPath $venvPath -Destination $savedVenv
Write-Output "Venv cũ được giữ tại: $savedVenv"
py -3.13 -m venv .venv
```

Nếu không có `py`, thay dòng cuối bằng đường dẫn Python 3.13 đã xác minh.

### Activate và VS Code

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn activate, dùng trực tiếp `.venv\Scripts\python.exe`; không cần hạ
execution policy toàn máy.

Trong VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → chọn
`<repo>\.venv\Scripts\python.exe`, sau đó mở terminal mới.

Xác minh:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys, struct; print(sys.executable); print('venv:', sys.prefix != sys.base_prefix); print('bits:', struct.calcsize('P') * 8)"
.\.venv\Scripts\python.exe -m pip --version
```

Python và pip phải cùng nằm dưới `<repo>\.venv`.

## 5. Cài dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Kiểm tra import:

```powershell
.\.venv\Scripts\python.exe -c "import argon2, duckdb, pandas, plotly, pyarrow, yaml, streamlit, pydantic, pytest; print('All imports OK')"
.\.venv\Scripts\python.exe -m streamlit --version
.\.venv\Scripts\python.exe -c "import duckdb; c=duckdb.connect(':memory:'); print(c.execute('SELECT 42').fetchone()); c.close()"
```

`requirements.txt` hiện chưa khóa phiên bản. Nếu cần tái lập chính xác giữa nhiều máy,
lưu output `pip freeze` trong artifact bàn giao và cân nhắc bổ sung lockfile riêng.

### Ranh giới môi trường Machine Learning

`.venv` Python 3.13 ở root chỉ là môi trường đã nghiệm thu cho Streamlit, Data
Engineering và test hiện có. Không cài toàn bộ thư viện BT1–BT8 vào venv này.

Notebook của Data Science có thể được phát triển trên Google Colab/Linux với Python
3.10 hoặc 3.11. Các package như `prophet`, `xgboost`, `lightgbm`, `tensorflow`, `torch`,
`statsmodels`, `optuna` hoặc `pulp` phụ thuộc cụ thể vào phiên bản package, Python, hệ
điều hành, CPU/GPU và wheel được phát hành. Không giả định một package chạy trên Colab
sẽ cài được trên Python 3.13/Windows; phải kiểm tra theo từng model handover.

Nguyên tắc:

- không downgrade `.venv` root để chữa lỗi một model;
- không trộn site-packages của Streamlit/DE và ML;
- mỗi BT dùng môi trường riêng, đúng Python/OS đã được model owner xác nhận;
- nếu cần parity với Colab, ưu tiên môi trường Linux riêng như Colab hoặc WSL2 đã được
  nhóm phê duyệt, không ép cài vào Windows root venv;
- dashboard không import/chạy model; nó chỉ đọc output đã được kiểm định và publish;
- không thêm ML dependencies vào root `requirements.txt` trước khi có source, lock,
  artifact và test tái lập thực tế.

Ví dụ chỉ sau khi BT1 xác nhận dùng Python 3.11 trên Windows và các wheel tương thích:

```powershell
$mlEnv = Join-Path $env:USERPROFILE '.virtualenvs\rohlik-bt1-py311'
py -3.11 -m venv $mlEnv
& "$mlEnv\Scripts\python.exe" -m pip install --upgrade pip
& "$mlEnv\Scripts\python.exe" -m pip install -r .\models\bt1\requirements.txt
& "$mlEnv\Scripts\python.exe" -m pip check
```

Đường dẫn `models\bt1\requirements.txt` chỉ là contract kỳ vọng trong tương lai; không
chạy ví dụ khi model handover chưa cung cấp file thật. Nếu model chỉ chạy trên Linux,
không dùng lệnh Windows này.

Mỗi model owner phải bàn giao tối thiểu:

| Nhóm bằng chứng | Nội dung bắt buộc |
| --- | --- |
| Runtime | OS, Python exact version, CPU/GPU, CUDA nếu có. |
| Dependencies | File requirements/lock từ môi trường chạy thật và lệnh cài. |
| Source | Notebook/source revision, entry command, seed và cấu hình. |
| Input | Dataset version, schema, keys, grain, units, date/as-of và null policy. |
| Artifact | Model/preprocessor files, format, loader và checksum. |
| Output | Schema, keys, grain, horizon, units, allowed/null values. |
| Verification | Metrics, tolerance và một lần tái lập trên môi trường đích. |

BT1–BT8 hiện vẫn `PENDING_MODEL_HANDOVER`; chưa có môi trường ML nào được tuyên bố hỗ
trợ production trong repository.

## 6. Chạy test

Không cần credential, raw CSV hoặc database thật để chạy test:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Baseline tại lần cập nhật README là `207 passed`. Sau commit mới, số test có thể tăng;
điều kiện nghiệm thu là không có test fail.

Nếu Windows giữ lock thư mục temp cũ:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp_handover
```

Không xóa thư mục không xác định để chữa lỗi test.

## 7. File local không có trên Git

`.gitignore` cố ý loại các thành phần sau:

- `.venv/`, cache Python và pytest temp;
- `.env`, `.streamlit/secrets.toml`, private keys và credential phổ biến;
- `data/auth/`;
- `data/raw/`;
- `data/warehouse/` và mọi `*.duckdb`;
- backup, export, acceptance output và log;
- CSV nguồn.

Kiểm tra:

```powershell
git check-ignore -v -- `
  .venv/Scripts/python.exe `
  data/auth/users.json `
  data/raw/orders/train.csv `
  data/warehouse/rohlik.duckdb `
  .env `
  .streamlit/secrets.toml
```

Không sửa `.gitignore` để commit các file này. Credential, raw data và database phải đi
qua kênh bàn giao bảo mật/được phê duyệt.

## 8. Provision tài khoản `admin_local`

### Ràng buộc

- Username duy nhất: `admin_local`.
- Cấu hình không chứa secret: `config/auth.yaml`.
- Credential store: `data/auth/users.json`.
- CLI fail closed nếu account chưa tồn tại; không tự tạo hoặc reset admin.

Do `users.json` không nằm trên Git, clone mới chỉ mở được màn hình login nhưng chưa thể
đăng nhập.

### Bàn giao credential

Người phụ trách chuyển `data/auth/users.json` qua kênh bảo mật. Password được truyền qua
kênh khác. Không gửi file hoặc password qua commit, issue, screenshot hay log.

Trên máy nhận:

```powershell
New-Item -ItemType Directory -Force -Path .\data\auth | Out-Null
# Đặt users.json được bàn giao vào .\data\auth\users.json.
git check-ignore -v -- data/auth/users.json
.\.venv\Scripts\python.exe -m scripts.create_user status
```

Kỳ vọng output chỉ có username và enabled state, không có password hash. Sau khi nhận:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user change-password
```

Password được nhập bằng prompt ẩn. Các lệnh quản trị khác:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user disable
.\.venv\Scripts\python.exe -m scripts.create_user enable
.\.venv\Scripts\python.exe -m scripts.create_user status
```

Nếu muốn máy mới tự tạo admin mà không chuyển credential store, cần triển khai một
first-time bootstrap flow riêng; repository hiện chưa có flow này.

## 9. Chạy dashboard local

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Mở `http://127.0.0.1:8501` và đăng nhập bằng `admin_local`.

Checklist local:

- anonymous/direct URL chỉ thấy login;
- login/logout hoạt động;
- có đúng 8 pages;
- sidebar hiển thị `LOCAL`;
- không có upload, data entry, Undo, CRUD hoặc pipeline/model action;
- thiếu warehouse/mart/model được báo bằng readiness;
- không có KPI hoặc forecast giả.

Dừng bằng `Ctrl+C`. Không dùng `app_smoke.py`; đó là entry point lịch sử.

## 10. Raw data cho Data Engineering

Người chỉ chạy test/dashboard shell không cần raw data. Người làm Data Engineering cần
nhận đúng 7 active sources:

```text
data/raw/orders/train.csv
data/raw/sales/sales_train.csv
data/raw/sales/inventory.csv
data/raw/sales/calendar.csv
data/raw/sales/test_weights.csv
data/raw/assumptions/cost_params.csv
data/raw/assumptions/workforce_params.csv
```

`config/sources.yaml` là source of truth cho path, SHA-256, row count, headers, types,
business keys và checks. Không chỉnh raw CSV hoặc sửa registry để hợp thức hóa file khác.

Sau khi đặt file:

```powershell
git check-ignore -v -- data/raw/orders/train.csv
.\.venv\Scripts\python.exe -m src.validate_source_registry
.\.venv\Scripts\python.exe -m src.ingest_landing
```

Lệnh `src.ingest_landing` không có `--execute` chỉ preflight read-only.

`data/raw/orders/train_calendar.csv` thuộc Task08A lịch sử, không phải active source của
V4 pipeline. Chỉ bàn giao khi cần tái hiện workflow lịch sử.

## 11. DuckDB và reporting marts

Dashboard mặc định đọc `data/warehouse/rohlik.duckdb` bằng connection read-only và chỉ
cho phép năm object:

```text
mart.sales_orders_day
mart.ops_warehouse_day
mart.category_sku_day
mart.marketing_promo_day
mart.exec_kpi_month
```

### Initial landing ingestion

Dry-run:

```powershell
.\.venv\Scripts\python.exe -m src.ingest_landing
```

Execute chỉ được dùng với database cô lập đã khởi tạo rõ ràng:

```powershell
.\.venv\Scripts\python.exe -m src.init_duckdb `
  --database .\data\warehouse\rohlik_landing_dev.duckdb

.\.venv\Scripts\python.exe -m src.ingest_landing `
  --execute `
  --database .\data\warehouse\rohlik_landing_dev.duckdb `
  --entered-by "developer:<TEN_NGUOI_NHAN>"
```

V4-03 từ chối ghi vào production warehouse mặc định khi update policies còn
`PENDING_CONFIRMATION`. Đóng DBeaver và mọi DuckDB client trước khi chạy writer.

Landing tạo 14 `src_*` tables nhưng không tạo STG/Core/5 Mart. Không đổi tên
`rohlik_bootstrap_dev.duckdb` hoặc landing database thành production warehouse để đánh
lừa readiness. Dashboard chỉ hiển thị dữ liệu khi nhận được warehouse đã kiểm định hoặc
khi pipeline mart thật được triển khai.

Khi cập nhật warehouse:

1. Dừng Streamlit.
2. Đóng mọi database client.
3. Chạy DE pipeline độc lập.
4. Xác minh DQ và mart contract.
5. Khởi động lại Streamlit.

Không chạy writer/pipeline từ Streamlit UI.

## 12. LAN opt-in

Chỉ bật LAN sau khi login/logout đã pass trên localhost:

```powershell
.\scripts\start_streamlit_lan.ps1
```

Script chạy một foreground Streamlit process trên `0.0.0.0:8501`, đặt sidebar mode
`LAN` và không tự sửa Windows Firewall.

Tra IPv4 host:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Format-Table InterfaceAlias,IPAddress
```

Client cùng LAN mở `http://<HOST_IPV4>:8501`.

LAN dùng HTTP. Chỉ dùng mạng tin cậy và dữ liệu không nhạy cảm; không port-forward ra
Internet. Firewall phải do người quản trị phê duyệt và giới hạn `Private`/`LocalSubnet`.
Xem `docs/streamlit_local_lan_runbook.md`.

## 13. Cấu trúc repository

```text
rohlik-data-warehouse/
├── .streamlit/config.toml        # localhost-default, XSRF/CORS và theme
├── app/
│   ├── main.py                   # Streamlit entry point
│   ├── auth.py                   # login/logout và require_admin
│   ├── navigation.py             # đúng 8 pages
│   ├── common.py                 # readiness/dashboard renderer
│   ├── services/
│   │   ├── identity.py           # Argon2id, credential, session, rate limit
│   │   └── reporting.py          # 5-mart allowlist, DuckDB read-only
│   └── views/                    # 8 page renderers
├── config/
│   ├── auth.yaml                 # auth policy, không chứa secret
│   ├── sources.yaml              # 7-source registry
│   └── contract.yaml             # 14 landing-table contract
├── data/                         # local/ignored, không có sau clone
│   ├── auth/users.json
│   ├── raw/
│   └── warehouse/
├── docs/
│   └── setup_tutorial.md         # tutorial/handover đầy đủ
├── scripts/
│   ├── create_user.py
│   └── start_streamlit_lan.ps1
├── src/                          # Data Engineering và DB safety
├── tests/                        # test dùng fixtures/temp databases
└── requirements.txt              # dependencies chưa pin version
```

## 14. Troubleshooting

### Python mặc định không phải 3.13

```powershell
py -0p
Get-Command python -All -ErrorAction SilentlyContinue
where.exe python
```

Dùng `py -3.13` hoặc đường dẫn Python 3.13 thật. Không uninstall Python của dự án khác
và không sửa `pyvenv.cfg` thủ công.

### `No module named ...`

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
.\.venv\Scripts\python.exe -m pip --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Không dùng lệnh `pip` trần vì nó có thể thuộc Python global khác.

### Không tìm thấy DuckDB wheel

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"
```

Kỳ vọng Python 3.13.x và 64. Nếu vẫn lỗi, lưu log và kiểm tra proxy/package index; không
tự chuyển sang build source.

### PowerShell chặn `Activate.ps1`

Không cần activate:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

### Login thất bại

```powershell
Test-Path -LiteralPath .\data\auth\users.json
.\.venv\Scripts\python.exe -m scripts.create_user status
```

Nếu file thiếu, provision theo phần 8. Nếu disabled, dùng `enable`. Không sửa JSON/hash
thủ công và không dùng `change-password` để tạo account mới.

### Warehouse chưa sẵn sàng

```powershell
Test-Path -LiteralPath .\data\warehouse\rohlik.duckdb
```

File thiếu là trạng thái hợp lệ. Nếu file có nhưng mart thiếu, phải triển khai pipeline
mart hoặc nhận warehouse đã publish; không fallback sang raw CSV.

### Port 8501 đang được dùng

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8501
```

Xác định process hiện hữu. Không chạy nhiều Streamlit process cùng port và không kill
PID không rõ nguồn gốc.

### DuckDB bị lock

Dừng Streamlit và đóng DBeaver/client trước khi chạy writer. Không xóa `.duckdb.wal`
hoặc database để chữa lock.

### Khác dependency giữa hai máy

```powershell
.\.venv\Scripts\python.exe -m pip freeze
.\.venv\Scripts\python.exe -m pip check
```

Lưu output vào artifact bàn giao. Không commit `.venv`.

## 15. Checklist nghiệm thu máy nhận

- [ ] Clone đúng `origin/main`; working tree sạch.
- [ ] Python 3.13 64-bit và `.venv` local hoạt động.
- [ ] Python/pip đều trỏ vào `<repo>\.venv`.
- [ ] Requirements cài thành công; imports và `pip check` pass.
- [ ] Toàn bộ pytest pass.
- [ ] `users.json`, raw CSV và DuckDB đều được Git ignore.
- [ ] Nếu cần login: `admin_local` enabled và người nhận đã đổi password local.
- [ ] Localhost login/logout và đủ 8 pages hoạt động.
- [ ] Người nhận hiểu readiness của warehouse, marts và models.
- [ ] Nếu làm DE: 7 source files khớp registry và validation pass.
- [ ] Nếu bật LAN: auth local đã pass, firewall được duyệt, không expose Internet.

## 16. Tài liệu chính

- [Setup & Technical Handover](docs/setup_tutorial.md)
- [Dashboard v3 Runbook](docs/dashboard_v3_runbook.md)
- [Authentication Runbook](docs/authentication_runbook.md)
- [Local/LAN Runbook](docs/streamlit_local_lan_runbook.md)
- [Dashboard v3 Refactor Audit](docs/dashboard_v3_refactor_audit.md)
- [V4 Source Registry](docs/source_registry.md)
- [DuckDB Setup](docs/duckdb_setup.md)
- [V4-03 Landing Handover](docs/v4_03_landing_handover.md)
- [Historical Task08A Bootstrap](docs/bootstrap_sources.md)
- [Model Integration Guide](docs/model_integration_contract.md)
- [Model Handover Checklist](docs/model_handover_checklist.md)
- [V4 Architecture](Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md)

Các tài liệu Streamlit 2.0, SQLite upload/write và Task05 smoke app được giữ làm lịch sử.
Khi có mâu thuẫn, ưu tiên code/test hiện tại, README này, setup tutorial và các runbook
v3.0. Không suy ra tính năng production từ kế hoạch hoặc tài liệu lịch sử.

## 17. Quy tắc Git và bảo mật

- Không commit credential, password/hash, `.env`, raw data, database, WAL hoặc backup.
- Không force-push `main` cho quy trình bàn giao thông thường.
- Trước commit: chạy test, `pip check`, `git diff --check` và xem từng file staged.
- Dùng database tạm/cô lập cho test và Data Engineering development.
- Không mở DuckDB writer đồng thời với Streamlit/DBeaver reader trong MVP.
- Không expose Streamlit HTTP trực tiếp ra Internet.
- Không tạo dữ liệu forecast/model giả để che trạng thái chưa sẵn sàng.
