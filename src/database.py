import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from src import config

DB_PATH = config.DB_PATH

# ────────────────────── Per-thread persistent connection ──────────────────────

_thread_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a per-thread persistent connection (created once, reused)."""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        return conn
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    _thread_local.conn = conn
    return conn


@contextmanager
def get_db():
    """Контекстный менеджер — reuses per-thread connection."""
    conn = _get_conn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise


def close_connections():
    """Close per-thread connection (for cleanup / testing)."""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        conn.close()
        _thread_local.conn = None


def init_database():
    """Инициализация базы данных."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                search_count INTEGER DEFAULT 0,
                download_count INTEGER DEFAULT 0,
                is_admin BOOLEAN DEFAULT 0,
                preferences TEXT DEFAULT '{}',
                is_banned BOOLEAN DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                command TEXT,
                query TEXT,
                results_count INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                book_id TEXT,
                title TEXT,
                author TEXT,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                tags TEXT,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                UNIQUE(user_id, book_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                book_id TEXT,
                title TEXT,
                author TEXT,
                format TEXT,
                download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books_cache (
                book_id TEXT PRIMARY KEY,
                title TEXT,
                author TEXT,
                link TEXT,
                formats TEXT,
                cover TEXT,
                size TEXT,
                series TEXT,
                year TEXT,
                cached_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
        """)

        # Миграция: добавляем новые колонки в books_cache
        for col, col_type in [
            ("annotation", 'TEXT DEFAULT ""'),
            ("genres", 'TEXT DEFAULT "[]"'),
            ("rating", 'TEXT DEFAULT ""'),
            ("author_link", 'TEXT DEFAULT ""'),
        ]:
            try:
                cursor.execute(f"ALTER TABLE books_cache ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_timestamp ON search_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_tags ON favorites(user_id, tags)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_downloads_book ON downloads(book_id)")

        conn.commit()

    init_audiobook_tables()
    init_reading_progress_tables()


# ────────────────────── Пользователи ──────────────────────


def add_or_update_user(user_id: str, username: str = None, full_name: str = None, is_admin: bool = False):
    """Добавить или обновить пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (user_id, username, full_name, is_admin)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(?, username),
                full_name = COALESCE(?, full_name),
                last_seen = CURRENT_TIMESTAMP
        """,
            (user_id, username, full_name, is_admin, username, full_name),
        )
        conn.commit()


def get_user(user_id: str) -> dict | None:
    """Получить информацию о пользователе."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_user_stats(user_id: str, search: bool = False, download: bool = False):
    """Обновить статистику пользователя (отдельный вызов, когда нужно)."""
    with get_db() as conn:
        cursor = conn.cursor()
        if search:
            cursor.execute(
                """
                UPDATE users SET search_count = search_count + 1, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """,
                (user_id,),
            )
        if download:
            cursor.execute(
                """
                UPDATE users SET download_count = download_count + 1, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """,
                (user_id,),
            )
        conn.commit()


def set_user_preference(user_id: str, key: str, value):
    """Установить настройку пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT preferences FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            prefs = json.loads(row["preferences"] or "{}")
            prefs[key] = value
            cursor.execute("UPDATE users SET preferences = ? WHERE user_id = ?", (json.dumps(prefs), user_id))
            conn.commit()


def get_user_preference(user_id: str, key: str, default=None):
    """Получить настройку пользователя."""
    user = get_user(user_id)
    if user:
        prefs = json.loads(user["preferences"] or "{}")
        return prefs.get(key, default)
    return default


# ────────────────────── История поиска ──────────────────────


def add_search_history(user_id: str, command: str, query: str, results_count: int = 0):
    """Добавить запись в историю поиска и обновить счётчик в одной транзакции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO search_history (user_id, command, query, results_count)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, command, query, results_count),
        )
        cursor.execute(
            """
            UPDATE users SET search_count = search_count + 1, last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """,
            (user_id,),
        )
        conn.commit()


