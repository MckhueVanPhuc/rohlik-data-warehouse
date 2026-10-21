"""Local identity, credential, rate-limit, and server-session services.

This module is independent of Streamlit and the warehouse. Credentials are
stored as Argon2id hashes in a dedicated JSON file; mutations use a same-folder
temporary file followed by ``os.replace`` for atomic publication.
"""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import getpass
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile
import threading
import time
from typing import Callable, Iterator
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


class IdentityError(Exception):
    """Base class for local identity failures."""


class CredentialStoreError(IdentityError):
    """Credential store is invalid, unavailable, or cannot be updated safely."""


class AccountConflictError(IdentityError):
    """Account creation or mutation conflicts with current store state."""


class PasswordPolicyError(IdentityError):
    """Password does not meet the configured minimum policy."""


class AuthenticationError(IdentityError):
    """Authentication failed without disclosing the specific reason."""


class SessionError(IdentityError):
    """Session is missing, expired, revoked, or no longer authorized."""


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 12
    max_length: int = 256

    def validate(self, password: str) -> None:
        if not isinstance(password, str):
            raise PasswordPolicyError("Password must be text.")
        if len(password) < self.min_length:
            raise PasswordPolicyError(
                f"Password must contain at least {self.min_length} characters."
            )
        if len(password) > self.max_length:
            raise PasswordPolicyError(
                f"Password must contain at most {self.max_length} characters."
            )
        categories = (
            any(character.islower() for character in password),
            any(character.isupper() for character in password),
            any(character.isdigit() for character in password),
            any(not character.isalnum() for character in password),
        )
        if sum(categories) < 3:
            raise PasswordPolicyError(
                "Password must use at least three of: lowercase, uppercase, number, symbol."
            )


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    username: str
    username_normalized: str
    password_hash: str
    role: str
    enabled: bool
    created_at: str
    updated_at: str
    password_changed_at: str

    @classmethod
    def from_mapping(cls, value: object) -> "UserRecord":
        if not isinstance(value, dict):
            raise CredentialStoreError("Each credential record must be a JSON object.")
        try:
            record = cls(
                user_id=str(value["user_id"]),
                username=str(value["username"]),
                username_normalized=str(value["username_normalized"]),
                password_hash=str(value["password_hash"]),
                role=str(value["role"]),
                enabled=value["enabled"],
                created_at=str(value["created_at"]),
                updated_at=str(value["updated_at"]),
                password_changed_at=str(value["password_changed_at"]),
            )
        except (KeyError, TypeError) as exc:
            raise CredentialStoreError("Credential record is missing required fields.") from exc
        if type(record.enabled) is not bool:
            raise CredentialStoreError("Credential field 'enabled' must be boolean.")
        if normalize_username(record.username) != record.username_normalized:
            raise CredentialStoreError("Credential username normalization is inconsistent.")
        if not record.password_hash.startswith("$argon2id$"):
            raise CredentialStoreError("Credential hash is not Argon2id.")
        return record

    def public_mapping(self) -> dict[str, object]:
        """Return non-secret fields suitable for CLI listing."""

        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    username: str


@dataclass(frozen=True)
class LoginResult:
    session_token: str
    user: AuthenticatedUser


@dataclass
class _SessionRecord:
    user_id: str
    username: str
    password_changed_at: str
    created_at: float
    last_seen_at: float


def normalize_username(username: str) -> str:
    """Normalize for case-insensitive lookup without changing display form."""

    return username.strip().casefold()


def validate_username(username: str) -> str:
    cleaned = username.strip()
    if not USERNAME_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "Username must be 3-64 characters using letters, numbers, dot, dash, or underscore."
        )
    return cleaned


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat()


def build_password_hasher() -> PasswordHasher:
    """Return the explicit Argon2id hasher used for all local accounts."""

    return PasswordHasher(type=Type.ID)


