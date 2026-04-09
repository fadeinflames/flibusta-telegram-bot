"""Book detail and download endpoints."""

import asyncio
import zipfile

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from api.auth import decode_access_token
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
async def download_book(book_id: str, fmt: str, token: str = Query(...)):
    """Download book file. Auth via query param `token` (JWT)."""
    user = decode_access_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
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


@router.get("/{book_id}/content/{fmt}")
async def get_book_content(book_id: str, fmt: str, token: str = Query(...)):
    """Return raw book content for in-app reading. Supports fb2."""
    user = decode_access_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if fmt.lower() not in ("fb2",):
        raise HTTPException(status_code=400, detail="Only fb2 format is supported for reading")

    book = await _get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Find matching format key
    format_key = None
    for key in book.formats:
        if "fb2" in key.lower():
            format_key = key
            break

    if not format_key:
        raise HTTPException(status_code=404, detail="FB2 format not available for this book")

    buf, filename = await asyncio.to_thread(flib.download_book, book, format_key)
    if not buf:
        raise HTTPException(status_code=502, detail="Download failed")

    content = buf.read()

    # Handle .fb2.zip — extract the .fb2 file from the zip
    if content[:4] == b"PK\x03\x04":
        import io
        zf = zipfile.ZipFile(io.BytesIO(content))
        fb2_names = [n for n in zf.namelist() if n.lower().endswith(".fb2")]
        if not fb2_names:
            raise HTTPException(status_code=502, detail="No .fb2 file found in archive")
        content = zf.read(fb2_names[0])

    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{book_id}/related", response_model=list[BookBrief])
async def get_related_books(book_id: str, user: CurrentUser):
    book = await _get_book(book_id)
    if not book or not book.author_link:
        return []

    related = await asyncio.to_thread(flib.get_other_books_by_author, book.author_link, book_id, 10)

    # Enrich with covers from cache (get_other_books_by_author doesn't parse covers)
    book_ids = [b.id for b in related]
    covers = await asyncio.to_thread(db.get_cached_covers, book_ids) if book_ids else {}

    return [BookBrief(id=b.id, title=b.title, author=b.author, cover=covers.get(b.id, "")) for b in related]