def get_user_search_history(user_id: str, limit: int = 10) -> list[dict]:
    """Получить историю поиска пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM search_history
            WHERE user_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        """,
            (user_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_user_search_history_paginated(user_id: str, offset: int = 0, limit: int = 15) -> tuple[list[dict], int]:
    """Получить историю поиска с пагинацией."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM search_history WHERE user_id = ?", (user_id,))
        total = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT * FROM search_history
            WHERE user_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ? OFFSET ?
        """,
            (user_id, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()], total


def clear_search_history(user_id: str) -> int:
    """Очистить историю поиска пользователя. Возвращает количество удалённых записей."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM search_history WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount


def clear_download_history(user_id: str) -> int:
    """Очистить историю скачиваний пользователя. Возвращает количество удалённых записей."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM downloads WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount


def get_last_search(user_id: str) -> dict | None:
    """Получить последний поисковый запрос пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT command, query FROM search_history
            WHERE user_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
        """,
            (user_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# ────────────────────── Избранное ──────────────────────


def add_to_favorites(user_id: str, book_id: str, title: str, author: str, tags: str = None, notes: str = None):
    """Добавить книгу в избранное."""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO favorites (user_id, book_id, title, author, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (user_id, book_id, title, author, tags, notes),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_from_favorites(user_id: str, book_id: str):
    """Удалить книгу из избранного."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE user_id = ? AND book_id = ?", (user_id, book_id))
        conn.commit()
        return cursor.rowcount > 0


def get_user_favorites(user_id: str, offset: int = 0, limit: int = 10, tag: str = None) -> tuple[list[dict], int]:
    """Получить избранное пользователя с пагинацией и фильтром по тегу."""
    with get_db() as conn:
        cursor = conn.cursor()

        if tag:
            cursor.execute(
                "SELECT COUNT(*) as total FROM favorites WHERE user_id = ? AND tags = ?",
                (user_id, tag),
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) as total FROM favorites WHERE user_id = ?",
                (user_id,),
            )
        total = cursor.fetchone()["total"]

        if tag:
            cursor.execute(
                """
                SELECT * FROM favorites
                WHERE user_id = ? AND tags = ?
                ORDER BY added_date DESC
                LIMIT ? OFFSET ?
            """,
                (user_id, tag, limit, offset),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM favorites
                WHERE user_id = ?
                ORDER BY added_date DESC
                LIMIT ? OFFSET ?
            """,
                (user_id, limit, offset),
            )

        favorites = [dict(row) for row in cursor.fetchall()]
        return favorites, total


def is_favorite(user_id: str, book_id: str) -> bool:
    """Проверить, есть ли книга в избранном."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM favorites WHERE user_id = ? AND book_id = ?", (user_id, book_id))
        return cursor.fetchone() is not None


def are_favorites(user_id: str, book_ids: list[str]) -> set[str]:
    """Batch-проверка: какие из book_ids есть в избранном пользователя."""
    if not book_ids:
        return set()
    with get_db() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(book_ids))
        cursor.execute(
            f"SELECT book_id FROM favorites WHERE user_id = ? AND book_id IN ({placeholders})",
            [user_id, *book_ids],
        )
        return {row["book_id"] for row in cursor.fetchall()}


def update_favorite_tags(user_id: str, book_id: str, tags: str):
    """Обновить теги (полку) книги в избранном."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE favorites SET tags = ?
            WHERE user_id = ? AND book_id = ?
        """,
            (tags, user_id, book_id),
        )
        conn.commit()


def update_favorite_notes(user_id: str, book_id: str, notes: str):
    """Обновить заметки к книге в избранном."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE favorites SET notes = ?
            WHERE user_id = ? AND book_id = ?
        """,
            (notes, user_id, book_id),
        )
        conn.commit()


def search_favorites(user_id: str, query: str) -> list[dict]:
    """Поиск по избранному (по названию или автору)."""
    with get_db() as conn:
        cursor = conn.cursor()
        like_query = f"%{query}%"
        cursor.execute(
            """
            SELECT * FROM favorites
            WHERE user_id = ? AND (title LIKE ? OR author LIKE ?)
            ORDER BY added_date DESC
            LIMIT 50
        """,
            (user_id, like_query, like_query),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_favorites_count_by_tag(user_id: str) -> dict[str, int]:
    """Получить количество избранных по каждому тегу."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(tags, '') as tag, COUNT(*) as cnt
            FROM favorites
            WHERE user_id = ?
            GROUP BY tags
        """,
            (user_id,),
        )
        return {row["tag"]: row["cnt"] for row in cursor.fetchall()}


def get_all_favorites_for_export(user_id: str) -> list[dict]:
    """Получить все избранные книги для экспорта."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT book_id, title, author, tags, notes, added_date
            FROM favorites
            WHERE user_id = ?
            ORDER BY added_date DESC
        """,
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# ────────────────────── Скачивания ──────────────────────


def add_download(user_id: str, book_id: str, title: str, author: str, book_format: str):
    """Добавить запись о скачивании и обновить счётчик в одной транзакции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO downloads (user_id, book_id, title, author, format)
            VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, book_id, title, author, book_format),
        )
        cursor.execute(
            """
            UPDATE users SET download_count = download_count + 1, last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """,
            (user_id,),
        )
        conn.commit()


