"""Book detail and download endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import CurrentUser
from api.schemas import BookBrief, BookDetail
from src import database as db
from src import flib

router = APIRouter(prefix="/api/books", tags=["books"])


async def _get_book(book_id: str) -> flib.Book | None:
    """Get book from cache or scrape it."""
    cached = await asyncio.to_thread(db.get_cached_book, book_id)
    if cached:
        return flib.Book.from_dict(cached)

    book = await asyncio.to_thread(flib.get_book_by_id, book_id)
    if book:
        await asyncio.to_thread(db.cache_book, book)
    return book


@router.get("/{book_id}", response_model=BookDetail)
async def get_book(book_id: str, user: CurrentUser):
    book = await _get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    user_id = str(user["id"])
    is_fav = await asyncio.to_thread(db.is_favorite, user_id, book_id)

    shelf = None
    if is_fav:
        favorites, _ = await asyncio.to_thread(db.get_user_favorites, user_id, 0, 1000)
        for f in favorites:
            if f["book_id"] == book_id:
                shelf = f.get("tags")
                break

    return BookDetail(
        id=book.id,
        title=book.title,
        author=book.author,
        cover=book.cover,
        formats=book.formats,
        size=book.size,
        series=book.series,
        year=book.year,
        annotation=book.annotation,
        genres=book.genres,
        rating=book.rating,
        author_link=book.author_link,
        is_favorite=is_fav,
        shelf=shelf,
    )


@router.get("/{book_id}/download/{fmt}")
async def download_book(book_id: str, fmt: str, user: CurrentUser):
    book = await _get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Find matching format key
    format_key = None
    for key in book.formats:
        if fmt.lower() in key.lower():
            format_key = key
            break

    if not format_key:
        raise HTTPException(status_code=404, detail=f"Format '{fmt}' not available")

    buf, filename = await asyncio.to_thread(flib.download_book, book, format_key)
    if not buf:
        raise HTTPException(status_code=502, detail="Download failed")

    # Record download
    user_id = str(user["id"])
    await asyncio.to_thread(db.add_download, user_id, book_id, book.title, book.author, fmt)

    content_type = "application/octet-stream"
    return StreamingResponse(
        buf,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{book_id}/related", response_model=list[BookBrief])
async def get_related_books(book_id: str, user: CurrentUser):
    book = await _get_book(book_id)
    if not book or not book.author_link:
        return []

    related = await asyncio.to_thread(flib.get_other_books_by_author, book.author_link, book_id, 10)
    return [BookBrief(id=b.id, title=b.title, author=b.author, cover=b.cover) for b in related]
