"""Auth endpoints: Telegram WebApp initData / Login Widget -> JWT."""

import asyncio
import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.auth import validate_init_data, create_access_token, get_bot_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class WebAppAuthRequest(BaseModel):
    init_data: str


class TelegramWidgetAuth(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/telegram-webapp", response_model=AuthResponse)
async def telegram_webapp_auth(body: WebAppAuthRequest):
    """Validate Telegram Mini App initData and return JWT token."""
    result = await asyncio.to_thread(validate_init_data, body.init_data)
    if not result or not result.get("user"):
        raise HTTPException(status_code=401, detail="Invalid or expired initData")

    user = result["user"]
    token = create_access_token(user)

    return AuthResponse(
        access_token=token,
        user={
            "user_id": user["id"],
            "first_name": user.get("first_name", ""),
            "username": user.get("username"),
            "photo_url": user.get("photo_url"),
        },
    )


@router.post("/telegram-widget", response_model=AuthResponse)
async def telegram_widget_auth(body: TelegramWidgetAuth):
    """Validate Telegram Login Widget data and return JWT token."""
    bot_token = get_bot_token()
    if not bot_token:
        raise HTTPException(status_code=503, detail="BOT_TOKEN not configured")

    # Verify hash: secret = SHA256(bot_token), NOT HMAC like Mini App
    fields = {"id": str(body.id), "first_name": body.first_name, "auth_date": str(body.auth_date)}
    if body.last_name:
        fields["last_name"] = body.last_name
    if body.username:
        fields["username"] = body.username
    if body.photo_url:
        fields["photo_url"] = body.photo_url

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, body.hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth hash")

    if int(time.time()) - body.auth_date > 86400:
        raise HTTPException(status_code=401, detail="Telegram auth data expired")

    user = {
        "id": body.id,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "username": body.username,
        "photo_url": body.photo_url,
    }
    token = create_access_token(user)

    return AuthResponse(
        access_token=token,
        user={
            "user_id": user["id"],
            "first_name": user["first_name"],
            "username": user.get("username"),
            "photo_url": user.get("photo_url"),
        },
    )
