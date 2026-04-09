"""Telegram WebApp initData validation (HMAC-SHA256)."""

import hashlib
import hmac
import json
import os
import time
import urllib.parse


def validate_init_data(init_data: str, bot_token: str | None = None, max_age: int = 86400) -> dict | None:
    """Validate Telegram WebApp initData and return parsed data.

    Returns user dict on success, None on failure.
    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None

    token = bot_token or os.getenv("TOKEN", "")
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
    # Each value is the first element (parse_qs returns lists)
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
