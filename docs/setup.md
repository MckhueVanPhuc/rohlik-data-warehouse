# Cài đặt V4-05 trên Windows

## Điều kiện

Dùng Windows 11, PowerShell, Git, Git LFS và Python 3.13 64-bit.

```powershell
git --version
git lfs version
py -3.13 -c "import platform,sys; print(sys.version); print(platform.architecture()[0])"
Get-PSDrive -Name C
```

## Clone và môi trường Python

```powershell
git lfs install
git clone https://github.com/MckhueVanPhuc/rohlik-data-warehouse.git
Set-Location .\rohlik-data-warehouse
git checkout main
git lfs pull

py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
.\.venv\Scripts\python.exe -m pip check
```

Nếu `.venv` đã có, kiểm tra version và kiến trúc trước khi dùng. Không xóa môi trường cũ khi chưa xác nhận nó không còn cần thiết.

## Kiểm tra dữ liệu

```powershell
git lfs ls-files
.\.venv\Scripts\python.exe -m src.validate_source_registry
```

Validator phải xác nhận đủ 7 nguồn active và checksum SHA-256. `data/raw/sales/sales_train.csv` phải là CSV thật, không phải Git LFS pointer.

Raw data, `.env`, `data/auth` và DuckDB là dữ liệu local. Không thay thế chúng bằng bản Git hoặc dùng `git clean` để dọn.

## Tài khoản và test

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user init-admin
.\.venv\Scripts\python.exe -m scripts.create_user status
.\.venv\Scripts\python.exe -m pytest -q
```

Các thao tác tài khoản khác: `change-password`, `disable`, `enable`. Không đưa password hoặc `data/auth` vào log và Git. Hai test tích hợp model có thể skip khi warehouse chưa được bàn giao; không chạy ingestion chỉ để loại bỏ skip.

## DuckDB và model

```powershell
.\.venv\Scripts\python.exe -m pipeline.run status
# Chỉ trên môi trường mới, sau khi xác nhận warehouse chưa tồn tại:
.\.venv\Scripts\python.exe -m pipeline.run init
.\.venv\Scripts\python.exe -m pipeline.run evaluate
.\.venv\Scripts\python.exe -m pipeline.run models
```

Nếu `data/warehouse/rohlik.duckdb` đã tồn tại, không chạy lại `init`. Xem [pipeline](pipeline.md) trước ingest/refresh. Repository và script LAN hiện được thiết kế cho PowerShell/Windows; chưa có runbook macOS được kiểm chứng nên tài liệu không tuyên bố hỗ trợ macOS.

## Mở ứng dụng

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Giữ localhost mặc định. Truy cập LAN cần nghiệm thu authentication, firewall và phạm vi dữ liệu trước.
