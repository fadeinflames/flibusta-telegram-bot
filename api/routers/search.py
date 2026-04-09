"""Search endpoints."""

import asyncio

from fastapi import APIRouter, Query

from api.deps import CurrentUser
from api.schemas import BookBrief, PaginatedResponse, SearchHistoryItem
from src import database as db
from src import flib

router = APIRouter(prefix="/api/search", tags=["search"])


def _flatten_author_results(author_groups: list[list[flib.Book]]) -> list[flib.Book]:
    """Flatten author search results (list of lists) into flat list."""
    result = []
    for group in author_groups:
        result.extend(group)
    return result


@router.get("", response_model=PaginatedResponse)
async def search_books(
    user: CurrentUser,
    q: str = Query(..., min_length=1),
    type: str = Query("title", pattern="^(title|author|exact)$"),
    page: int = 1,
    per_page: int = 20,
):
    user_id = str(user["id"])

    if type == "title":
        books = await asyncio.to_thread(flib.scrape_books_by_title, q)
    elif type == "author":
        author_results = await asyncio.to_thread(flib.scrape_books_by_author, q)
        books = _flatten_author_results(author_results) if author_results else None
    else:
        parts = q.split(" - ", 1)
        title = parts[0].strip()
        author = parts[1].strip() if len(parts) > 1 else ""
        books = await asyncio.to_thread(flib.scrape_books_mbl, title, author)

    if not books:
        # Record search with 0 results
        await asyncio.to_thread(db.add_search_history, user_id, type, q, 0)
        return PaginatedResponse(items=[], total=0, page=page, per_page=per_page)

    # Record search
    await asyncio.to_thread(db.add_search_history, user_id, type, q, len(books))

    # Paginate
    total = len(books)
    start = (page - 1) * per_page
    end = start + per_page
    page_books = books[start:end]

    items = [
        BookBrief(id=b.id, title=b.title, author=b.author, cover=b.cover).model_dump()
        for b in page_books
    ]
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/history")
async def get_search_history(user: CurrentUser, page: int = 1, per_page: int = 20):
    user_id = str(user["id"])
    offset = (page - 1) * per_page
    items, total = await asyncio.to_thread(db.get_user_search_history_paginated, user_id, offset, per_page)
    history = [
        SearchHistoryItem(
            command=h["command"],
            query=h["query"],
            results_count=h.get("results_count", 0),
            timestamp=h.get("timestamp", ""),
        ).model_dump()
        for h in items
    ]
    return PaginatedResponse(items=history, total=total, page=page, per_page=per_page)


@router.delete("/history")
async def clear_search_history(user: CurrentUser):
    user_id = str(user["id"])
    deleted = await asyncio.to_thread(db.clear_search_history, user_id)
    return {"deleted": deleted}
