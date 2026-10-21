# Rohlik Decision Hub — Setup & Technical Handover

> Tài liệu hiện hành cho Streamlit v3.0 và Data Engineering V4. Các kế hoạch
> Streamlit 2.0 về 7-role RBAC, CSV Upload, Data Entry, Undo, CRUD và chạy pipeline
> từ UI đã bị thay thế. Không dùng các tài liệu lịch sử đó để suy ra runtime hiện tại.

**Cập nhật:** 22/10/2026

**Nền tảng chuẩn:** Windows 11 · PowerShell · Python 3.13 64-bit

**Repository:** `https://github.com/MckhueVanPhuc/rohlik-data-warehouse` · nhánh `main`

## 1. Hiện trạng và phạm vi bàn giao

Rohlik Decision Hub v3.0 là ứng dụng Streamlit:

- dashboard-only và read-only;
- chỉ tài khoản local `admin_local` được đăng nhập;
- giữ Argon2id, rate limiting, server-side session, idle timeout và logout;
- có đúng 8 trang dashboard;
- chỉ đọc năm reporting mart được allowlist qua DuckDB read-only;
- không có upload, nhập liệu, Undo, CRUD, refresh/init pipeline hoặc chạy model từ UI;
- không dựng KPI, forecast hoặc dữ liệu model giả khi BT1–BT8 chưa sẵn sàng.

Data Engineering V4 hiện có source registry, contract, DuckDB safety layer và initial
landing ingestion. STG/Core/Mart chính thức và model BT1–BT8 chưa hoàn tất. Vì vậy
dashboard chạy được ngay sau khi có credential, nhưng có thể chỉ hiển thị readiness:

- `WAREHOUSE_NOT_READY`: chưa có/mở được warehouse;
- `TABLE_NOT_AVAILABLE`: warehouse có nhưng mart của trang chưa được publish;
- `DATA_READY`: mart tồn tại và có thể đọc bằng query allowlisted;
- `PENDING_MODEL`: output model chưa được kiểm định.

### Ba mức bàn giao

| Mức | Cần gì ngoài Git | Kết quả |
| --- | --- | --- |
| Code và test | Không | Cài dependencies và chạy toàn bộ pytest. |
| Dashboard shell | Credential store local | Đăng nhập, xem đủ 8 trang và readiness states. |
| Dashboard có dữ liệu | Credential store và DuckDB đã publish đủ mart | Xem filter, aggregate, chart và bảng phân trang trên dữ liệu thật. |

Không cần raw CSV hoặc DuckDB để chạy test vì test sử dụng thư mục/database tạm.

## 2. Những file không có trên Git

Các thành phần sau cố ý bị `.gitignore` loại khỏi repository:

- `.venv/`;
- `.env`, `.streamlit/secrets.toml` và các secret/key;
- `data/auth/users.json`;
- `data/raw/`;
- `data/warehouse/*.duckdb` và WAL;
- `data/backups/`, `data/exports/`, `data/acceptance/`, log và pytest temp.

Không sửa `.gitignore` để đưa chúng lên Git. Credential, raw data và database chỉ được
bàn giao qua kênh bảo mật/được phê duyệt, với quyền truy cập tối thiểu.

## 3. Điều kiện máy nhận

### Bắt buộc

- Windows 11 và PowerShell;
- Git for Windows;
- Python 3.13 64-bit;
- quyền đọc/ghi thư mục repository;
- mạng để clone và tải package Python.

### Tùy chọn

- VS Code và Microsoft Python extension;
- DBeaver để kiểm tra DuckDB thủ công sau khi writer đã đóng;
- Codex hoặc công cụ phát triển khác, không bắt buộc cho runtime.

Kiểm tra:

```powershell
git --version
Get-Command git -ErrorAction Stop
Get-Command py -ErrorAction SilentlyContinue
Get-Command python -All -ErrorAction SilentlyContinue
where.exe python
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) { py -0p } else { Write-Output 'Python Launcher chưa được cài/nhận diện.' }
```

