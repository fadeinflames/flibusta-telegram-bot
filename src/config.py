import os

SITE = "http://flibusta.is"
ALL_FORMATS = ["fb2", "epub", "mobi", "pdf", "djvu"]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Requests timeouts (connect, read)
REQUEST_TIMEOUT = (10, 30)

# Cache for parsed pages
PAGE_CACHE_TTL_SEC = 300
PAGE_CACHE_MAX_SIZE = 128

# Local storage
DATA_DIR = os.path.join(os.getcwd(), "data")
BOOKS_DIR = os.path.join(os.getcwd(), "books")
DB_PATH = os.path.join(DATA_DIR, "flibusta_bot.db")

# Pagination defaults
BOOKS_PER_PAGE_DEFAULT = 10
FAVORITES_PER_PAGE_DEFAULT = 10

# Search cache
SEARCH_CACHE_TTL_SEC = 120
SEARCH_CACHE_MAX_SIZE = 256
