"""Smoke tests for the admin-only Streamlit scaffold."""

from pathlib import Path

import yaml

from app.common import DataStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_app_imports_cleanly() -> None:
    import app
    import app.auth
    import app.common
    import app.main
    import app.services.reporting
    import app.views

    assert app and app.auth and app.common and app.main and app.views


def test_readiness_vocabulary_is_retained() -> None:
    required = {
        "WAREHOUSE_NOT_READY", "TABLE_NOT_AVAILABLE", "DATA_READY",
        "PENDING_MODEL", "DQ_FAILED", "REFRESH_REQUIRED",
    }
    assert required <= {status.value for status in DataStatus}


def test_auth_config_declares_exact_local_admin() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "config/auth.yaml").read_text(encoding="utf-8"))
    assert config["admin_username"] == "admin_local"
    assert config["credential_store"] == "data/auth/users.json"
    assert config["session_idle_minutes"] > 0
    assert config["rate_limit"]["account_max_failures"] > 0


def test_streamlit_runtime_has_no_role_policy_dependency() -> None:
    files = [
        PROJECT_ROOT / "app/auth.py",
        PROJECT_ROOT / "app/main.py",
        PROJECT_ROOT / "app/navigation.py",
        PROJECT_ROOT / "app/common.py",
        PROJECT_ROOT / "app/services/identity.py",
        PROJECT_ROOT / "app/services/reporting.py",
        PROJECT_ROOT / "scripts/create_user.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files).casefold()
    for forbidden in ("roles.yaml", "rolepolicy", "can_write", "can_undo", "can_refresh"):
        assert forbidden not in source
    assert not (PROJECT_ROOT / "app/services/access.py").exists()
    assert not (PROJECT_ROOT / "config/roles.yaml").exists()


def test_anonymous_app_stops_at_login() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(PROJECT_ROOT / "app/main.py")).run(timeout=10)
    assert not app.exception
    assert [title.value for title in app.title] == ["Đăng nhập"]
    assert [field.label for field in app.text_input] == ["Tên đăng nhập", "Mật khẩu"]
    assert not app.sidebar