`py -0p` liệt kê các interpreter mà Python Launcher nhận diện. Việc `python --version`
trả 3.11, 3.12, 3.14 hoặc một Microsoft Store alias không có nghĩa phải gỡ phiên bản
đó; dự án chỉ cần cài thêm Python 3.13 64-bit và tạo `.venv` bằng đúng interpreter.

Không dùng Python global để cài package dự án. Không copy `.venv` từ máy khác vì venv
chứa đường dẫn tuyệt đối và phụ thuộc hệ điều hành/interpreter cục bộ.

### Ma trận quyết định Python

| Tình trạng máy nhận | Xử lý |
| --- | --- |
| `py -3.13 --version` thành công | Dùng `py -3.13 -m venv .venv`; bỏ qua phiên bản mà lệnh `python` mặc định trỏ tới. |
| Chỉ có Python 3.11/3.12/3.14 | Giữ nguyên bản đang dùng cho dự án khác; cài thêm Python 3.13 64-bit side-by-side rồi mở terminal mới. |
| Không có `py`, nhưng biết đường dẫn Python 3.13 | Gọi trực tiếp đường dẫn `python.exe` đã xác minh để tạo `.venv`. |
| `python` mở Microsoft Store hoặc không chạy | Không dùng alias đó; dùng `py -3.13` hoặc đường dẫn installer thật. |
| Có `.venv` cũ dùng sai Python | Không cài đè package; chuyển venv cũ ra ngoài repository rồi tạo `.venv` mới. |
| Chỉ có Python 32-bit | Cài thêm Python 3.13 64-bit; DuckDB/data workload không được nghiệm thu trên 32-bit. |

Tải Python từ nguồn chính thức của Python và chọn installer Windows 64-bit. Sau khi cài,
đóng terminal/VS Code cũ và mở lại để launcher nhận interpreter mới. Không cần đổi
`PATH` toàn máy nếu `py -3.13` hoạt động.

## 4. Clone source từ `main`

```powershell
Set-Location -LiteralPath "$env:USERPROFILE\Documents"
git clone https://github.com/MckhueVanPhuc/rohlik-data-warehouse.git
Set-Location -LiteralPath .\rohlik-data-warehouse
git switch main
git pull --ff-only origin main
git status --short --branch
git log -1 --oneline
```

Kỳ vọng working tree sạch và branch là `main`. Nếu repository private, người nhận cần
được cấp quyền GitHub trước; không gửi token qua chat hoặc lưu token trong repository.

Nếu máy đã có repository, không clone/ghi đè thư mục cũ. Mở root, chạy `git remote -v`
và `git status --short --branch`. Khi có thay đổi local, phải bảo toàn chúng trước;
chỉ chạy `git switch main` và `git pull --ff-only origin main` khi working tree sạch.

## 5. Chọn đúng Python và tạo virtual environment

### 5.1 Kiểm tra interpreter trước khi tạo venv

```powershell
py -0p
py -3.13 --version
py -3.13 -c "import sys, struct; print(sys.executable); print(sys.version); print('bits:', struct.calcsize('P') * 8)"
```

Chỉ tiếp tục nếu output là Python `3.13.x` và `bits: 64`. Nếu máy đang dùng Python khác
cho dự án khác, không uninstall và không thay interpreter của dự án đó.

### 5.2 Trường hợp clone mới, chưa có `.venv`

Từ root repository:

```powershell
py -3.13 -m venv .venv
```

Nếu Python launcher không tìm thấy 3.13, kiểm tra bản cài theo user:

```powershell
$python313 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
Test-Path -LiteralPath $python313
& $python313 --version
& $python313 -m venv .venv
```

Nếu Python nằm ở vị trí khác, dùng đường dẫn thực tế đã xác minh. Không dùng nhầm
Microsoft Store alias hoặc phiên bản Python khác chỉ để vượt qua bước này.

### 5.3 Trường hợp đã có `.venv`

Kiểm tra trước, không mặc định venv cũ còn hợp lệ:

