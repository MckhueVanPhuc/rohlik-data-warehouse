# Rohlik Decision Hub — V4-05

Rohlik Decision Hub là hệ thống Data Engineering và BI local-first dùng DuckDB, Python và Streamlit. V4-05 cung cấp pipeline có kiểm soát, mô hình BT1–BT8, dashboard vận hành và cơ chế cập nhật dữ liệu có audit/undo.

## Thành phần chính

- 7 nguồn CSV active được kiểm tra bằng registry và SHA-256.
- 14 bảng landing, 14 bảng STG, 6 bảng Core và 5 mart nền.
- 8 mô hình nghiệp vụ BT1–BT8 với runner, tham số và output contract.
- 10 trang Streamlit; reporting đọc DuckDB read-only.
- Upload CSV, data entry, undo và refresh được kiểm soát; chạy model chỉ qua CLI.
- Local authentication dùng Argon2id và session phía server.

## Yêu cầu

- Windows 11 và PowerShell
- Git + Git LFS
- Python 3.13 64-bit

## Cài đặt nhanh

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

Không commit `.env`, `data/auth`, raw data thật, model artifacts hoặc `data/warehouse/*.duckdb`.

## Kiểm tra nguồn và khởi tạo

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry
.\.venv\Scripts\python.exe -m scripts.create_user init-admin
.\.venv\Scripts\python.exe -m pipeline.run init
```

`pipeline.run init` chỉ nên chạy khi đã xác nhận đúng nguồn và vị trí warehouse. Không ghi đè database hiện hữu; xem hướng dẫn an toàn trong tài liệu pipeline.

## Chạy pipeline và mô hình

```powershell
.\.venv\Scripts\python.exe -m pipeline.run status
.\.venv\Scripts\python.exe -m pipeline.run evaluate
.\.venv\Scripts\python.exe -m pipeline.run models
```

Các lệnh pipeline khác: `ingest`, `refresh`, `all` và `import-outputs`. Model parameters mặc định cần được đánh giá trên dữ liệu của môi trường trước khi coi là đã kiểm định.

## Chạy Streamlit

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Ứng dụng mặc định phục vụ local. Chỉ bật truy cập LAN khi authentication và firewall đã được kiểm tra.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Test model phụ thuộc warehouse có thể được skip khi `data/warehouse/rohlik.duckdb` chưa tồn tại; đây không phải yêu cầu tự động tạo database.

## Tài liệu V4-05

- [Kiến trúc](docs/architecture.md)
- [Cài đặt và vận hành ban đầu](docs/setup.md)
- [Pipeline và runbook](docs/pipeline.md)
- [Data contract](docs/data_contract.md)
- [Mô hình BT1–BT8](docs/models.md)
- [Dashboard và thao tác vận hành](docs/dashboard.md)

V4-05 không còn runtime SQLite và không còn bootstrap Task08A. Registry production tại `config/sources.yaml` là nguồn cấu hình chính thức.
