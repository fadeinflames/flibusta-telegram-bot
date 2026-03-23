"""Shared state, decorators and utilities used across all tg_bot_* modules."""

import asyncio
import os
import time
from functools import wraps

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import CallbackContext

from src import config, flib
from src import database as db
from src.custom_logging import get_logger
from src.tg_bot_cache import TTLCache

logger = get_logger(__name__)

# ────────────────────── Caches & state ──────────────────────

_SEARCH_CACHE = TTLCache(
    ttl_sec=config.SEARCH_CACHE_TTL_SEC,
    max_size=config.SEARCH_CACHE_MAX_SIZE,
)

_allowed_users_raw = os.getenv("ALLOWED_USERS", "").split(",")
_allowed_users_list = [uid.strip() for uid in _allowed_users_raw if uid.strip()]

ALLOWED_USERS: set[str] = set(_allowed_users_list)
ADMIN_USER_ID: str | None = _allowed_users_list[0] if _allowed_users_list else None

FAVORITES_PER_PAGE = config.FAVORITES_PER_PAGE_DEFAULT


# ────────────────────── Cache wrappers ──────────────────────


def cache_get(key: str):
    return _SEARCH_CACHE.get(key)


def cache_set(key: str, value):
    _SEARCH_CACHE.set(key, value)


# ────────────────────── Async bridge ──────────────────────