```powershell
Test-Path -LiteralPath .\.venv\Scripts\python.exe
Get-Content -LiteralPath .\.venv\pyvenv.cfg
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys, struct; print(sys.executable); print(sys.base_prefix); print('bits:', struct.calcsize('P') * 8)"
```

Nếu venv không dùng Python 3.13 64-bit hoặc trỏ tới interpreter đã bị gỡ, đóng mọi
terminal/process đang dùng nó. Giữ bản cũ bên ngoài repository trước khi tạo lại:

```powershell
$projectRoot = (Resolve-Path -LiteralPath .).Path
$venvPath = (Resolve-Path -LiteralPath .\.venv -ErrorAction Stop).Path
if ($venvPath -ne (Join-Path $projectRoot '.venv')) { throw 'Sai đường dẫn .venv; dừng thao tác.' }
$savedVenv = Join-Path $env:TEMP ("rohlik-venv-backup-" + [guid]::NewGuid().ToString('N'))
Move-Item -LiteralPath $venvPath -Destination $savedVenv
Write-Output "Venv cũ được giữ tại: $savedVenv"
py -3.13 -m venv .venv
```

Nếu máy không có `py` launcher, thay dòng cuối bằng đường dẫn Python 3.13 đã xác minh ở
phần 5.2. Không dùng Python khác với lý do chỉ để tạo được venv.

Không chuyển source, data hoặc credential cùng venv. Khi môi trường mới đã được nghiệm
thu, người nhận tự quyết định thời điểm dọn bản backup trong `%TEMP%`.

### 5.4 Activate và chọn interpreter trong VS Code

Có thể activate:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu execution policy chặn activate, dùng trực tiếp `.venv\Scripts\python.exe` trong
mọi lệnh; không cần hạ policy của toàn máy.

Trong VS Code:

1. `Ctrl+Shift+P` → **Python: Select Interpreter**.
2. Chọn `Enter interpreter path`.
3. Chọn `<repo>\.venv\Scripts\python.exe`.
4. Đóng terminal cũ và tạo terminal mới.

Không dựa riêng vào chữ `(.venv)` trên prompt; luôn kiểm tra executable thực tế.

