"""Telegram WebApp initData validation (HMAC-SHA256) + JWT."""

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from jose import jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

_JWT_DEFAULT = "dev-secret-change-me"


def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", _JWT_DEFAULT)
    if secret == _JWT_DEFAULT:
        import logging
        logging.getLogger(__name__).warning(
            "JWT_SECRET not set — using insecure default! Set JWT_SECRET in .env for production."
        )
    return secret


def get_bot_token() -> str:
    return os.getenv("TOKEN", "")


def validate_init_data(init_data: str, bot_token: str | None = None, max_age: int = 86400) -> dict | None:
    """Validate Telegram WebApp initData and return parsed data.

    Returns user dict on success, None on failure.
    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None

    token = bot_token or get_bot_token()
    if not token:
        return None

    # Parse the query string
    parsed = urllib.parse.parse_qs(init_data, keep_blank_values=True)

    # Extract hash
    received_hash = parsed.pop("hash", [None])[0]
    if not received_hash:
        return None

    # Check auth_date freshness
    auth_date_str = parsed.get("auth_date", [None])[0]
    if not auth_date_str:
        return None

    try:
        auth_date = int(auth_date_str)
    except (ValueError, TypeError):
        return None

    if max_age > 0 and (time.time() - auth_date) > max_age:
        return None

    # Build data-check-string: sorted key=value pairs joined with \n
    data_check_parts = []
    for key in sorted(parsed.keys()):
        val = parsed[key][0]
        data_check_parts.append(f"{key}={val}")
    data_check_string = "\n".join(data_check_parts)

    # HMAC validation
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    # Parse user data
    user_data_str = parsed.get("user", [None])[0]
    if not user_data_str:
        return None

    try:
        user = json.loads(user_data_str)
    except (json.JSONDecodeError, TypeError):
        return None

    return {
        "user": user,
        "auth_date": auth_date,
        "query_id": parsed.get("query_id", [None])[0],
    }


def create_access_token(user: dict) -> str:
    """Create JWT token for an authenticated Telegram user."""
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user["id"]),
        "first_name": user.get("first_name", ""),
        "username": user.get("username"),
        "photo_url": user.get("photo_url"),
        "exp": expire,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate JWT token. Returns user dict or None."""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        return {
            "id": int(user_id_str),
            "first_name": payload.get("first_name", ""),
            "username": payload.get("username"),
            "photo_url": payload.get("photo_url"),
        }
    except (jwt.JWTError, jwt.ExpiredSignatureError, ValueError, KeyError):
        return None