def get_user_downloads(user_id: str, limit: int = 10) -> list[dict]:
    """Получить историю скачиваний пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM downloads
            WHERE user_id = ?
            ORDER BY download_date DESC
            LIMIT ?
        """,
            (user_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


# ────────────────────── Кэш книг ──────────────────────


def cache_book(book):
    """Закэшировать информацию о книге (используя Book.to_dict)."""
    with get_db() as conn:
        cursor = conn.cursor()
        d = book.to_dict()

        cursor.execute(
            """
            INSERT OR REPLACE INTO books_cache
            (book_id, title, author, link, formats, cover, size, series, year,
             annotation, genres, rating, author_link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                d["book_id"],
                d["title"],
                d["author"],
                d["link"],
                d["formats"],
                d["cover"],
                d["size"],
                d["series"],
                d["year"],
                d["annotation"],
                d["genres"],
                d["rating"],
                d["author_link"],
            ),
        )
        conn.commit()


def get_cached_book(book_id: str) -> dict | None:
    """Получить книгу из кэша."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books_cache WHERE book_id = ?", (book_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                """
                UPDATE books_cache
                SET access_count = access_count + 1
                WHERE book_id = ?
            """,
                (book_id,),
            )
            conn.commit()
            return dict(row)
        return None


# ────────────────────── Статистика ──────────────────────


def get_global_stats() -> dict:
    """Получить глобальную статистику."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total_users FROM users")
        total_users = cursor.fetchone()["total_users"]

        cursor.execute("""
            SELECT COUNT(*) as active_users FROM users
            WHERE last_seen > datetime('now', '-7 days')
        """)
        active_users = cursor.fetchone()["active_users"]

        cursor.execute("SELECT COUNT(*) as total_searches FROM search_history")
        total_searches = cursor.fetchone()["total_searches"]

        cursor.execute("SELECT COUNT(*) as total_downloads FROM downloads")
        total_downloads = cursor.fetchone()["total_downloads"]

        cursor.execute("SELECT COUNT(*) as total_favorites FROM favorites")
        total_favorites = cursor.fetchone()["total_favorites"]

        cursor.execute("""
            SELECT command, COUNT(*) as count
            FROM search_history
            GROUP BY command
            ORDER BY count DESC
            LIMIT 5
        """)
        top_commands = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT book_id, title, author, COUNT(*) as count
            FROM downloads
            GROUP BY book_id
            ORDER BY count DESC
            LIMIT 10
        """)
        top_books = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT author, COUNT(*) as count
            FROM downloads
            GROUP BY author
            ORDER BY count DESC
            LIMIT 10
        """)
        top_authors = [dict(row) for row in cursor.fetchall()]

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_searches": total_searches,
            "total_downloads": total_downloads,
            "total_favorites": total_favorites,
            "top_commands": top_commands,
            "top_books": top_books,
            "top_authors": top_authors,
        }


def get_user_stats(user_id: str) -> dict:
    """Получить статистику пользователя (все запросы в одном соединении)."""
    with get_db() as conn:
        cursor = conn.cursor()

        # User info
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            return {}
        user = dict(user_row)

        # Favorites count
        cursor.execute("SELECT COUNT(*) as favorites_count FROM favorites WHERE user_id = ?", (user_id,))
        favorites_count = cursor.fetchone()["favorites_count"]

        # Recent searches
        cursor.execute(
            """
            SELECT * FROM search_history
            WHERE user_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 5
        """,
            (user_id,),
        )
        recent_searches = [dict(row) for row in cursor.fetchall()]

        # Recent downloads
        cursor.execute(
            """
            SELECT * FROM downloads
            WHERE user_id = ?
            ORDER BY download_date DESC
            LIMIT 5
        """,
            (user_id,),
        )
        recent_downloads = [dict(row) for row in cursor.fetchall()]

        # Favorite authors
        cursor.execute(
            """
            SELECT author, COUNT(*) as count
            FROM downloads
            WHERE user_id = ?
            GROUP BY author
            ORDER BY count DESC
            LIMIT 5
        """,
            (user_id,),
        )
        favorite_authors = [dict(row) for row in cursor.fetchall()]

        return {
            "user_info": user,
            "favorites_count": favorites_count,
            "recent_searches": recent_searches,
            "recent_downloads": recent_downloads,
            "favorite_authors": favorite_authors,
        }


# ────────────────────── Очистка ──────────────────────


def cleanup_old_data(days: int = 30, max_cache_size: int = 10000):
    """Очистить старые данные и ограничить размер кэша книг."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM search_history
            WHERE timestamp < datetime('now', '-' || CAST(? AS TEXT) || ' days')
        """,
            (str(days),),
        )

        cursor.execute(
            """
            DELETE FROM books_cache
            WHERE cached_date < datetime('now', '-' || CAST(? AS TEXT) || ' days')
            AND access_count < 2
        """,
            (str(days),),
        )

        # Enforce max cache size — keep most accessed entries
        cursor.execute("SELECT COUNT(*) as cnt FROM books_cache")
        cache_count = cursor.fetchone()["cnt"]
        if cache_count > max_cache_size:
            cursor.execute(
                """
                DELETE FROM books_cache WHERE book_id IN (
                    SELECT book_id FROM books_cache
                    ORDER BY access_count ASC, cached_date ASC
                    LIMIT ?
                )
            """,
                (cache_count - max_cache_size,),
            )

        conn.commit()


def rt_reset_stuck_downloads():
    """Reset tasks stuck in 'downloading' status back to 'pending' (call on startup)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE rt_download_queue SET status = 'pending' WHERE status = 'downloading'"
        )
        count = cursor.rowcount
        conn.commit()
        return count