Xác minh interpreter:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import sys, struct; print(sys.executable); print('venv:', sys.prefix != sys.base_prefix); print('bits:', struct.calcsize('P') * 8)"
```

Kỳ vọng Python 3.13.x, `venv: True`, `bits: 64`.

Kiểm tra pip cũng thuộc cùng venv:

```powershell
.\.venv\Scripts\python.exe -m pip --version
```

Đường dẫn trong output phải nằm dưới `<repo>\.venv\`. Nếu pip trỏ ra ngoài repository,
dừng cài package và sửa interpreter trước.

## 6. Cài dependencies

`requirements.txt` hiện chưa khóa phiên bản. Người nhận phải lưu output version nếu
cần tái lập chính xác môi trường hoặc điều tra khác biệt giữa hai máy.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Xác minh import chính:

```powershell
.\.venv\Scripts\python.exe -c "import argon2, duckdb, pandas, plotly, pyarrow, yaml, streamlit, pydantic, pytest; print('All imports OK')"
.\.venv\Scripts\python.exe -m streamlit --version
```

Nếu DuckDB không có wheel, xác minh lại Python 3.13 64-bit trước khi thử giải pháp khác.
Không build package native hoặc đổi Python ngoài phạm vi dự án mà chưa ghi nhận lý do.

### 6.1 Tách môi trường Machine Learning khỏi Streamlit/DE

Root `.venv` Python 3.13 chỉ dành cho Streamlit, Data Engineering và test hiện có.
Không dùng nó làm môi trường chung cho BT1–BT8.

Các notebook Data Science có thể được làm trên Google Colab/Linux và Python 3.10 hoặc
3.11. Khả năng cài `prophet`, `xgboost`, `lightgbm`, `tensorflow`, `torch`,
`statsmodels`, `optuna`, `pulp` hay package khác phụ thuộc phiên bản cụ thể, Python,
OS, kiến trúc CPU/GPU và wheel sẵn có. Việc chạy được trên Colab không chứng minh chạy
được trên Python 3.13/Windows.

Quy tắc bàn giao:

1. Không downgrade hoặc làm bẩn `.venv` root để chạy model.
2. Mỗi BT dùng venv/Conda/Colab/WSL2 riêng theo môi trường đã được model owner xác nhận.
3. Không thêm ML package vào root `requirements.txt` trước khi model thực sự được nhận.
4. Model owner phải cung cấp OS, Python exact version, dependency lock, CPU/GPU/CUDA,
   notebook/source revision, entry command, seed và config.
5. Phải bàn giao input schema/grain/as-of/null policy, artifact + checksum, output schema,
   metrics và reproduction tolerance.
6. Dashboard không chạy model; chỉ đọc output đã kiểm định từ reporting mart.

Ví dụ tạo môi trường riêng khi BT1 đã xác nhận Python 3.11 và hỗ trợ Windows:

```powershell
$mlEnv = Join-Path $env:USERPROFILE '.virtualenvs\rohlik-bt1-py311'
py -3.11 -m venv $mlEnv
& "$mlEnv\Scripts\python.exe" -m pip install --upgrade pip
& "$mlEnv\Scripts\python.exe" -m pip install -r .\models\bt1\requirements.txt
& "$mlEnv\Scripts\python.exe" -m pip check
```

Đây chỉ là mẫu cấu trúc. `models\bt1\requirements.txt` chưa tồn tại và không được tự
tạo bằng suy đoán. Nếu model gốc chỉ hỗ trợ Linux, tái lập trong Colab/WSL2/Linux riêng
đã được phê duyệt, thay vì ép package vào Windows.

Trạng thái hiện tại: BT1–BT8 đều `PENDING_MODEL_HANDOVER`; repository chưa tuyên bố môi
trường ML production nào đã được hỗ trợ hoặc tái lập.

## 7. Chạy kiểm thử trước khi nhận bàn giao

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Baseline tại lần cập nhật tài liệu này là `207 passed`. Số test có thể tăng sau các
commit mới; điều kiện nghiệm thu là không có test fail, không phải cố giữ đúng con số.

Nếu Windows giữ lock thư mục pytest cũ, không xóa tùy tiện thư mục không xác định.
Có thể dùng một basetemp mới nằm trong repository:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp_handover
```

`.pytest_tmp*` đã được ignore.

## 8. Provision credential local

### 8.1 Ràng buộc hiện tại

Ứng dụng chỉ chấp nhận username `admin_local`, cấu hình tại `config/auth.yaml`.
Credential store là `data/auth/users.json` và không có trên Git.

CLI quản trị hiện tại fail closed: nếu `admin_local` chưa tồn tại, CLI không tự tạo
account và không reset password. Vì vậy clone mới chưa thể đăng nhập chỉ bằng source.

### 8.2 Cách bàn giao hiện tại

Người phụ trách chuyển riêng file `data/auth/users.json` qua kênh bảo mật. File chứa
password hash, không chứa plaintext password, nhưng vẫn phải coi là credential nhạy cảm.

Trên máy nhận:

```powershell
New-Item -ItemType Directory -Force -Path .\data\auth | Out-Null
# Đặt users.json đã nhận vào .\data\auth\users.json bằng quy trình bảo mật của nhóm.
git check-ignore -v -- data/auth/users.json
.\.venv\Scripts\python.exe -m scripts.create_user status
```

Kỳ vọng chỉ in username và enabled state, không in role hoặc hash. Truyền mật khẩu ban
đầu qua kênh khác với kênh chuyển file. Người nhận nên đặt password local riêng:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user change-password
```

Lệnh dùng prompt ẩn. Việc đổi password trên bản credential local của máy nhận không sửa
credential store trên máy bàn giao.

Các lệnh vận hành khác:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user disable
.\.venv\Scripts\python.exe -m scripts.create_user enable
.\.venv\Scripts\python.exe -m scripts.create_user status
```

Không gửi password/password hash trong issue, commit, screenshot hoặc log. Không mount
`data/auth/` qua network share. Nếu muốn fresh-machine provisioning không cần chuyển
credential store, phải triển khai và review một bootstrap flow riêng; repository hiện
chưa có flow đó.