class CredentialStore:
    """Atomic JSON credential store; never creates a default account."""

    def __init__(
        self,
        path: Path,
        *,
        password_hasher: PasswordHasher | None = None,
        harden_windows_acl: bool = False,
    ) -> None:
        self.path = Path(path)
        self._hasher = password_hasher or build_password_hasher()
        self._thread_lock = threading.RLock()
        self._harden_windows_acl = harden_windows_acl

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    def _empty_document(self) -> dict[str, object]:
        return {"version": STORE_VERSION, "users": []}

    def _load_document(self) -> dict[str, object]:
        try:
            if not self.path.exists():
                return self._empty_document()
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CredentialStoreError("Credential store cannot be read safely.") from exc
        if not isinstance(document, dict) or document.get("version") != STORE_VERSION:
            raise CredentialStoreError("Unsupported credential store format.")
        users = document.get("users")
        if not isinstance(users, list):
            raise CredentialStoreError("Credential store users must be a list.")
        records = [UserRecord.from_mapping(item) for item in users]
        normalized = [record.username_normalized for record in records]
        identifiers = [record.user_id for record in records]
        if len(normalized) != len(set(normalized)) or len(identifiers) != len(set(identifiers)):
            raise CredentialStoreError("Credential store contains duplicate identities.")
        return {"version": STORE_VERSION, "users": [asdict(record) for record in records]}

    def list_users(self) -> tuple[UserRecord, ...]:
        document = self._load_document()
        return tuple(UserRecord.from_mapping(item) for item in document["users"])

    def find_by_username(self, username: str) -> UserRecord | None:
        normalized = normalize_username(username)
        return next(
            (record for record in self.list_users() if record.username_normalized == normalized),
            None,
        )

    def find_by_id(self, user_id: str) -> UserRecord | None:
        return next((record for record in self.list_users() if record.user_id == user_id), None)

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        *,
        valid_roles: set[str],
        password_policy: PasswordPolicy,
    ) -> UserRecord:
        display_username = validate_username(username)
        normalized = normalize_username(display_username)
        if role not in valid_roles:
            raise ValueError(f"Unknown role: {role}")
        password_policy.validate(password)
        password_hash = self._hasher.hash(password)
        now = utc_now_text()
        record = UserRecord(
            user_id=str(uuid4()),
            username=display_username,
            username_normalized=normalized,
            password_hash=password_hash,
            role=role,
            enabled=True,
            created_at=now,
            updated_at=now,
            password_changed_at=now,
        )

        def mutation(document: dict[str, object]) -> UserRecord:
            users = document["users"]
            if any(item["username_normalized"] == normalized for item in users):
                raise AccountConflictError("Username already exists.")
            users.append(asdict(record))
            return record

        return self._mutate(mutation)

    def change_password(
        self,
        username: str,
        password: str,
        *,
        password_policy: PasswordPolicy,
    ) -> UserRecord:
        password_policy.validate(password)
        new_hash = self._hasher.hash(password)
        normalized = normalize_username(username)

        def mutation(document: dict[str, object]) -> UserRecord:
            now = utc_now_text()
            for index, item in enumerate(document["users"]):
                if item["username_normalized"] == normalized:
                    updated = dict(item)
                    updated.update(
                        password_hash=new_hash,
                        password_changed_at=now,
                        updated_at=now,
                    )
                    document["users"][index] = updated
                    return UserRecord.from_mapping(updated)
            raise AccountConflictError("Account does not exist.")

        return self._mutate(mutation)

    def disable_user(self, username: str) -> UserRecord:
        normalized = normalize_username(username)

        def mutation(document: dict[str, object]) -> UserRecord:
            for index, item in enumerate(document["users"]):
                if item["username_normalized"] == normalized:
                    updated = dict(item)
                    updated.update(enabled=False, updated_at=utc_now_text())
                    document["users"][index] = updated
                    return UserRecord.from_mapping(updated)
            raise AccountConflictError("Account does not exist.")

        return self._mutate(mutation)

    def enable_user(self, username: str) -> UserRecord:
        """Re-enable an existing local account without changing its password."""

        normalized = normalize_username(username)

        def mutation(document: dict[str, object]) -> UserRecord:
            for index, item in enumerate(document["users"]):
                if item["username_normalized"] == normalized:
                    updated = dict(item)
                    updated.update(enabled=True, updated_at=utc_now_text())
                    document["users"][index] = updated
                    return UserRecord.from_mapping(updated)
            raise AccountConflictError("Account does not exist.")

        return self._mutate(mutation)

    def _mutate(self, operation: Callable[[dict[str, object]], UserRecord]) -> UserRecord:
        with self._thread_lock, self._exclusive_file_lock():
            document = self._load_document()
            result = operation(document)
            self._atomic_write(document)
            return result

    def _atomic_write(self, document: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except OSError as exc:
            raise CredentialStoreError("Cannot secure credential directory permissions.") from exc
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                json.dump(document, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(temporary_name, self.path)
            temporary_name = None
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
            if self._harden_windows_acl and os.name == "nt":
                self._apply_windows_acl()
        except OSError as exc:
            raise CredentialStoreError("Credential update could not be published atomically.") from exc
        finally:
            if temporary_name:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning("Could not remove abandoned credential temporary file.")

    def _apply_windows_acl(self) -> None:
        username = getpass.getuser()
        commands = (
            [
                "icacls",
                str(self.path.parent),
                "/inheritance:r",
                "/grant:r",
                f"{username}:(OI)(CI)F",
                "SYSTEM:(OI)(CI)F",
            ],
            [
                "icacls",
                str(self.path),
                "/inheritance:r",
                "/grant:r",
                f"{username}:F",
                "SYSTEM:F",
            ],
        )
        for command in commands:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                shell=False,
            )
            if completed.returncode != 0:
                raise CredentialStoreError("Windows ACL hardening failed; account store is not safe.")

    @contextmanager
    def _exclusive_file_lock(self, timeout_seconds: float = 5.0) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.lock_path.open("a+b")
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        deadline = time.monotonic() + timeout_seconds
        acquired = False
        try:
            while not acquired:
                try:
                    lock_file.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise CredentialStoreError("Credential store is busy.") from exc
                    time.sleep(0.05)
            yield
        finally:
            if acquired:
                lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


@dataclass
class _AttemptState:
    failures: deque[float]
    locked_until: float = 0.0


class LoginRateLimiter:
    """Thread-safe, server-side limiter by account and browser-session scope."""

    def __init__(
        self,
        *,
        account_max_failures: int,
        session_max_failures: int,
        window_seconds: float,
        lockout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.account_max_failures = account_max_failures
        self.session_max_failures = session_max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._clock = clock
        self._states: dict[tuple[str, str], _AttemptState] = {}
        self._lock = threading.RLock()

    def _state(self, kind: str, key: str) -> _AttemptState:
        return self._states.setdefault((kind, key), _AttemptState(deque()))

    def _prune(self, state: _AttemptState, now: float) -> None:
        cutoff = now - self.window_seconds
        while state.failures and state.failures[0] < cutoff:
            state.failures.popleft()
        if state.locked_until <= now:
            state.locked_until = 0.0

    def is_limited(self, username: str, scope: str) -> bool:
        account = normalize_username(username)
        now = self._clock()
        with self._lock:
            states = (self._state("account", account), self._state("session", scope))
            for state in states:
                self._prune(state, now)
            return any(state.locked_until > now for state in states)

    def record_failure(self, username: str, scope: str) -> None:
        account = normalize_username(username)
        now = self._clock()
        with self._lock:
            pairs = (
                (self._state("account", account), self.account_max_failures),
                (self._state("session", scope), self.session_max_failures),
            )
            for state, limit in pairs:
                self._prune(state, now)
                state.failures.append(now)
                if len(state.failures) >= limit:
                    state.locked_until = now + self.lockout_seconds

    def record_success(self, username: str, scope: str) -> None:
        with self._lock:
            self._states.pop(("account", normalize_username(username)), None)
            self._states.pop(("session", scope), None)


class ServerSessionRegistry:
    """Authoritative in-process session registry; clients only receive tokens."""

    def __init__(
        self,
        idle_timeout_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.idle_timeout_seconds = idle_timeout_seconds
        self._clock = clock
        self._sessions: dict[str, _SessionRecord] = {}
        self._lock = threading.RLock()

    def create(self, user: UserRecord) -> str:
        now = self._clock()
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = _SessionRecord(
                user_id=user.user_id,
                username=user.username,
                password_changed_at=user.password_changed_at,
                created_at=now,
                last_seen_at=now,
            )
        return token

    def get_and_touch(self, token: str) -> _SessionRecord:
        now = self._clock()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                raise SessionError("Authentication required.")
            if now - session.last_seen_at > self.idle_timeout_seconds:
                self._sessions.pop(token, None)
                raise SessionError("Session expired.")
            session.last_seen_at = now
            return _SessionRecord(**asdict(session))

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)


class AuthenticationService:
    """Authenticate accounts and continuously revalidate server sessions."""

    def __init__(
        self,
        store: CredentialStore,
        admin_username: str,
        sessions: ServerSessionRegistry,
        limiter: LoginRateLimiter,
        *,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.store = store
        self.admin_username = validate_username(admin_username)
        self.admin_username_normalized = normalize_username(self.admin_username)
        self.sessions = sessions
        self.limiter = limiter
        self._hasher = password_hasher or build_password_hasher()
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(24))

    def authenticate(self, username: str, password: str, *, scope: str) -> LoginResult:
        if self.limiter.is_limited(username, scope):
            LOGGER.warning("auth_login_limited scope=%s", scope)
            raise AuthenticationError("Invalid username or password.")

        record = self.store.find_by_username(username)
        candidate_hash = record.password_hash if record else self._dummy_hash
        verified = False
        try:
            verified = self._hasher.verify(candidate_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            verified = False

        if (
            not verified
            or record is None
            or not record.enabled
            or record.username_normalized != self.admin_username_normalized
        ):
            self.limiter.record_failure(username, scope)
            LOGGER.warning("auth_login_failed scope=%s", scope)
            raise AuthenticationError("Invalid username or password.")

        self.limiter.record_success(username, scope)
        token = self.sessions.create(record)
        user = AuthenticatedUser(record.user_id, record.username)
        LOGGER.info("auth_login_success user_id=%s", user.user_id)
        return LoginResult(token, user)

    def validate_session(self, token: str) -> AuthenticatedUser:
        session = self.sessions.get_and_touch(token)
        current = self.store.find_by_id(session.user_id)
        if (
            current is None
            or not current.enabled
            or current.username != session.username
            or current.username_normalized != self.admin_username_normalized
            or current.password_changed_at != session.password_changed_at
        ):
            self.sessions.revoke(token)
            raise SessionError("Session is no longer valid.")
        return AuthenticatedUser(current.user_id, current.username)

    def logout(self, token: str) -> None:
        try:
            session = self.sessions.get_and_touch(token)
            LOGGER.info("auth_logout user_id=%s", session.user_id)
        except SessionError:
            pass
        self.sessions.revoke(token)
