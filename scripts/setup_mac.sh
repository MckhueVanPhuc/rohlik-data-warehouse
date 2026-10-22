#!/usr/bin/env bash
# Rohlik Decision Hub – cài môi trường trên macOS (D08). Chạy 1 lần tại thư mục gốc repo:
#     bash scripts/setup_mac.sh
# Việc script làm: kiểm tra Python 3.13 + Homebrew libomp (LightGBM cần) → tạo .venv → cài thư viện → chạy test.
# Không xoá/sửa dữ liệu, không tạo tài khoản (tạo admin bằng: .venv/bin/python -m scripts.create_user init-admin).
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
echo "Repo: $REPO_ROOT"
case "$REPO_ROOT" in
  *" "*) echo "CẢNH BÁO: đường dẫn repo có dấu cách – nên đặt repo ở thư mục không dấu cách (vd ~/Projects/rohlik-data-warehouse).";;
esac
[ -d .git ] || { echo "LỖI: không thấy .git – hãy chạy script trong thư mục repo đã git clone."; exit 1; }

PY="${PYTHON:-python3.13}"
command -v "$PY" >/dev/null 2>&1 || { echo "LỖI: chưa có $PY – cài Python 3.13 (macOS 64-bit universal2) từ python.org rồi chạy lại."; exit 1; }
"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version' || { echo "LỖI: cần Python 3.13"; exit 1; }

if command -v brew >/dev/null 2>&1; then
  brew list libomp >/dev/null 2>&1 || { echo "Cài libomp cho LightGBM…"; brew install libomp; }
else
  echo "CẢNH BÁO: chưa có Homebrew – LightGBM có thể báo thiếu libomp.dylib. Cài Homebrew (brew.sh) rồi: brew install libomp"
fi

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-models.txt
.venv/bin/python -m pip check
.venv/bin/python -c "import duckdb, pandas, streamlit, lightgbm, pulp, pyfixest; print('Thư viện OK – DuckDB', duckdb.__version__, '· LightGBM', lightgbm.__version__)"
.venv/bin/python -m pytest -q
echo
echo "XONG. Bước tiếp theo (xem tài liệu hướng dẫn tổng):"
echo "  1) chép 7 file nguồn vào data/raw/ (orders/, sales/, assumptions/)"
echo "  2) .venv/bin/python -m scripts.create_user init-admin"
echo "  3) .venv/bin/python -m pipeline.run init"
echo "  4) .venv/bin/python -m pipeline.run models     (hoặc import-outputs --from \"<Final Code>\")"
echo "  5) .venv/bin/python -m streamlit run app/main.py"