## 9. Chạy dashboard local

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Mở `http://127.0.0.1:8501`, đăng nhập bằng `admin_local`, rồi xác minh:

- anonymous/direct URL chỉ thấy login;
- đăng nhập thành công với credential local;
- có đúng 8 trang;
- không có Entry, Upload, Undo, CRUD, refresh/pipeline/model action;
- logout thu hồi session hiện tại;
- sidebar hiển thị `LOCAL`;
- warehouse/mart/model thiếu được báo bằng readiness, không có dữ liệu giả.

Dừng server bằng `Ctrl+C`. Không chạy `app_smoke.py`; đó là entry point lịch sử.

## 10. Dữ liệu nguồn V4

Raw data không cần để chạy dashboard shell hoặc test. Người làm Data Engineering mới
cần nhận đúng bảy active source qua kênh dữ liệu được phê duyệt:

```text
data/raw/orders/train.csv
data/raw/sales/sales_train.csv
data/raw/sales/inventory.csv
data/raw/sales/calendar.csv
data/raw/sales/test_weights.csv
data/raw/assumptions/cost_params.csv
data/raw/assumptions/workforce_params.csv
```

`config/sources.yaml` là source of truth cho path, SHA-256, row count, header, types,
business keys và checks. Không đổi tên, chỉnh sửa hoặc normalize raw CSV trên máy nhận.

Sau khi đặt file:

```powershell
git check-ignore -v -- data/raw/orders/train.csv
.\.venv\Scripts\python.exe -m src.validate_source_registry
.\.venv\Scripts\python.exe -m src.ingest_landing
```

`src.ingest_landing` không có `--execute` chỉ chạy preflight read-only. Nếu hash/header/
row count không khớp, dừng và xác minh lại gói dữ liệu; không sửa registry để hợp thức
hóa một file khác.

### Historical source

`data/raw/orders/train_calendar.csv` chỉ thuộc adapter Task08A lịch sử, không phải active
source của V4 business pipeline. Chỉ bàn giao nếu người nhận cần tái hiện Task08A.

## 11. DuckDB, landing và reporting marts

### 11.1 Dashboard mặc định đọc gì

Dashboard đọc `data/warehouse/rohlik.duckdb` bằng connection read-only và chỉ cho phép:

```text
mart.sales_orders_day
mart.ops_warehouse_day
mart.category_sku_day
mart.marketing_promo_day
mart.exec_kpi_month
```

Warehouse chính tại thời điểm bàn giao chưa có năm mart này. Không đổi tên
`rohlik_bootstrap_dev.duckdb` thành `rohlik.duckdb`: bootstrap database không có contract
reporting mart mà UI yêu cầu.

### 11.2 Initial landing ingestion

V4-03 có thể nạp 14 landing tables vào một DuckDB cô lập được chỉ định rõ ràng. Dry-run:

```powershell
.\.venv\Scripts\python.exe -m src.ingest_landing
```

Execute là thao tác ghi và bắt buộc chỉ định database:

```powershell
.\.venv\Scripts\python.exe -m src.init_duckdb `
  --database .\data\warehouse\rohlik_landing_dev.duckdb

.\.venv\Scripts\python.exe -m src.ingest_landing `
  --execute `
  --database .\data\warehouse\rohlik_landing_dev.duckdb `
  --entered-by "developer:<TEN_NGUOI_NHAN>"
```

`--execute` chỉ chấp nhận một DuckDB cô lập đã được khởi tạo rõ ràng; nó không tự tạo
target còn thiếu và từ chối warehouse production mặc định. Chỉ chạy execute sau khi
preflight thành công, raw sources đã được phê duyệt và không có DuckDB client khác giữ
file. Không trỏ thử nghiệm vào warehouse chính thức. Đọc
`docs/v4_03_landing_handover.md` trước khi thực thi.

