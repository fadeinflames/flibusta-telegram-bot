"""Pydantic models for API request/response."""

from pydantic import BaseModel


class BookBrief(BaseModel):
    id: str
    title: str
    author: str
    cover: str = ""


class BookDetail(BaseModel):
    id: str
    title: str
    author: str
    cover: str = ""
    formats: dict = {}
    size: str = ""
    series: str = ""
    year: str = ""
    annotation: str = ""
    genres: list[str] = []
    rating: str = ""
    author_link: str = ""
    is_favorite: bool = False
    shelf: str | None = None


class FavoriteItem(BaseModel):
    book_id: str
    title: str
    author: str
    shelf: str | None = None
    notes: str | None = None
    added_date: str = ""


class FavoriteAdd(BaseModel):
    title: str
    author: str
    shelf: str | None = None
    notes: str | None = None


class FavoriteUpdate(BaseModel):
    shelf: str | None = None
    notes: str | None = None


class DownloadItem(BaseModel):
    book_id: str
    title: str
    author: str
    format: str
    download_date: str = ""


class SearchHistoryItem(BaseModel):
    command: str
    query: str
    results_count: int = 0
    timestamp: str = ""


class UserProfile(BaseModel):
    user_id: str
    username: str = ""
    full_name: str = ""
    first_seen: str = ""
    search_count: int = 0
    download_count: int = 0
    favorites_count: int = 0
    level_name: str = ""
    level_index: int = 0
    level_progress: float = 0.0


class PreferencesUpdate(BaseModel):
    default_format: str | None = None
    books_per_page: int | None = None


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    per_page: int


class ShelfCounts(BaseModel):
    all: int = 0
    want: int = 0
    reading: int = 0
    done: int = 0
    recommend: int = 0