# ────────────────────── Кэш аудиокниг (legacy, для старых данных) ──────────────────────


def init_audiobook_tables():
    """Создать таблицы для аудиокниг."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audiobooks_cache (
                book_id        TEXT PRIMARY KEY,
                slug           TEXT UNIQUE,
                title          TEXT,
                author         TEXT,
                narrator       TEXT,
                cover_url      TEXT,
                chapters_json  TEXT DEFAULT '[]',
                total_chapters INTEGER DEFAULT 0,
                cached_date    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audiobook_progress (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT NOT NULL REFERENCES users(user_id),
                book_id         TEXT NOT NULL,
                book_title      TEXT,
                book_author     TEXT,
                current_chapter INTEGER DEFAULT 0,
                total_chapters  INTEGER DEFAULT 0,
                updated_date    DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, book_id)
            )
        """)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audiobook_progress_user ON audiobook_progress(user_id)"
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rt_download_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                chat_id     INTEGER NOT NULL,
                topic_id    TEXT NOT NULL,
                title       TEXT NOT NULL,
                file_index  INTEGER,
                filename    TEXT,
                file_size   INTEGER DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  REAL NOT NULL
            )
        """)

        # Миграция старой схемы очереди RuTracker
        for col, col_type in [
            ("file_index", "INTEGER"),
            ("filename", "TEXT"),
            ("file_size", "INTEGER DEFAULT 0"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE rt_download_queue ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass

        conn.commit()


def init_reading_progress_tables():
    """Таблица прогресса чтения/прослушивания (в т.ч. аудио RuTracker)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reading_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'audio',
                flibusta_book_id TEXT,
                rutracker_topic_id TEXT NOT NULL,
                title TEXT NOT NULL,
                author TEXT,
                current_chapter INTEGER NOT NULL DEFAULT 0,
                total_chapters INTEGER NOT NULL DEFAULT 0,
                file_indices_json TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL
            )
        """)
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_progress_user_topic "
            "ON reading_progress(user_id, rutracker_topic_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reading_progress_user_updated "
            "ON reading_progress(user_id, updated_at DESC)"
        )
        conn.commit()


def reading_progress_upsert_audio(
    user_id: int,
    rutracker_topic_id: str,
    title: str,
    author: str,
    flibusta_book_id: str | None,
    file_indices: list[int],
    current_chapter: int,
) -> None:
    """Сохранить прогресс по аудиорелизу RuTracker (одна строка на пользователя и топик)."""
    now = time.time()
    total = len(file_indices)
    payload = json.dumps(file_indices, ensure_ascii=False)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO reading_progress
                (user_id, kind, flibusta_book_id, rutracker_topic_id, title, author,
                 current_chapter, total_chapters, file_indices_json, updated_at)
            VALUES (?, 'audio', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, rutracker_topic_id) DO UPDATE SET
                title=excluded.title,
                author=excluded.author,
                current_chapter=excluded.current_chapter,
                total_chapters=excluded.total_chapters,
                file_indices_json=excluded.file_indices_json,
                updated_at=excluded.updated_at,
                flibusta_book_id=COALESCE(excluded.flibusta_book_id, reading_progress.flibusta_book_id)
            """,
            (
                str(user_id),
                flibusta_book_id,
                rutracker_topic_id,
                title,
                author or "",
                current_chapter,
                total,
                payload,
                now,
            ),
        )
        conn.commit()


