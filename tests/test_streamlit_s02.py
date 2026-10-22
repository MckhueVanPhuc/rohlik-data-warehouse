"""Navigation and dashboard-shell regression tests (Streamlit v3.1: 8 trang báo cáo + 2 trang nhập liệu – D01)."""

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
    "entry": ("Nhập dữ liệu", "nhap-du-lieu"),
    "batches": ("Lịch sử lô / Undo", "lich-su-lo"),
    "system": ("Vận hành hệ thống", "van-hanh-he-thong"),
}


def test_exactly_ten_pages_with_stable_urls() -> None:
    assert len(PAGE_DEFINITIONS) == 10
    assert sum(page.default for page in PAGE_DEFINITIONS) == 1
    assert {page.module: (page.title, page.url_path) for page in PAGE_DEFINITIONS} == EXPECTED_PAGES
    assert all(page.icon.startswith(":material/") for page in PAGE_DEFINITIONS)


def test_navigation_has_no_role_argument_or_filter(monkeypatch) -> None:
    calls = []

    def fake_page(renderer, **kwargs):
        calls.append((renderer, kwargs))
        return kwargs

    monkeypatch.setattr("app.navigation.st.Page", fake_page)
    groups = build_navigation()
    assert tuple(groups) == ("Tổng quan", "Nghiệp vụ", "Dữ liệu & hệ thống")
    assert sum(len(pages) for pages in groups.values()) == 10
    assert [call[1]["url_path"] for call in calls] == [page.url_path for page in PAGE_DEFINITIONS]


def test_all_views_import_and_anonymous_users_only_see_login() -> None:
    for module_name, (title, _path) in EXPECTED_PAGES.items():
        module = import_module(f"app.views.{module_name}")
        assert callable(module.render)
        app = AppTest.from_string(f"from app.views import {module_name}\n{module_name}.render()\n").run(timeout=10)
        assert not app.exception
        assert [item.value for item in app.title] == ["Đăng nhập"]
        assert title not in [item.value for item in app.title]


def test_entry_pages_require_operator_and_reason_and_never_run_models() -> None:
    entry = (PROJECT_ROOT / "app/views/entry.py").read_text(encoding="utf-8")
    batches = (PROJECT_ROOT / "app/views/batches.py").read_text(encoding="utf-8")
    assert "Người nhập" in entry and "Lý do" in entry
    assert "Người undo" in batches and "Lý do undo" in batches
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [PROJECT_ROOT / "app/common.py", PROJECT_ROOT / "app/navigation.py", *(PROJECT_ROOT / "app/views").glob("*.py")]
    ).casefold()
    for forbidden in ("data_editor", "run_models(", "src.models.runner", "execute(\"drop", "delete from"):
        assert forbidden not in source
    ops = (PROJECT_ROOT / "app/services/operations.py").read_text(encoding="utf-8")
    assert ops.count("_require_admin()") >= 8


def test_model_states_point_to_allowlisted_result_marts_without_fake_forecasts() -> None:
    from app.services.reporting import MODEL_MARTS
    modules = ("overview", "ops", "logistics", "demand", "pricing", "growth")
    for name in modules:
        states = import_module(f"app.views.{name}").SPEC.model_states
        assert states and all(state.mart in MODEL_MARTS for state in states)
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
