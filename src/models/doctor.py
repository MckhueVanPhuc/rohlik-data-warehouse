"""Chẩn đoán môi trường chạy mô hình: `python -m pipeline.run doctor`.

Mỗi phép thử chạy trong một tiến trình con riêng, nên dù thư viện gốc làm sập tiến trình (access violation,
segfault) thì doctor vẫn chạy tiếp và báo được phép thử nào hỏng → biết nguyên nhân và cách sửa.
"""

from __future__ import annotations

import importlib.metadata as md
import os
import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_FIT = r'''
import numpy as np
rng = np.random.default_rng(42)
n = 4000
X = np.column_stack([rng.integers(0, 7, n), rng.normal(size=n), rng.normal(size=n)]).astype("float64")
y = np.abs(X[:, 1] * 3 + X[:, 0] + rng.normal(size=n))
import lightgbm as lgb
m = lgb.LGBMRegressor(objective="__OBJ__", n_estimators=30, n_jobs=__NJ__, verbose=-1, random_state=42, deterministic=True)
m.fit(X, y, categorical_feature=[0])
print("OK", round(float(m.predict(X[:5]).sum()), 3))
'''

_PANDAS_FIT = r'''
import numpy as np, pandas as pd
rng = np.random.default_rng(42)
n = 4000
df = pd.DataFrame({"kho": pd.Categorical(rng.choice(["Prague_1", "Brno_1", "Munich_1"], n)),
                   "x1": rng.normal(size=n), "x2": rng.normal(size=n)})
y = pd.Series(np.abs(df["x1"] * 3 + rng.normal(size=n)))
import lightgbm as lgb
m = lgb.LGBMRegressor(objective="quantile", alpha=0.5, n_estimators=30, n_jobs=__NJ__, verbose=-1, random_state=42)
m.fit(df, y, sample_weight=np.ones(n), categorical_feature=["kho"])
print("OK", round(float(m.predict(df.head()).sum()), 3))
'''

_DLLS = r'''
import ctypes, ctypes.wintypes as wt
names = ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "vcomp140.dll", "libomp140.x86_64.dll"]
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.GetModuleHandleW.restype = wt.HMODULE
for nm in names:
    h = k.GetModuleHandleW(nm)
    if not h:
        continue
    buf = ctypes.create_unicode_buffer(1024)
    k.GetModuleFileNameW(h, buf, 1024)
    ver = ""
    try:
        v = ctypes.WinDLL("version")
        size = v.GetFileVersionInfoSizeW(buf.value, None)
        data = ctypes.create_string_buffer(size)
        v.GetFileVersionInfoW(buf.value, 0, size, data)
        p = ctypes.c_void_p(); ln = wt.UINT()
        v.VerQueryValueW(data, "\\", ctypes.byref(p), ctypes.byref(ln))
        class FI(ctypes.Structure):
            _fields_ = [(f, wt.DWORD) for f in ("sig", "struc", "fvms", "fvls", "pvms", "pvls", "mask", "flags", "os", "type", "sub", "dms", "dls")]
        fi = ctypes.cast(p, ctypes.POINTER(FI)).contents
        ver = f"{fi.fvms >> 16}.{fi.fvms & 0xFFFF}.{fi.fvls >> 16}.{fi.fvls & 0xFFFF}"
    except Exception:
        pass
    print(f"   {nm:<22} {ver:<16} {buf.value}")
'''


def _fit(obj: str, nj: int) -> str:
    return _FIT.replace("__OBJ__", obj).replace("__NJ__", str(nj))


def _run(code: str, pre: str = "") -> tuple[bool, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, "-X", "utf8", "-c", pre + code], cwd=str(PROJECT_ROOT), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    txt = (p.stdout + p.stderr).strip().splitlines()
    tail = txt[-1] if txt else ""
    if p.returncode != 0:
        crash = {3221225477: "ACCESS VIOLATION (0xC0000005)", -11: "SEGFAULT"}.get(p.returncode, f"mã thoát {p.returncode}")
        return False, f"{crash} – {tail[:160]}"
    return True, tail


def _vcredist() -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64") as k:
            return str(winreg.QueryValueEx(k, "Version")[0])
    except OSError:
        return "không tìm thấy"