def reading_progress_list(user_id: int, limit: int = 30) -> list[dict]:
    """Список активных книг/релизов пользователя (новые сверху)."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM reading_progress
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (str(user_id), limit),
        ).fetchall()
        return [dict(r) for r in rows]


def reading_progress_by_topic(user_id: int, topic_id: str) -> dict | None:
    """Одна запись по RuTracker topic_id."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM reading_progress
            WHERE user_id = ? AND rutracker_topic_id = ?
            """,
            (str(user_id), topic_id),
        ).fetchone()
        return dict(row) if row else None


def reading_progress_by_id(user_id: int, row_id: int) -> dict | None:
    """Запись по id (проверка user_id)."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM reading_progress
            WHERE user_id = ? AND id = ?
            """,
            (str(user_id), row_id),
        ).fetchone()
        return dict(row) if row else None


def reading_progress_update_chapter(user_id: int, topic_id: str, chapter_index: int) -> None:
    """Обновить текущую главу/файл."""
    now = time.time()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE reading_progress
            SET current_chapter = ?, updated_at = ?
            WHERE user_id = ? AND rutracker_topic_id = ?
            """,
            (chapter_index, now, str(user_id), topic_id),
        )
        conn.commit()


def reading_progress_delete(user_id: int, row_id: int) -> bool:
    """Удалить запись прогресса."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM reading_progress WHERE user_id = ? AND id = ?",
            (str(user_id), row_id),
        )
        conn.commit()
        return cur.rowcount > 0


def save_audiobook_cache(
    book_id: str, slug: str, title: str, author: str,
    narrator: str, cover_url: str, chapters: list, total_chapters: int,
):
    """Сохранить или обновить кэш аудиокниги."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO audiobooks_cache
                (book_id, slug, title, author, narrator, cover_url,
                 chapters_json, total_chapters, cached_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(book_id) DO UPDATE SET
                slug=excluded.slug, title=excluded.title,
                author=excluded.author, narrator=excluded.narrator,
                cover_url=excluded.cover_url, chapters_json=excluded.chapters_json,
                total_chapters=excluded.total_chapters, cached_date=CURRENT_TIMESTAMP
            """,
            (book_id, slug, title, author, narrator, cover_url,
             json.dumps(chapters, ensure_ascii=False), total_chapters),
        )
        conn.commit()


def get_audiobook_cache(book_id: str) -> dict | None:
    """Получить кэшированные данные аудиокниги по book_id."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM audiobooks_cache WHERE book_id = ?", (book_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["chapters"] = json.loads(result.get("chapters_json") or "[]")
        return result


def get_audiobook_cache_by_slug(slug: str) -> dict | None:
    """Получить кэшированные данные аудиокниги по slug."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM audiobooks_cache WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["chapters"] = json.loads(result.get("chapters_json") or "[]")
        return result


def upsert_audiobook_progress(
    user_id: str, book_id: str, book_title: str,
    book_author: str, current_chapter: int, total_chapters: int,
):
    """Создать или обновить прогресс прослушивания."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO audiobook_progress
                (user_id, book_id, book_title, book_author,
                 current_chapter, total_chapters, updated_date)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                current_chapter=excluded.current_chapter,
                total_chapters=excluded.total_chapters,
                updated_date=CURRENT_TIMESTAMP
            """,
            (user_id, book_id, book_title, book_author, current_chapter, total_chapters),
        )
        conn.commit()


def get_user_listening_progress(user_id: str) -> dict | None:
    """Получить последний прогресс прослушивания пользователя."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM audiobook_progress
            WHERE user_id = ?
            ORDER BY updated_date DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_audiobook_progress(user_id: str, book_id: str) -> dict | None:
    """Получить прогресс прослушивания конкретной книги."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM audiobook_progress WHERE user_id = ? AND book_id = ?",
            (user_id, book_id),
        ).fetchone()
        return dict(row) if row else None


def get_all_user_audiobook_progress(user_id: str, limit: int = 10) -> list[dict]:
    """Получить все аудиокниги пользователя с прогрессом."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM audiobook_progress
            WHERE user_id = ?
            ORDER BY updated_date DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_reading_books(user_id: str) -> list[dict]:
    """Получить книги с полки 'Читаю' из избранного."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT book_id, title, author, added_date
            FROM favorites
            WHERE user_id = ? AND tags = 'reading'
            ORDER BY added_date DESC
            LIMIT 10
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────
# RuTracker download queue
# ──────────────────────────────────────────────────────────

def rt_enqueue(
    user_id: int,
    chat_id: int,
    topic_id: str,
    title: str,
    file_index: int | None = None,
    filename: str = "",
    file_size: int = 0,
) -> int:
    """Insert a pending download task.  Returns the new row id."""
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO rt_download_queue
               (user_id, chat_id, topic_id, title, file_index, filename, file_size, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (str(user_id), chat_id, topic_id, title, file_index, filename, file_size, time.time()),
        )
        conn.commit()
        return cur.lastrowid


def rt_update_status(task_id: int, status: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE rt_download_queue SET status = ? WHERE id = ?",
            (status, task_id),
        )
        conn.commit()


def rt_get_task(task_id: int) -> dict | None:
    """Return one RuTracker queue row by id."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM rt_download_queue WHERE id = ?",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None


def rt_delete_task(task_id: int) -> bool:
    """Delete a queue row. Returns True if a row was removed."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM rt_download_queue WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0


def rt_all_topic_ids() -> list[str]:
    """Distinct topic_id values currently in the queue (for disk cleanup)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT topic_id FROM rt_download_queue",
        ).fetchall()
        return [str(r["topic_id"]) for r in rows]


def rt_delete_all_rows() -> int:
    """Remove all RuTracker queue rows. Returns number of deleted rows."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM rt_download_queue")
        conn.commit()
        return cur.rowcount


def rt_pending_for_user(user_id: int) -> list[dict]:
    """Return tasks that are still pending/downloading for a user."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM rt_download_queue
               WHERE user_id = ? AND status IN ('pending', 'downloading')
               ORDER BY created_at""",
            (str(user_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def rt_recent_tasks(limit: int = 20) -> list[dict]:
    """Return recent RuTracker queue tasks for admin monitoring."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, chat_id, topic_id, title, file_index, filename, file_size, status, created_at
            FROM rt_download_queue
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
