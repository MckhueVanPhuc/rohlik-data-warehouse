"""Đọc và kiểm tra config/settings.yaml cho pipeline Rohlik Decision Hub (D03, D07)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"


class SettingsError(ValueError):
    """config/settings.yaml thiếu khoá hoặc mốc thời gian không khớp nhau."""


@dataclass(frozen=True)
class Settings:
    warehouse_path: str
    warehouses: tuple[str, ...]
    train_from: date
    as_of: date
    test_start: date
    forecast_start: date
    forecast_end: date
    horizon_days: int
    seed: int
    currency_by_warehouse: dict[str, str]
    fx_eur: dict[str, float]
    new_warehouses: tuple[str, ...]
    upload_max_rows: int
    lock_timeout_seconds: float
    params_dir: Path
    runs_dir: Path
    n_jobs: int
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    def currency(self, warehouse: str) -> str:
        return self.currency_by_warehouse[warehouse]

    def fx(self, warehouse: str) -> float:
        return float(self.fx_eur[self.currency_by_warehouse[warehouse]])

    def sql_params(self) -> dict[str, Any]:
        """Giá trị dùng chung cho các câu SQL của STG/Core/Mart."""
        return {
            "train_from": self.train_from,
            "as_of": self.as_of,
            "forecast_end": self.forecast_end,
            "test_start": self.test_start,
        }

    def model_config(self) -> dict[str, Any]:
        """Phần cấu hình chung truyền vào mọi mô hình BT1–BT8."""
        return {
            "as_of": self.as_of.isoformat(),
            "train_start": self.train_from.isoformat(),
            "horizon": self.horizon_days,
            "seed": self.seed,
            "warehouses": list(self.warehouses),
            "currency_by_warehouse": dict(self.currency_by_warehouse),
            "fx_eur": dict(self.fx_eur),
        }


def _date(value: Any, key: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise SettingsError(f"settings.{key} phải là ngày dạng YYYY-MM-DD: {value!r}") from exc


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> Settings:
    """Đọc settings.yaml; báo lỗi tiếng Việt rõ ràng nếu thiếu khoá hoặc mốc lệch nhau."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise SettingsError(f"Không đọc được {path}: {exc}") from exc
    try:
        scope = data["sku_scope"]
        warehouses = tuple(scope["warehouses"])
        train_from = _date(scope["train_from"], "sku_scope.train_from")
        horizon = int(data["horizon_days"])
        as_of = _date(data["as_of"], "as_of")
        test_start = _date(data.get("test_start", as_of - timedelta(days=horizon - 1)), "test_start")
        fc_start = _date(data.get("forecast_start", as_of + timedelta(days=1)), "forecast_start")
        fc_end = _date(data.get("forecast_end", as_of + timedelta(days=horizon)), "forecast_end")
        currency = {str(k): str(v) for k, v in data["currency_by_warehouse"].items()}
        fx = {str(k): float(v) for k, v in data["fx_eur"].items()}
    except KeyError as exc:
        raise SettingsError(f"config/settings.yaml thiếu khoá {exc}") from exc
    if not warehouses or len(set(warehouses)) != len(warehouses):
        raise SettingsError("sku_scope.warehouses phải là danh sách kho không trùng")
    if fc_start != as_of + timedelta(days=1) or fc_end != as_of + timedelta(days=horizon):
        raise SettingsError("forecast_start/forecast_end phải = as_of + 1 và as_of + horizon_days")
    if test_start != as_of - timedelta(days=horizon - 1):
        raise SettingsError("test_start phải = as_of − (horizon_days − 1)")
    if not train_from < test_start:
        raise SettingsError("train_from phải trước test_start")
    lack_ccy = sorted(set(warehouses) - set(currency))
    if lack_ccy:
        raise SettingsError(f"currency_by_warehouse thiếu kho {lack_ccy}")
    lack_fx = sorted(set(currency.values()) - set(fx))
    if lack_fx:
        raise SettingsError(f"fx_eur thiếu tiền tệ {lack_fx}")
    upload = data.get("upload", {}) or {}
    models = data.get("models", {}) or {}
    return Settings(
        warehouse_path=str(data["warehouse"]),
        warehouses=warehouses,
        train_from=train_from,
        as_of=as_of,
        test_start=test_start,
        forecast_start=fc_start,
        forecast_end=fc_end,
        horizon_days=horizon,
        seed=int(data.get("seed", 42)),
        currency_by_warehouse=currency,
        fx_eur=fx,
        new_warehouses=tuple(data.get("new_warehouses", ())),
        upload_max_rows=int(upload.get("max_rows", 50000)),
        lock_timeout_seconds=float(upload.get("lock_timeout_seconds", 10)),
        params_dir=PROJECT_ROOT / str(models.get("params_dir", "data/models/params")),
        runs_dir=PROJECT_ROOT / str(models.get("runs_dir", "data/models/runs")),
        n_jobs=int(models.get("n_jobs", -1)),
        raw=data,
    )
