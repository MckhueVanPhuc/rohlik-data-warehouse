"""Single-admin authentication, session, and CLI security tests."""

from pathlib import Path
import subprocess

from argon2 import PasswordHasher, Type
import pytest
from streamlit.testing.v1 import AppTest

from app.services.identity import (
    AuthenticationError,
    AuthenticationService,
    CredentialStore,
    CredentialStoreError,
    LoginRateLimiter,
    PasswordPolicy,
    ServerSessionRegistry,
    SessionError,
)
from scripts import create_user


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_PASSWORD = "Strong-Password-42"
NEW_PASSWORD = "New-Password-84!"


class ManualClock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def auth_factory(tmp_path):
    def factory(*, idle_timeout=300, failures=5, include_other=False):
        clock = ManualClock()
        hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1, type=Type.ID)
        store = CredentialStore(tmp_path / f"users-{idle_timeout}-{failures}.json", password_hasher=hasher)
        policy = PasswordPolicy()
        admin = store.create_user(
            "admin_local", VALID_PASSWORD, "data_team",
            valid_roles={"data_team", "marketing"}, password_policy=policy,
        )
        other = None
        if include_other:
            other = store.create_user(
                "other_user", VALID_PASSWORD, "marketing",
                valid_roles={"data_team", "marketing"}, password_policy=policy,
            )
        service = AuthenticationService(
            store, "admin_local", ServerSessionRegistry(idle_timeout, clock=clock),
            LoginRateLimiter(
                account_max_failures=failures, session_max_failures=failures,
                window_seconds=900, lockout_seconds=120, clock=clock,
            ),
            password_hasher=hasher,
        )
        return store, admin, other, service, clock

    return factory


def test_legacy_data_team_admin_logs_in_without_hash_rewrite(auth_factory) -> None:
    store, admin, _other, service, _clock = auth_factory()
    before = store.path.read_bytes()
    result = service.authenticate("admin_local", VALID_PASSWORD, scope="browser-a")
    assert result.user.username == "admin_local"
    assert result.user.user_id == admin.user_id
    assert not hasattr(result.user, "role")
    assert store.path.read_bytes() == before
    assert admin.password_hash.startswith("$argon2id$")


def test_other_enabled_account_is_denied_with_generic_error(auth_factory) -> None:
    _store, _admin, other, service, _clock = auth_factory(include_other=True)
    with pytest.raises(AuthenticationError, match="Invalid username or password"):
        service.authenticate(other.username, VALID_PASSWORD, scope="browser-b")


def test_wrong_password_and_unknown_username_share_failure(auth_factory) -> None:
    _store, _admin, _other, service, _clock = auth_factory()
    messages = []
    for username in ("admin_local", "unknown"):
        with pytest.raises(AuthenticationError) as captured:
            service.authenticate(username, "Wrong-Password-99!", scope=username)
        messages.append(str(captured.value))
    assert messages == ["Invalid username or password."] * 2


def test_disable_enable_session_revalidation_and_logout(auth_factory) -> None:
    store, admin, _other, service, _clock = auth_factory()
    token = service.authenticate(admin.username, VALID_PASSWORD, scope="a").session_token
    store.disable_user(admin.username)
    with pytest.raises(SessionError):
        service.validate_session(token)
    store.enable_user(admin.username)
    new_token = service.authenticate(admin.username, VALID_PASSWORD, scope="b").session_token
    service.logout(new_token)
    with pytest.raises(SessionError):
        service.validate_session(new_token)


def test_timeout_token_forgery_and_rate_limit(auth_factory) -> None:
    _store, admin, _other, service, clock = auth_factory(idle_timeout=30, failures=2)
    token = service.authenticate(admin.username, VALID_PASSWORD, scope="valid").session_token
    clock.advance(31)
    with pytest.raises(SessionError, match="expired"):
        service.validate_session(token)
    with pytest.raises(SessionError):
        service.validate_session("forged-token")
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            service.authenticate(admin.username, "Wrong-Password-99!", scope="limited")
    with pytest.raises(AuthenticationError):
        service.authenticate(admin.username, VALID_PASSWORD, scope="limited")


def test_password_change_invalidates_session(auth_factory) -> None:
    store, admin, _other, service, _clock = auth_factory()
    token = service.authenticate(admin.username, VALID_PASSWORD, scope="old").session_token
    store.change_password(admin.username, NEW_PASSWORD, password_policy=PasswordPolicy())
    with pytest.raises(SessionError):
        service.validate_session(token)
    with pytest.raises(AuthenticationError):
        service.authenticate(admin.username, VALID_PASSWORD, scope="old-password")
    assert service.authenticate(admin.username, NEW_PASSWORD, scope="new-password").user == service.validate_session(
        service.authenticate(admin.username, NEW_PASSWORD, scope="second").session_token
    )


def test_cli_manages_only_configured_existing_admin(tmp_path, monkeypatch, capsys) -> None:
    hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1, type=Type.ID)
    store = CredentialStore(tmp_path / "users.json", password_hasher=hasher)
    store.create_user(
        "admin_local", VALID_PASSWORD, "data_team",
        valid_roles={"data_team"}, password_policy=PasswordPolicy(),
    )
    monkeypatch.setattr(create_user, "load_cli_dependencies", lambda: (store, PasswordPolicy(), "admin_local"))
    assert create_user.main(["status"]) == 0
    output = capsys.readouterr().out
    assert "admin_local\ttrue" in output
    assert "$argon2" not in output and "data_team" not in output
    assert create_user.main(["disable"]) == 0
    assert store.find_by_username("admin_local").enabled is False
    assert create_user.main(["enable"]) == 0
    assert store.find_by_username("admin_local").enabled is True
    parser = create_user.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create", "--username", "demo"])


def test_cli_refuses_to_create_missing_admin(tmp_path, monkeypatch) -> None:
    store = CredentialStore(tmp_path / "missing.json")
    monkeypatch.setattr(create_user, "load_cli_dependencies", lambda: (store, PasswordPolicy(), "admin_local"))
    assert create_user.main(["status"]) == 1
    assert not store.path.exists()


def test_anonymous_main_and_generic_login_failure() -> None:
    app = AppTest.from_file(str(PROJECT_ROOT / "app/main.py")).run(timeout=10)
    assert not app.exception
    assert [title.value for title in app.title] == ["Đăng nhập"]
    app.text_input[0].input("unknown-user")
    app.text_input[1].input("Wrong-Password-99!")
    app.button[0].click().run(timeout=10)
    assert len(app.error) == 1
    assert "Không thể đăng nhập" in app.error[0].value
    assert "unknown-user" not in app.error[0].value


def test_credential_store_wraps_permission_error(tmp_path, monkeypatch) -> None:
    store = CredentialStore(tmp_path / "users.json")
    original_exists = Path.exists

    def permission_denied(path):
        if path == store.path:
            raise PermissionError("access denied")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", permission_denied)
    with pytest.raises(CredentialStoreError, match="cannot be read safely"):
        store.list_users()


def test_real_credential_store_is_ignored_and_not_tracked() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "data/auth/users.json"], cwd=PROJECT_ROOT,
        check=False, capture_output=True, text=True,
    )
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "data/auth/users.json"], cwd=PROJECT_ROOT,
        check=False, capture_output=True, text=True,
    )
    assert ignored.returncode == 0
    assert tracked.returncode != 0
