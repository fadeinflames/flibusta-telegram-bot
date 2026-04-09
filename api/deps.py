"""FastAPI dependencies: auth, database access."""

import asyncio
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from api.auth import validate_init_data


async def get_current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    """Extract and validate Telegram user from Authorization header.

    Expected format: Authorization: tma <initData>
    """
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")

    init_data = authorization[4:]
    result = await asyncio.to_thread(validate_init_data, init_data)

    if not result or not result.get("user"):
        raise HTTPException(status_code=401, detail="Invalid or expired initData")

    return result["user"]


CurrentUser = Annotated[dict, Depends(get_current_user)]