Landing ingestion không tạo STG/Core/Mart. Muốn dashboard hiển thị `DATA_READY`, người
tiếp nhận phải triển khai pipeline mart hoặc nhận một `rohlik.duckdb` đã được kiểm định
và bàn giao nhất quán. Không tạo mart/dữ liệu giả chỉ để làm dashboard trông hoàn chỉnh.

### 11.3 Cập nhật warehouse cho dashboard

MVP không hỗ trợ concurrent writer:

1. Dừng Streamlit.
2. Đóng DBeaver/client đang mở database.
3. Chạy DE pipeline độc lập.
4. Xác minh DQ và mart contract.
5. Khởi động lại Streamlit.

Không chạy writer hoặc pipeline subprocess từ Streamlit UI.

## 12. LAN opt-in

Localhost là mặc định. Chỉ bật LAN sau khi auth đã được nghiệm thu local:

```powershell
.\scripts\start_streamlit_lan.ps1
```

Script bind một foreground process vào `0.0.0.0:8501`, không tự sửa firewall. Xem IPv4:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Format-Table InterfaceAlias,IPAddress
```

Client cùng LAN mở `http://<HOST_IPV4>:8501`. LAN hiện dùng HTTP, chỉ phù hợp mạng tin
cậy và dữ liệu không nhạy cảm. Không port-forward ra Internet. Firewall rule phải được
người quản trị duyệt, giới hạn `Private` và `LocalSubnet`; xem hướng dẫn chi tiết tại
`docs/streamlit_local_lan_runbook.md`.

## 13. Cấu trúc quan trọng

```text
rohlik-data-warehouse/
├── .streamlit/config.toml        # localhost-default, theme và XSRF/CORS
├── app/
│   ├── main.py                   # Streamlit entry point
│   ├── auth.py                   # require_admin, login/logout
│   ├── navigation.py             # đúng 8 pages
│   ├── common.py                 # dashboard/readiness renderer
│   ├── services/
│   │   ├── identity.py           # Argon2id, credentials, sessions, rate limit
│   │   └── reporting.py          # 5-mart allowlist, DuckDB read-only
│   └── views/                    # 8 page renderers
├── config/
│   ├── auth.yaml                 # username/path/policy, không chứa secret
│   ├── sources.yaml              # 7 active raw sources
│   └── contract.yaml             # 14 landing-table contract
├── data/                         # local/ignored; không có sau clone
│   ├── auth/users.json
│   ├── raw/
│   └── warehouse/
├── scripts/
│   ├── create_user.py            # quản lý admin hiện hữu, không bootstrap
│   └── start_streamlit_lan.ps1
├── src/                          # Data Engineering pipeline và DB safety
├── tests/                        # unit/integration/Streamlit tests
└── requirements.txt              # dependencies chưa pin version
```

## 14. Troubleshooting

### Máy đang dùng phiên bản Python khác

```powershell
py -0p
Get-Command python -All -ErrorAction SilentlyContinue
where.exe python
```

- Nếu đã có Python 3.13 64-bit: tạo venv bằng `py -3.13`, bất kể `python` mặc định là bản nào.
- Nếu chưa có: cài thêm 3.13 side-by-side, mở terminal mới rồi kiểm tra lại.
- Không đổi interpreter trong `.venv` hiện hữu bằng cách sửa `pyvenv.cfg` thủ công.
- Không cài requirements bằng Python 3.11/3.12/3.14 rồi coi đó là môi trường đã nghiệm thu.
- macOS/Linux có thể chạy phần Python nhưng chưa thuộc baseline bàn giao; LAN script,
  ACL credential và hướng dẫn firewall trong tài liệu này dành cho Windows.

### `No module named ...` sau khi đã cài requirements

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
.\.venv\Scripts\python.exe -m pip --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Cả Python và pip phải trỏ vào cùng `<repo>\.venv`. Không sửa lỗi bằng `pip install`
không kèm `python -m`, vì lệnh `pip` có thể thuộc interpreter global khác.

