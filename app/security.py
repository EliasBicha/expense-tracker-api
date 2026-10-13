"""Password hashing (Argon2id) and JWT access tokens."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.errors import AuthError

# argon2-cffi defaults to Argon2id with OWASP-recommended parameters.
# Unlike bcrypt, Argon2 has no 72-byte password truncation.
_hasher = PasswordHasher()

# Verified against when the email is unknown, so a login attempt costs the same
# time whether or not the account exists (AUTH-05).
_DUMMY_HASH = _hasher.hash("timing-equalisation-dummy-password")

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """Return (token, lifetime in seconds)."""
    settings = get_settings()
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "iat": now, "exp": now + lifetime}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> uuid.UUID:
    """Return the user id from a valid token, or raise AuthError (AUTH-06, AUTH-07).

    `algorithms` is pinned so a token can't choose its own algorithm (e.g. "none").
    """
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthError("Invalid or expired token") from exc
