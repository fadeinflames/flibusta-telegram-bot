"""In-memory + SQLite cache for RuTracker data.

Two layers:
1. In-memory dict with TTL — instant lookups, no I/O
2. SQLite table — survives restarts, shared across threads

Cache keys: "info:{topic_id}", "files:{topic_id}", "search:{query_hash}"
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any

from src import config

logger = logging.getLogger(__name__)

DB_PATH = config.DB_PATH

# TTL in seconds
TTL_TOPIC_INFO = 24 * 3600      # 24 hours — topic page rarely changes
TTL_TOPIC_FILES = 7 * 24 * 3600  # 7 days — torrent file list is immutable
TTL_SEARCH = 2 * 3600            # 2 hours — seeds/leeches change

# ── In-memory layer ──

_mem_cache: dict[str, tuple[float, Any]] = {}  # key → (expires_at, value)
_mem_lock = threading.Lock()


def _mem_get(key: str) -> Any | None:
    with _mem_lock:
        entry = _mem_cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del _mem_cache[key]
            return None
        return value


def _mem_set(key: str, value: Any, ttl: int) -> None:
    with _mem_lock:
        _mem_cache[key] = (time.time() + ttl, value)


# ── SQLite layer ──

_thread_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    conn = getattr(_thread_local, "cache_conn", None)
    if conn is not None:
        return conn
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    _thread_local.cache_conn = conn
    return conn


def init_cache_table() -> None:
    """Create the cache table if it doesn't exist."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rt_cache (
            cache_key   TEXT PRIMARY KEY,
            data_json   TEXT NOT NULL,
            expires_at  REAL NOT NULL,
            created_at  REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rt_cache_expires ON rt_cache(expires_at)")
    conn.commit()


def _db_get(key: str) -> Any | None:
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT data_json, expires_at FROM rt_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        data_json, expires_at = row
        if time.time() > expires_at:
            conn.execute("DELETE FROM rt_cache WHERE cache_key = ?", (key,))
            conn.commit()
            return None
        return json.loads(data_json)
    except Exception as e:
        logger.warning("rt_cache db_get error: %s", e)
        return None


def _db_set(key: str, value: Any, ttl: int) -> None:
    try:
        conn = _get_conn()
        now = time.time()
        conn.execute(
            """INSERT OR REPLACE INTO rt_cache (cache_key, data_json, expires_at, created_at)
               VALUES (?, ?, ?, ?)""",
            (key, json.dumps(value, ensure_ascii=False), now + ttl, now),
        )
        conn.commit()
    except Exception as e:
        logger.warning("rt_cache db_set error: %s", e)


# ── Public API ──

def get(key: str) -> Any | None:
    """Get from cache (memory first, then SQLite)."""
    val = _mem_get(key)
    if val is not None:
        return val
    val = _db_get(key)
    if val is not None:
        # Promote to memory
        _mem_set(key, val, TTL_TOPIC_INFO)
    return val


def set(key: str, value: Any, ttl: int) -> None:
    """Set in both memory and SQLite."""
    _mem_set(key, value, ttl)
    _db_set(key, value, ttl)


def search_key(query: str) -> str:
    """Generate cache key for search query."""
    h = hashlib.md5(query.strip().lower().encode()).hexdigest()[:12]
    return f"search:{h}"


def topic_info_key(topic_id: str) -> str:
    return f"info:{topic_id}"


def topic_files_key(topic_id: str) -> str:
    return f"files:{topic_id}"


def cleanup_expired() -> int:
    """Delete expired entries from SQLite + memory. Returns count deleted."""
    # Clean memory
    now = time.time()
    with _mem_lock:
        expired_keys = [k for k, (exp, _) in _mem_cache.items() if now > exp]
        for k in expired_keys:
            del _mem_cache[k]
    # Clean SQLite
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM rt_cache WHERE expires_at < ?", (now,)
        )
        conn.commit()
        return cursor.rowcount + len(expired_keys)
    except Exception:
        return len(expired_keys)


def get_stats() -> dict:
    """Return cache statistics."""
    with _mem_lock:
        mem_count = len(_mem_cache)
    try:
        conn = _get_conn()
        row = conn.execute("SELECT COUNT(*) FROM rt_cache").fetchone()
        db_count = row[0] if row else 0
    except Exception:
        db_count = 0
    return {"memory_entries": mem_count, "db_entries": db_count}


def clear_all() -> int:
    """Clear all cache entries (memory + SQLite)."""
    with _mem_lock:
        count = len(_mem_cache)
        _mem_cache.clear()
    try:
        conn = _get_conn()
        cursor = conn.execute("DELETE FROM rt_cache")
        conn.commit()
        return count + cursor.rowcount
    except Exception:
        return count
