# Streamlit Infrastructure Smoke Test

## Mục tiêu và phạm vi

`app_smoke.py` xác minh Python, Streamlit và khả năng đọc hai database hạ tầng. Đây là
ứng dụng kiểm tra Infrastructure, không phải dashboard nghiệp vụ: không upload CSV,
không xác thực, không ETL, không tạo schema/bảng và không chạy model.

## Kiểm tra và chạy

```powershell
.\.venv\Scripts\python.exe -c "import streamlit; print(streamlit.__version__)"
.\.venv\Scripts\python.exe -m streamlit run app_smoke.py
```

Mở `http://127.0.0.1:8501`. Dừng bằng `Ctrl+C` trong terminal đã khởi động ứng dụng.
`.streamlit/config.toml` chỉ đặt `[server]`, `address = "127.0.0.1"` và `port = 8501`.
Nó không tắt bảo mật mặc định và không chứa credentials. `.streamlit/secrets.toml` chưa
được sử dụng và đã bị `.gitignore` loại trừ.

## Database checks và trạng thái

- SQLite: kiểm tra `data/input.db`, mở URI với `mode=ro`, chạy `SELECT 42`, rồi đóng.
- DuckDB: kiểm tra `data/warehouse/rohlik.duckdb`, mở `read_only=True`, chạy
  `SELECT 42`, rồi đóng.
- File không tồn tại được báo `MISSING`/`NOT_AVAILABLE`; smoke test không tạo file.

`PASS` là kiểm tra thật đã đạt; `FAIL` là kết nối/truy vấn lỗi hoặc kết quả sai;
`NOT_AVAILABLE` (database `MISSING` trên UI) là chưa có file; `BLOCKED` là file có nhưng
đang bị khóa/bận. Khi bị khóa, dừng đúng process sở hữu nếu được phép rồi thử lại; không
xóa lock hoặc kill process không xác định. Startup, HTTP health, UI execution và database
connectivity là bốn bằng chứng riêng.

## Automated verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_streamlit_smoke.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.validate_source_registry
```

Unit tests dùng database tạm hoặc mock; không thay đổi database thật. UI test dùng
`streamlit.testing.v1.AppTest`, không cần browser.

## Troubleshooting

- `ModuleNotFoundError`: chọn `.venv\Scripts\python.exe`, rồi cài đúng
  `requirements.txt`; không nâng cấp package khác nếu không cần.
- Port 8501 bận: dừng instance Task 05 do chính bạn chạy; không tự kill ứng dụng khác.
- `MISSING`: dùng quy trình initializer riêng khi được giao; smoke test cố ý không gọi nó.
- `BLOCKED`: đóng writer hoặc công cụ database đang giữ file rồi chạy lại.
- Lỗi config: kiểm tra TOML bằng `streamlit config show`; không thêm secret vào file.

## Bàn giao và giới hạn

Ứng dụng chính thức nên dùng entry point khác, tái sử dụng đường dẫn theo project root,
đọc published Parquet khi pipeline được triển khai và không chia sẻ DuckDB writer giữa
các session. `config/sources.yaml` là cấu hình DE riêng; không thay thế Streamlit config.

LAN chưa được bật. Ở giai đoạn sau, chỉ khi đã duyệt mạng, firewall, authentication và
vận hành, có thể đổi `server.address` sang interface phù hợp (hoặc `0.0.0.0`) và dùng IP
máy chủ. Không áp dụng hướng dẫn này ở Task 05.

Chưa triển khai: SQLite Business Schema, 14 physical Source Tables, CSV Upload backend,
Bronze/Silver/Gold/Mart, ETL/batch sync, Parquet Publisher, Model Runner BT1–BT8,
authentication và production Streamlit Dashboard.
