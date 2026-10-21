"""Navigation and dashboard-shell regression tests for Streamlit v3.0."""

from importlib import import_module
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.navigation import PAGE_DEFINITIONS, build_navigation


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PAGES = {
    "overview": ("Tổng quan", "tong-quan"),
    "ops": ("Nhân sự kho", "nhan-su-kho"),
    "logistics": ("Tài xế", "tai-xe"),
    "demand": ("Nhu cầu & Đặt hàng", "nhu-cau-dat-hang"),
    "pricing": ("Khuyến mãi", "khuyen-mai"),
    "growth": ("Tăng trưởng", "tang-truong"),
    "explorer": ("Truy vấn & EDA", "truy-van-eda"),
    "system": ("Vận hành hệ thống", "van-hanh-he-thong"),
}


def test_exactly_eight_pages_with_stable_urls() -> None:
    assert len(PAGE_DEFINITIONS) == 8
    assert sum(page.default for page in PAGE_DEFINITIONS) == 1
    assert {page.module: (page.title, page.url_path) for page in PAGE_DEFINITIONS} == EXPECTED_PAGES
    assert "nhap-du-lieu" not in {page.url_path for page in PAGE_DEFINITIONS}
    assert all(page.icon.startswith(":material/") for page in PAGE_DEFINITIONS)


def test_navigation_has_no_role_argument_or_filter(monkeypatch) -> None:
    calls = []

    def fake_page(renderer, **kwargs):
        calls.append((renderer, kwargs))
        return kwargs

    monkeypatch.setattr("app.navigation.st.Page", fake_page)
    groups = build_navigation()
    assert tuple(groups) == ("Tổng quan", "Nghiệp vụ", "Dữ liệu & hệ thống")
    assert sum(len(pages) for pages in groups.values()) == 8
    assert [call[1]["url_path"] for call in calls] == [page.url_path for page in PAGE_DEFINITIONS]


def test_all_views_import_and_anonymous_users_only_see_login() -> None:
    for module_name, (title, _path) in EXPECTED_PAGES.items():
        module = import_module(f"app.views.{module_name}")
        assert callable(module.render)
        app = AppTest.from_string(f"from app.views import {module_name}\n{module_name}.render()\n").run(timeout=10)
        assert not app.exception
        assert [item.value for item in app.title] == ["Đăng nhập"]
        assert title not in [item.value for item in app.title]


def test_removed_entry_module_and_actions_are_absent() -> None:
    assert not (PROJECT_ROOT / "app/views/entry.py").exists()
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [PROJECT_ROOT / "app/common.py", PROJECT_ROOT / "app/navigation.py", *(PROJECT_ROOT / "app/views").glob("*.py")]
    ).casefold()
    for forbidden in (
        "file_uploader", "data_editor", "nhap-du-lieu", "xác nhận ghi",
        "soft undo", "disabled_actions", "pipeline.run", "src.ingestion",
    ):
        assert forbidden not in source
    assert "st.button(" not in source


def test_model_states_are_pending_without_fake_forecasts() -> None:
    modules = ("overview", "ops", "logistics", "demand", "pricing", "growth")
    assert all(import_module(f"app.views.{name}").SPEC.model_states for name in modules)
    source = "\n".join((PROJECT_ROOT / "app/views" / f"{name}.py").read_text(encoding="utf-8") for name in modules)
    assert "PENDING_MODEL" not in source  # centralized renderer owns the state badge
    assert "mock forecast" not in source.casefold()


def test_status_markup_has_accessible_semantics() -> None:
    source = (PROJECT_ROOT / "app/common.py").read_text(encoding="utf-8")
    assert 'role="status" aria-live="polite"' in source
    assert 'role="list" aria-label="Trạng thái đầu ra mô hình"' in source
    assert 'role="listitem"' in source
    assert '<div class="rdh-empty"><h2>' in source


def test_local_server_security_settings_remain_enabled() -> None:
    config = (PROJECT_ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")
    assert 'address = "127.0.0.1"' in config
    assert "enableCORS = true" in config
    assert "enableXsrfProtection = true" in config
