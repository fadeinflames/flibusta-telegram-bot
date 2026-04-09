"""Auth endpoints: Telegram WebApp initData -> JWT."""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.auth import validate_init_data, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class WebAppAuthRequest(BaseModel):
    init_data: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/telegram-webapp", response_model=AuthResponse)
async def telegram_webapp_auth(body: WebAppAuthRequest):
    """Validate Telegram initData and return JWT token."""
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