### Pip báo không tìm thấy DuckDB wheel

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"
```

Kỳ vọng Python 3.13.x và 64. Nếu đúng nhưng vẫn lỗi, lưu nguyên log, kiểm tra proxy/
package index và báo người bàn giao; không tự chuyển sang source build.

### Login luôn thất bại

```powershell
Test-Path -LiteralPath .\data\auth\users.json
.\.venv\Scripts\python.exe -m scripts.create_user status
```

Nếu file thiếu, phải provision theo phần 8. Không gọi `change-password` để tạo account;
CLI sẽ fail closed. Nếu account disabled, dùng `enable`. Không sửa JSON/hash thủ công.

### Warehouse báo chưa sẵn sàng

```powershell
Test-Path -LiteralPath .\data\warehouse\rohlik.duckdb
```

File thiếu là trạng thái hợp lệ. Nếu file tồn tại nhưng mart thiếu, cần pipeline mart;
không fallback sang raw CSV và không init warehouse từ UI.

### Port 8501 đã được dùng

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8501
```

Xác định process hiện hữu; không khởi động nhiều Streamlit process cùng port. Dừng đúng
process do mình quản lý thay vì kill PID không rõ nguồn gốc.

### PowerShell không activate venv

Dùng trực tiếp:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

### DuckDB bị lock

Dừng Streamlit và đóng DBeaver/client khác trước khi chạy writer. Không xóa `.duckdb.wal`
hoặc database để chữa lock. Giữ file và điều tra owner/process.

### Dependency khác máy bàn giao

```powershell
.\.venv\Scripts\python.exe -m pip freeze
.\.venv\Scripts\python.exe -m pip check
```

Lưu output vào artifact bàn giao nếu cần đối chiếu. Không commit `.venv`.

## 15. Checklist bàn giao

### Người bàn giao

- [ ] Code mới nhất đã có trên `origin/main`.
- [ ] Không có secret, credential, raw CSV hoặc DuckDB trong Git.
- [ ] Ghi commit SHA được bàn giao.
- [ ] Chuyển credential store qua kênh bảo mật nếu người nhận cần đăng nhập.
- [ ] Truyền password ban đầu qua kênh tách biệt.
- [ ] Chuyển đúng bảy raw sources nếu người nhận làm Data Engineering.
- [ ] Chuyển warehouse đã kiểm định nếu yêu cầu dashboard có dữ liệu.
- [ ] Ghi rõ mart/model nào chưa sẵn sàng; không tuyên bố dữ liệu giả là production.

### Người nhận

- [ ] Clone `main`, working tree sạch.
- [ ] Python 3.13 64-bit và `.venv` local hoạt động.
- [ ] Dependencies cài thành công; `pip check` sạch.
- [ ] Toàn bộ pytest pass.
- [ ] `data/auth/users.json` được ignore và `status` chỉ ra `admin_local` enabled.
- [ ] Đã đổi password local qua prompt ẩn.
- [ ] Localhost login/logout và đủ 8 pages hoạt động.
- [ ] Hiểu warehouse/mart/model readiness hiện tại.
- [ ] Nếu nhận raw data, registry validation thành công và hash khớp.
- [ ] Chỉ bật LAN sau nghiệm thu auth; không expose port 8501 ra Internet.

## 16. Tài liệu phải đọc theo phạm vi

- Streamlit runtime: `docs/dashboard_v3_runbook.md`
- Authentication: `docs/authentication_runbook.md`
- Local/LAN: `docs/streamlit_local_lan_runbook.md`
- Refactor audit: `docs/dashboard_v3_refactor_audit.md`
- V4 source registry: `docs/source_registry.md`
- DuckDB safety: `docs/duckdb_setup.md`
- V4-03 landing: `docs/v4_03_landing_handover.md`
- Task08A lịch sử: `docs/bootstrap_sources.md`
- Model integration: `docs/model_integration_contract.md`
- Model handover: `docs/model_handover_checklist.md`
- Kiến trúc V4: `Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md`

Khi tài liệu lịch sử mâu thuẫn với runtime, ưu tiên code/test hiện tại, `README.md`, tài
liệu v3 ở trên và quyết định phạm vi admin-only/dashboard-only/read-only.
