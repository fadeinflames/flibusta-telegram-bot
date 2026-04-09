"""Library (favorites/shelves) endpoints."""

import asyncio

from fastapi import APIRouter

from api.deps import CurrentUser
from api.schemas import FavoriteAdd, FavoriteItem, FavoriteUpdate, PaginatedResponse, ShelfCounts
from src import database as db

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("", response_model=PaginatedResponse)
async def get_library(user: CurrentUser, shelf: str | None = None, page: int = 1, per_page: int = 20):
    user_id = str(user["id"])
    offset = (page - 1) * per_page
    tag = shelf if shelf and shelf != "all" else None

    items, total = await asyncio.to_thread(db.get_user_favorites, user_id, offset, per_page, tag)
    favorites = [
        FavoriteItem(
            book_id=f["book_id"],
            title=f["title"],
            author=f["author"],
            shelf=f.get("tags"),
            notes=f.get("notes"),
            added_date=f.get("added_date", ""),
        ).model_dump()
        for f in items
    ]
    return PaginatedResponse(items=favorites, total=total, page=page, per_page=per_page)


@router.get("/counts", response_model=ShelfCounts)
async def get_shelf_counts(user: CurrentUser):
    user_id = str(user["id"])
    counts = await asyncio.to_thread(db.get_favorites_count_by_tag, user_id)

    total = sum(counts.values())
    return ShelfCounts(
        all=total,
        want=counts.get("want", 0),
        reading=counts.get("reading", 0),
        done=counts.get("done", 0),
        recommend=counts.get("recommend", 0),
    )


@router.post("/{book_id}")
async def add_to_library(book_id: str, body: FavoriteAdd, user: CurrentUser):
    user_id = str(user["id"])
    ok = await asyncio.to_thread(
        db.add_to_favorites, user_id, book_id, body.title, body.author, body.shelf, body.notes
    )
    if not ok:
        return {"status": "already_exists"}
    return {"status": "added"}


@router.delete("/{book_id}")
async def remove_from_library(book_id: str, user: CurrentUser):
    user_id = str(user["id"])
    removed = await asyncio.to_thread(db.remove_from_favorites, user_id, book_id)
    return {"status": "removed" if removed else "not_found"}


@router.patch("/{book_id}")
async def update_library_item(book_id: str, body: FavoriteUpdate, user: CurrentUser):
    user_id = str(user["id"])
    if body.shelf is not None:
        await asyncio.to_thread(db.update_favorite_tags, user_id, book_id, body.shelf)
    if body.notes is not None:
        await asyncio.to_thread(db.update_favorite_notes, user_id, book_id, body.notes)
    return {"status": "updated"}
