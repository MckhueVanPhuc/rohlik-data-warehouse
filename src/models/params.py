"""Tham số chốt của 8 mô hình cho chế độ `models` (D06).

Thứ tự ưu tiên khi đọc:
  1. data/models/params/BTx.json  – do `python -m pipeline.run evaluate` ghi trên máy (không commit, đã .gitignore)
  2. config/model_params/BTx.json – bản mặc định đi kèm repo (sinh từ lần evaluate trên dữ liệu thật ngày 22/10/2026)
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from src.config.settings import PROJECT_ROOT, Settings

DEFAULT_PARAMS_DIR = PROJECT_ROOT / "config" / "model_params"


def params_path(settings: Settings, bt_id: str) -> tuple[Path, Path]:
    return settings.params_dir / f"{bt_id}.json", DEFAULT_PARAMS_DIR / f"{bt_id}.json"


def load_params(settings: Settings, bt_id: str) -> dict[str, Any] | None:
    local, default = params_path(settings, bt_id)
    for path, source in ((local, "evaluate cục bộ"), (default, "mặc định repo")):
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            params = data.get("params", data)
            params["_source"] = f"{source}: {path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path}"
            return params
    return None


def save_params(settings: Settings, bt_id: str, params: dict[str, Any], *, run_id: str, model_version: str) -> Path:
    local, _ = params_path(settings, bt_id)
    local.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "bt_id": bt_id,
        "model_version": model_version,
        "run_id": run_id,
        "as_of": settings.as_of.isoformat(),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "params": {k: v for k, v in params.items() if not k.startswith("_")},
    }
    local.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return local
