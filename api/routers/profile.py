"""User profile and preferences endpoints."""

import asyncio
import json

from fastapi import APIRouter

from api.deps import CurrentUser
from api.schemas import PreferencesUpdate, UserProfile
from src import config
from src import database as db

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _compute_level(search_count: int, download_count: int) -> tuple[str, int, float]:
    """Compute achievement level, index, and progress to next level."""
    levels = config.ACHIEVEMENT_LEVELS
    current_idx = 0

    for i, level in enumerate(levels):
        if search_count >= level["searches"] and download_count >= level["downloads"]:
            current_idx = i

    level_name = levels[current_idx]["name"]

    # Progress to next level
    progress = 1.0
    if current_idx < len(levels) - 1:
        next_level = levels[current_idx + 1]
        curr_level = levels[current_idx]

        search_range = next_level["searches"] - curr_level["searches"]
        download_range = next_level["downloads"] - curr_level["downloads"]

        search_progress = (search_count - curr_level["searches"]) / search_range if search_range > 0 else 1.0
        download_progress = (download_count - curr_level["downloads"]) / download_range if download_range > 0 else 1.0

        progress = min((search_progress + download_progress) / 2, 1.0)

    return level_name, current_idx, progress


@router.get("", response_model=UserProfile)
async def get_profile(user: CurrentUser):
    user_id = str(user["id"])

    # Ensure user exists in DB
    await asyncio.to_thread(
        db.add_or_update_user,
        user_id,
        user.get("username", ""),
        f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
    )

    db_user = await asyncio.to_thread(db.get_user, user_id)
    if not db_user:
        return UserProfile(user_id=user_id)

    counts = await asyncio.to_thread(db.get_favorites_count_by_tag, user_id)
    favorites_count = sum(counts.values())

    level_name, level_idx, progress = _compute_level(
        db_user.get("search_count", 0),
        db_user.get("download_count", 0),
    )

    return UserProfile(
        user_id=user_id,
        username=db_user.get("username", ""),
        full_name=db_user.get("full_name", ""),
        first_seen=db_user.get("first_seen", ""),
        search_count=db_user.get("search_count", 0),
        download_count=db_user.get("download_count", 0),
        favorites_count=favorites_count,
        level_name=level_name,
        level_index=level_idx,
        level_progress=progress,
    )


@router.get("/preferences")
async def get_preferences(user: CurrentUser):
    user_id = str(user["id"])
    db_user = await asyncio.to_thread(db.get_user, user_id)
    if not db_user:
        return {"default_format": "fb2", "books_per_page": 10}

    prefs = json.loads(db_user.get("preferences", "{}") or "{}")
    return {
        "default_format": prefs.get("default_format", "fb2"),
        "books_per_page": prefs.get("books_per_page", 10),
    }


@router.patch("/preferences")
async def update_preferences(body: PreferencesUpdate, user: CurrentUser):
    user_id = str(user["id"])
    if body.default_format is not None:
        await asyncio.to_thread(db.set_user_preference, user_id, "default_format", body.default_format)
    if body.books_per_page is not None:
        await asyncio.to_thread(db.set_user_preference, user_id, "books_per_page", body.books_per_page)
    return {"status": "updated"}
