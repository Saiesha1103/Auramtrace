"""Password hashing (bcrypt) and JWT access tokens."""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from ..config import get_settings


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; reject rather than silently truncate
    raw = password.encode("utf-8")
    if len(raw) > 72:
        raise ValueError("Password is too long (max 72 bytes)")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > 72:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, organisation_id: uuid.UUID, role: str) -> tuple[str, int]:
    s = get_settings()
    expires_in = s.access_token_minutes * 60
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "org": str(organisation_id), "role": role, "iat": now, "exp": now + timedelta(seconds=expires_in), "typ": "access"}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), expires_in


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["sub", "org", "exp"]})
