# V4-05.1 – Sửa lỗi "OSError: access violation reading 0x0000000000000000" (LightGBM trên Windows)

## Chép file (PowerShell, tại thư mục repo)
    Expand-Archive "$env:USERPROFILE\Downloads\Rohlik_Fix_V4-05.1.zip" -DestinationPath "$env:USERPROFILE\Downloads\fix" -Force
    Copy-Item "$env:USERPROFILE\Downloads\fix\Rohlik_Fix_V4-05.1\*" -Destination . -Recurse -Force

## Chạy
    powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1   # kiểm VC++ Redistributable, cài lại, doctor, test
    .\.venv\Scripts\python.exe -m pipeline.run doctor
    .\.venv\Scripts\python.exe -m pipeline.run models --database data/warehouse/rohlik_acceptance.duckdb

## File thay đổi
| File | Loại | Thay đổi |
|---|---|---|
| src/models/worker.py | MỚI | Chạy 1 BT trong tiến trình riêng; nạp LightGBM trước DuckDB/pyarrow; trả kết quả qua Parquet |
| src/models/doctor.py | MỚI | `pipeline.run doctor`: 5 phép thử LightGBM trong tiến trình riêng + kết luận cách sửa |
| src/models/runner.py | SỬA | Mặc định chạy mỗi BT trong tiến trình riêng; tiến trình con sập → BT đó FAILED, BT khác chạy tiếp |
| src/config/settings.py, config/settings.yaml | SỬA | Thêm `models.isolate: true` |
| pipeline/run.py | SỬA | Lệnh `doctor`, cờ `--no-isolate` |
| src/models/bt3.py | SỬA | Tắt cảnh báo FutureWarning observed=False (không đổi kết quả) |
| src/models/bt4.py | SỬA (bản đã sửa trước) | Lỗi Categorical "Unknown" |
| scripts/setup_windows.ps1 | MỚI | Cài Windows 1 lệnh, kiểm/cài VC++ Redistributable ≥ 14.40 |
| tests/test_model_isolation.py | MỚI | Kiểm thử tiến trình riêng + giả lập sập thư viện gốc |
