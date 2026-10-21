"""Single-admin Streamlit authentication boundary for Rohlik Decision Hub."""

from __future__ import annotations

import logging
from pathlib import Path
import secrets

import streamlit as st
import yaml

from app.services.identity import (
    AuthenticationError,
    AuthenticationService,
    AuthenticatedUser,
    CredentialStore,
    CredentialStoreError,
    LoginRateLimiter,
    PasswordPolicy,
    ServerSessionRegistry,
    SessionError,
)


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTH_CONFIG_PATH = PROJECT_ROOT / "config" / "auth.yaml"
SESSION_TOKEN_KEY = "_rdh_auth_session_token"
ATTEMPT_SCOPE_KEY = "_rdh_auth_attempt_scope"
LOGIN_ERROR_KEY = "_rdh_auth_login_error"
GENERIC_LOGIN_ERROR = "Không thể đăng nhập. Vui lòng kiểm tra thông tin và thử lại sau."


def _load_auth_config() -> dict:
    try:
        with AUTH_CONFIG_PATH.open(encoding="utf-8") as file_handle:
            config = yaml.safe_load(file_handle)
    except (OSError, yaml.YAMLError) as exc:
        raise CredentialStoreError("Authentication configuration is unavailable.") from exc
    if not isinstance(config, dict):
        raise CredentialStoreError("Authentication configuration must be a mapping.")
    return config


def _resolve_credential_path(config: dict) -> Path:
    configured = config.get("credential_store")
    if not isinstance(configured, str) or not configured:
        raise CredentialStoreError("Credential store path is not configured.")
    path = (PROJECT_ROOT / configured).resolve()
    auth_root = (PROJECT_ROOT / "data" / "auth").resolve()
    if path != auth_root and auth_root not in path.parents:
        raise CredentialStoreError("Credential store must remain under data/auth.")
    return path


@st.cache_resource(show_spinner=False)
def get_security_services() -> tuple[AuthenticationService, PasswordPolicy]:
    """Build one process-local security service set for all Streamlit sessions."""

    config = _load_auth_config()
    admin_username = config.get("admin_username")
    if not isinstance(admin_username, str) or not admin_username.strip():
        raise CredentialStoreError("Admin username is not configured.")
    password_config = config.get("password_policy", {})
    rate_config = config.get("rate_limit", {})
    try:
        password_policy = PasswordPolicy(
            min_length=int(password_config["min_length"]),
            max_length=int(password_config["max_length"]),
        )
        idle_timeout = float(config["session_idle_minutes"]) * 60
        limiter = LoginRateLimiter(
            account_max_failures=int(rate_config["account_max_failures"]),
            session_max_failures=int(rate_config["session_max_failures"]),
            window_seconds=float(rate_config["window_seconds"]),
            lockout_seconds=float(rate_config["lockout_seconds"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CredentialStoreError("Authentication settings are invalid.") from exc

    store = CredentialStore(_resolve_credential_path(config))
    try:
        authentication = AuthenticationService(
            store,
            admin_username,
            ServerSessionRegistry(idle_timeout),
            limiter,
        )
    except ValueError as exc:
        raise CredentialStoreError("Configured admin username is invalid.") from exc
    return authentication, password_policy


def _attempt_scope() -> str:
    if ATTEMPT_SCOPE_KEY not in st.session_state:
        st.session_state[ATTEMPT_SCOPE_KEY] = secrets.token_urlsafe(18)
    return st.session_state[ATTEMPT_SCOPE_KEY]


def _clear_auth_state() -> None:
    for key in (SESSION_TOKEN_KEY, ATTEMPT_SCOPE_KEY, LOGIN_ERROR_KEY):
        st.session_state.pop(key, None)


def render_login() -> None:
    """Render the only screen available to an anonymous browser session."""

    st.title("Đăng nhập")
    st.markdown(
        "Truy cập Rohlik Decision Hub bằng tài khoản nội bộ được tạo trên máy host."
    )
    with st.form("rdh-login", clear_on_submit=False):
        username = st.text_input("Tên đăng nhập", autocomplete="username")
        password = st.text_input(
            "Mật khẩu",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button(
            "Đăng nhập",
            type="primary",
            use_container_width=True,
        )

    if st.session_state.pop(LOGIN_ERROR_KEY, False):
        st.error(GENERIC_LOGIN_ERROR)

    if submitted:
        try:
            authentication, _password_policy = get_security_services()
            result = authentication.authenticate(username, password, scope=_attempt_scope())
        except (AuthenticationError, CredentialStoreError):
            st.session_state[LOGIN_ERROR_KEY] = True
            st.rerun()
        else:
            st.session_state[SESSION_TOKEN_KEY] = result.session_token
            st.session_state.pop(LOGIN_ERROR_KEY, None)
            st.rerun()


def require_admin(*, show_login: bool = True) -> AuthenticatedUser:
    """Resolve an opaque token against the configured admin account server-side."""

    token = st.session_state.get(SESSION_TOKEN_KEY)
    if isinstance(token, str) and token:
        try:
            authentication, _password_policy = get_security_services()
            return authentication.validate_session(token)
        except (SessionError, CredentialStoreError):
            _clear_auth_state()

    if show_login:
        render_login()
    st.stop()
    raise SessionError("Authentication required.")  # pragma: no cover


def logout_current_session() -> None:
    """Revoke server state, remove the browser token, and return to login."""

    token = st.session_state.get(SESSION_TOKEN_KEY)
    if isinstance(token, str) and token:
        try:
            authentication, _password_policy = get_security_services()
            authentication.logout(token)
        except CredentialStoreError:
            LOGGER.exception("Authentication service failed during logout.")
    _clear_auth_state()


def render_logout_control() -> None:
    if st.sidebar.button(
        "Đăng xuất",
        icon=":material/logout:",
        use_container_width=True,
        key="rdh-logout",
    ):
        logout_current_session()
        st.rerun()


