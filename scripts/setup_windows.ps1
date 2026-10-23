# Rohlik Decision Hub – cài môi trường trên Windows (PowerShell). Chạy 1 lần tại thư mục gốc repo:
#     powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
# Việc script làm: kiểm tra Python 3.13 64-bit + Microsoft Visual C++ Redistributable (LightGBM cần bản mới)
# → tạo .venv → cài thư viện → chẩn đoán LightGBM (pipeline.run doctor) → chạy test.
# Không xoá/sửa dữ liệu, không tạo tài khoản.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")
Write-Host "Repo: $(Get-Location)"
if (-not (Test-Path ".git")) { Write-Host "LỖI: không thấy .git – hãy chạy trong thư mục repo đã git clone."; exit 1 }

# 1) Python 3.13 64-bit
try { $pyver = & py -3.13 -c "import sys, struct; print(sys.version.split()[0], struct.calcsize('P')*8)" } catch { $pyver = $null }
if (-not $pyver) { Write-Host "LỖI: chưa có Python 3.13 – cài 'Windows installer (64-bit)' từ python.org (tích Add python.exe to PATH)."; exit 1 }
if ($pyver -notmatch " 64$") { Write-Host "LỖI: cần Python 64-bit (đang là: $pyver)."; exit 1 }
Write-Host "Python: $pyver"

# 2) Visual C++ Redistributable 2015–2022 x64 (LightGBM dùng msvcp140.dll / vcomp140.dll).
#    Bản cũ là nguyên nhân phổ biến của lỗi "OSError: access violation reading 0x0000000000000000" khi huấn luyện LightGBM.
$need = [version]"14.40.0.0"
$vc = $null
try { $vc = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction Stop).Version } catch { }
$vcv = $null
if ($vc) { $vcv = [version]($vc.TrimStart("v")) }
if (-not $vcv -or $vcv -lt $need) {
    Write-Host "Visual C++ Redistributable x64 đang là: $(if ($vc) { $vc } else { 'chưa cài' }) – cần >= $need."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Đang cài bản mới nhất bằng winget (có thể hiện hộp thoại xin quyền Administrator)…"
        winget install --id Microsoft.VCRedist.2015+.x64 -e --accept-package-agreements --accept-source-agreements
        Write-Host "Cài xong. KHỞI ĐỘNG LẠI MÁY rồi chạy lại script này."; exit 2
    } else {
        Write-Host "Tải và cài: https://aka.ms/vs/17/release/vc_redist.x64.exe  → khởi động lại máy → chạy lại script."; exit 2
    }
}
Write-Host "Visual C++ Redistributable x64: $vc (đạt)"

# 3) .venv + thư viện
if (-not (Test-Path ".venv\Scripts\python.exe")) { & py -3.13 -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt -r requirements-models.txt
& $py -m pip check
& $py -c "import duckdb, pandas, streamlit, lightgbm, pulp, pyfixest; print('Thư viện OK – DuckDB', duckdb.__version__, '· LightGBM', lightgbm.__version__)"

# 4) Chẩn đoán LightGBM trong tiến trình riêng (không làm sập script nếu thư viện gốc lỗi)
& $py -m pipeline.run doctor
if ($LASTEXITCODE -ne 0) { Write-Host "CẢNH BÁO: doctor báo lỗi – đọc mục 'Kết luận' ở trên trước khi chạy mô hình." }

# 5) Test
& $py -m pytest -q
Write-Host ""
Write-Host "XONG. Bước tiếp theo:"
Write-Host "  .\.venv\Scripts\python.exe -m pipeline.run init"
Write-Host "  .\.venv\Scripts\python.exe -m pipeline.run evaluate      (1 lần) rồi  pipeline.run models"
Write-Host "  .\.venv\Scripts\python.exe -m scripts.create_user init-admin"
Write-Host "  .\.venv\Scripts\python.exe -m streamlit run app/main.py"
