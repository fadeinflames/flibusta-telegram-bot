"""Downloads history endpoints."""

import asyncio

from fastapi import APIRouter

from api.deps import CurrentUser
from api.schemas import DownloadItem, PaginatedResponse
from src import database as db

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.get("", response_model=PaginatedResponse)
async def get_downloads(user: CurrentUser, page: int = 1, per_page: int = 20):
    user_id = str(user["id"])
    all_downloads = await asyncio.to_thread(db.get_user_downloads, user_id, 1000)
    total = len(all_downloads)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = all_downloads[start:end]

    # Fetch covers from books_cache
    book_ids = list({d["book_id"] for d in page_items})
    covers = await asyncio.to_thread(db.get_cached_covers, book_ids) if book_ids else {}

    items = [
        DownloadItem(
            book_id=d["book_id"],
            title=d["title"],
            author=d["author"],
            cover=covers.get(d["book_id"], ""),
            format=d["format"],
            download_date=d.get("download_date", ""),
        ).model_dump()
        for d in page_items
    ]
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)


@router.delete("")
async def clear_downloads(user: CurrentUser):
    user_id = str(user["id"])
    deleted = await asyncio.to_thread(db.clear_download_history, user_id)
    return {"deleted": deleted}