def doctor(n_jobs: int = -1) -> int:
    print("== Môi trường ==")
    print(f"  Hệ điều hành : {platform.platform()} · CPU logic: {os.cpu_count()}")
    print(f"  Python       : {sys.version.split()[0]} ({platform.architecture()[0]}) – {sys.executable}")
    for pkg in ("numpy", "pandas", "pyarrow", "duckdb", "lightgbm", "scikit-learn", "pyfixest", "PuLP", "scipy"):
        try:
            print(f"  {pkg:<13}: {md.version(pkg)}")
        except md.PackageNotFoundError:
            print(f"  {pkg:<13}: CHƯA CÀI")
    vc = _vcredist()
    if vc is not None:
        print(f"  VC++ Redistributable x64: {vc}")

    print("\n== Phép thử LightGBM (mỗi phép thử chạy trong tiến trình riêng) ==")
    tests = [
        ("A. LightGBM nạp riêng, numpy, nhiều luồng", "", _fit("regression_l1", n_jobs)),
        ("B. LightGBM nạp riêng, 1 luồng", "", _fit("regression_l1", 1)),
        ("C. Nạp DuckDB + pyarrow TRƯỚC rồi LightGBM", "import duckdb, pyarrow, pandas\n", _fit("tweedie", n_jobs)),
        ("D. pandas Categorical + quantile (giống BT1)", "", _PANDAS_FIT.replace("__NJ__", str(n_jobs))),
        ("E. Thứ tự của pipeline cũ (DuckDB đọc kho rồi LightGBM)",
         "import duckdb; duckdb.connect().execute('select 1').df()\n", _PANDAS_FIT.replace("__NJ__", str(n_jobs))),
    ]
    res = {}
    for name, pre, code in tests:
        ok, msg = _run(code, pre)
        res[name[0]] = ok
        print(f"  {'ĐẠT ' if ok else 'LỖI '} {name}: {msg}")

    if os.name == "nt":
        print("\n== Thư viện runtime C++ đang được nạp (sau khi import duckdb, pyarrow, lightgbm) ==")
        p = subprocess.run([sys.executable, "-X", "utf8", "-c", "import duckdb, pyarrow, lightgbm\n" + _DLLS],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(p.stdout.rstrip() or "   (không đọc được)")

    print("\n== Kết luận ==")
    if all(res.values()):
        print("  Mọi phép thử ĐẠT – môi trường chạy được 8 mô hình.")
        return 0
    if not res["A"] and not res["B"]:
        print("  LightGBM hỏng ngay cả khi chạy một mình → thư viện runtime C++ của Windows quá cũ hoặc bản LightGBM cài lỗi.")
        print("  Sửa: (1) cài 'Microsoft Visual C++ Redistributable 2015–2022 x64' bản mới nhất:")
        print("         winget install --id Microsoft.VCRedist.2015+.x64   (hoặc tải https://aka.ms/vs/17/release/vc_redist.x64.exe)")
        print("       (2) khởi động lại máy; (3) .venv\\Scripts\\python.exe -m pip install --force-reinstall --no-cache-dir lightgbm==4.7.0")
    elif not res["A"] and res["B"]:
        print("  LightGBM chỉ hỏng khi chạy nhiều luồng → đặt `models.n_jobs: 1` trong config/settings.yaml (chậm hơn nhưng ổn định).")
    elif res["A"] and (not res["C"] or not res["E"]):
        print("  LightGBM chạy riêng thì ĐẠT nhưng hỏng khi DuckDB/pyarrow nạp trước → xung đột thư viện runtime C++.")
        print("  Pipeline V4-05.1 đã xử lý: mỗi BT chạy trong tiến trình riêng và nạp LightGBM trước (models.isolate: true).")
        print("  Nên cài thêm VC++ Redistributable mới nhất (lệnh winget ở trên) để gốc rễ biến mất.")
    elif not res["D"]:
        print("  Hỏng với dữ liệu pandas Categorical → cài lại đúng phiên bản: pip install --force-reinstall pandas==2.3.3 lightgbm==4.7.0")
    return 1