async def db_call(func, *args, **kwargs):
    """Run sync DB function in thread pool."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def flib_call(func, *args, **kwargs):
    """Run sync scraper/network function in thread pool."""
    return await asyncio.to_thread(func, *args, **kwargs)


# ────────────────────── Message helpers ──────────────────────


def inc_error_stat(context: CallbackContext, error: Exception):
    stats = context.bot_data.setdefault("error_stats", {})
    name = type(error).__name__
    stats[name] = stats.get(name, 0) + 1


async def safe_edit_or_send(query, context: CallbackContext, text: str, reply_markup, parse_mode=ParseMode.HTML):
    """Edit message text; if it fails (previous was a photo), delete and send new."""
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except (BadRequest, Forbidden):
        try:
            await query.delete_message()
        except (BadRequest, Forbidden):
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


async def send_or_edit_message(update: Update, context: CallbackContext, text: str, reply_markup):
    """Send new message or edit existing (auto-detect by callback_query presence)."""
    if len(text) > 4096:
        text = text[:4092] + "…"
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        except (BadRequest, Forbidden):
            try:
                await update.callback_query.delete_message()
            except (BadRequest, Forbidden):
                pass
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )


# ────────────────────── Book cache ──────────────────────


async def book_from_cache(book_id: str):
    """Restore a Book from DB cache, or fetch from Flibusta."""
    cached = await db_call(db.get_cached_book, book_id)
    if cached:
        return flib.Book.from_dict(cached)
    book = await flib_call(flib.get_book_by_id, book_id)
    if book:
        await db_call(db.cache_book, book)
    return book


# ────────────────────── Search helpers ──────────────────────


def save_search_results(context: CallbackContext, books: list, search_type: str, query: str):
    """Save search results to user_data (deduplicated pattern)."""
    context.user_data["search_results"] = books
    context.user_data["search_results_original"] = list(books)
    context.user_data["search_type"] = search_type
    context.user_data["search_query"] = query
    context.user_data["current_results_page"] = 1


MAX_SPLIT_VARIANTS = 2


async def try_split_search(query: str):
    """Try splitting query into title + author and search.

    Returns (books, title_part, author_part) or (None, None, None).
    Limited to MAX_SPLIT_VARIANTS to avoid excessive HTTP requests.
    """
    words = query.split()
    if len(words) < 2:
        return None, None, None

    max_variants = min(MAX_SPLIT_VARIANTS, len(words) - 1)

    # Try exact search splits
    for author_words in range(1, max_variants + 1):
        title_part = " ".join(words[:-author_words])
        author_part = " ".join(words[-author_words:])
        if not title_part or not author_part:
            continue

        cache_key = f"exact:{title_part}|{author_part}"
        books = cache_get(cache_key)
        if books is None:
            books = await flib_call(flib.scrape_books_mbl, title_part, author_part)
            cache_set(cache_key, books)

        if books:
            return books, title_part, author_part

    # Try author search splits
    for author_words in range(1, max_variants + 1):
        title_part = " ".join(words[:-author_words])
        author_part = " ".join(words[-author_words:])
        if not title_part or not author_part:
            continue

        cache_key = f"author:{author_part}"
        authors_books = cache_get(cache_key)
        if authors_books is None:
            authors_books = await flib_call(flib.scrape_books_by_author, author_part)
            cache_set(cache_key, authors_books)

        if not authors_books:
            continue

        all_books = []
        for group in authors_books:
            all_books.extend(group)

        title_part_lower = title_part.lower()
        matched = [b for b in all_books if title_part_lower in b.title.lower()]
        if matched:
            return matched, title_part, author_part

    return None, None, None


async def perform_title_search(query: str, user_id: str):
    """Title search with split-search fallback.

    Returns (books, search_type_label, history_command, history_query).
    """
    cache_key = f"title:{query}"
    books = cache_get(cache_key)
    if books is None:
        books = await flib_call(flib.scrape_books_by_title, query)
        cache_set(cache_key, books)

    if not books and len(query.split()) >= 2:
        logger.info("Title search returned nothing, trying split fallback", extra={"query": query, "user_id": user_id})
        split_books, split_title, split_author = await try_split_search(query)
        if split_books:
            return (
                split_books,
                f"«{split_title}» + «{split_author}»",
                "exact",
                f"{split_title} | {split_author}",
            )

    return books, "названию", "title", query


# ────────────────────── Access decorators ──────────────────────


def check_access(func):
    """Decorator: verify user access for command handlers."""

    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)

        await db_call(
            db.add_or_update_user,
            user_id=user_id,
            username=update.effective_user.username,
            full_name=update.effective_user.full_name,
            is_admin=(ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID),
        )

        if not ALLOWED_USERS:
            return await func(update, context)

        if user_id not in ALLOWED_USERS:
            logger.warning(
                msg="Unauthorized access attempt",
                extra={
                    "user_id": user_id,
                    "user_name": update.effective_user.name,
                    "user_full_name": update.effective_user.full_name,
                },
            )
            await update.message.reply_text(
                "⛔ У вас нет доступа к этому боту.\nОбратитесь к администратору для получения доступа."
            )
            return

        return await func(update, context)

    return wrapper


def rate_limit(min_interval_sec: float = 1.0):
    """Simple per-user rate-limiter."""

    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
            last_key = f"last_request_{func.__name__}"
            last_time = context.user_data.get(last_key, 0)
            now = time.time()
            if now - last_time < min_interval_sec:
                await update.message.reply_text("⏳ Слишком часто. Подождите пару секунд.")
                return
            context.user_data[last_key] = now
            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator


def check_callback_access(func):
    """Decorator: verify user access for callback query handlers."""

    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)

        await db_call(
            db.add_or_update_user,
            user_id=user_id,
            username=update.effective_user.username,
            full_name=update.effective_user.full_name,
        )

        if not ALLOWED_USERS:
            return await func(update, context)

        if user_id not in ALLOWED_USERS:
            logger.warning(
                msg="Unauthorized callback access attempt",
                extra={
                    "user_id": user_id,
                    "user_name": update.effective_user.name,
                    "user_full_name": update.effective_user.full_name,
                },
            )
            query = update.callback_query
            await query.answer("У вас нет доступа к этому боту", show_alert=True)
            return

        return await func(update, context)

    return wrapper


# ────────────────────── Error handling ──────────────────────


async def handle_error(error, update: Update, context: CallbackContext, mes):
    """Handle search/command errors: delete loading message, notify user, log."""
    try:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
    except (BadRequest, Forbidden):
        pass

    try:
        await update.message.reply_text(
            "❌ Произошла ошибка при выполнении запроса.\nПопробуйте позже или используйте другую команду."
        )
    except (BadRequest, Forbidden):
        pass

    inc_error_stat(context, error)
    logger.error(
        "Error occurred",
        exc_info=error,
        extra={
            "user_id": str(update.effective_user.id) if update.effective_user else None,
            "error_type": type(error).__name__,
            "error_message": str(error),
        },
    )
