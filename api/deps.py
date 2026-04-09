"""FastAPI dependencies: JWT auth, current user."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from api.auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/telegram-webapp")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    """Extract and validate user from JWT Bearer token."""
    user = decode_access_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]
