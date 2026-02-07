import os
from pathlib import Path

# Base directory — parent of src/
BASE_DIR = Path(__file__).resolve().parent.parent

# ──────────────────── Site ────────────────────
SITE = os.getenv("FLIBUSTA_SITE", "http://flibusta.is")
ALL_FORMATS = ["fb2", "epub", "mobi", "pdf", "djvu"]
KINDLE_FORMATS = ["epub", "mobi", "pdf", "fb2"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ──────────────────── Requests ────────────────────
REQUEST_TIMEOUT = (10, 30)
REQUEST_MAX_RETRIES = 3
REQUEST_RETRY_BACKOFF = 1.0  # seconds, multiplied by attempt number

# ──────────────────── Page cache ────────────────────
PAGE_CACHE_TTL_SEC = 300
PAGE_CACHE_MAX_SIZE = 128

# ──────────────────── Local storage ────────────────────
DATA_DIR = os.getenv("DATA_DIR", str(BASE_DIR / "data"))
BOOKS_DIR = os.getenv("BOOKS_DIR", str(BASE_DIR / "books"))
LOGS_DIR = os.getenv("LOGS_DIR", str(BASE_DIR / "logs"))
DB_PATH = os.path.join(DATA_DIR, "flibusta_bot.db")
LOG_FILE = os.path.join(LOGS_DIR, "search_log.log")

# ──────────────────── Pagination ────────────────────
BOOKS_PER_PAGE_DEFAULT = 10
FAVORITES_PER_PAGE_DEFAULT = 10

# ──────────────────── Search cache ────────────────────
SEARCH_CACHE_TTL_SEC = 120
SEARCH_CACHE_MAX_SIZE = 256

# ──────────────────── Achievements / levels ────────────────────
ACHIEVEMENT_LEVELS = [
    {"name": "📖 Новичок", "searches": 0, "downloads": 0},
    {"name": "📚 Читатель", "searches": 10, "downloads": 5},
    {"name": "📕 Библиофил", "searches": 50, "downloads": 20},
    {"name": "🏛 Книгочей", "searches": 100, "downloads": 50},
    {"name": "🎓 Эрудит", "searches": 500, "downloads": 100},
    {"name": "👑 Мастер", "searches": 1000, "downloads": 250},
]

# ──────────────────── Favorite shelves / tags ────────────────────
FAVORITE_SHELVES = {
    "want": "📕 Хочу прочитать",
    "reading": "📗 Читаю",
    "done": "📘 Прочитано",
    "recommend": "📙 Рекомендую",
}
