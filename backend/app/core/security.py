from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import secrets

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def _prepare_password_for_bcrypt(password: str) -> bytes:
    """
    Prepare password for bcrypt hashing.

    Bcrypt has a 72-byte limit. If password exceeds this, we hash it with
    SHA-256 first to get a fixed 32-byte digest.
    This ensures passwords of any length can be hashed securely.
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        return password_bytes
    password_hash = hashlib.sha256(password_bytes).digest()
    return password_hash


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    prepared_password = _prepare_password_for_bcrypt(plain_password)
    return bcrypt.checkpw(prepared_password, hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    prepared_password = _prepare_password_for_bcrypt(password)
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(prepared_password, salt)
    return hashed.decode("utf-8")


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


def create_refresh_token() -> str:
    """Generate a secure random refresh token."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token using bcrypt before storage."""
    token_bytes = token.encode("utf-8")
    if len(token_bytes) <= 72:
        prepared_token = token_bytes
    else:
        prepared_token = hashlib.sha256(token_bytes).digest()

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(prepared_token, salt)
    return hashed.decode("utf-8")


def verify_refresh_token_hash(plain_token: str, hashed_token: str) -> bool:
    """Verify a plain refresh token against a hashed token."""
    token_bytes = plain_token.encode("utf-8")
    if len(token_bytes) <= 72:
        prepared_token = token_bytes
    else:
        prepared_token = hashlib.sha256(token_bytes).digest()

    return bcrypt.checkpw(prepared_token, hashed_token.encode("utf-8"))
