"""Telegram handlers for RuTracker audiobook search and download."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from src import database as db
from src import rutracker
from src.rutracker_downloader import downloader

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

_PAGE_SIZE = 5
_RT_RESULTS_KEY = "rt_search_results"


def _fmt_size(raw: str) -> str:
    """Keep the human-readable size string as-is."""
    return raw


def _results_text(results: list[rutracker.RTopic], query: str, page: int) -> str:
    total = len(results)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    start = (page - 1) * _PAGE_SIZE
    chunk = results[start : start + _PAGE_SIZE]

    lines = [f"<b>🎧 RuTracker</b> — «{query}» ({total} результ.)\n"]
    for i, t in enumerate(chunk, start + 1):
        seeds_icon = "🟢" if t.seeds >= 10 else ("🟡" if t.seeds >= 3 else "🔴")
        lines.append(
            f"{i}. {t.title[:80]}\n"
            f"   {seeds_icon} {t.seeds} сид • {_fmt_size(t.size)}"
        )
    if pages > 1:
        lines.append(f"\nСтраница {page}/{pages}")
    return "\n".join(lines)


def _results_keyboard(
    results: list[rutracker.RTopic], query: str, page: int
) -> InlineKeyboardMarkup:
    total = len(results)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    start = (page - 1) * _PAGE_SIZE
    chunk = results[start : start + _PAGE_SIZE]

    rows = []
    for i, t in enumerate(chunk, start + 1):
        rows.append(
            [InlineKeyboardButton(f"{i}. {t.title[:55]}", callback_data=f"rt_dl_{t.topic_id}")]
        )

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Назад", callback_data=f"rt_page_{page - 1}"))
    if page < pages:
        nav.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"rt_page_{page + 1}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(rows)


async def _show_rt_results(
    results: list[rutracker.RTopic],
    query: str,
    page: int,
    update: Update,
    context: CallbackContext,
    edit: bool = False,
) -> None:
    text = _results_text(results, query, page)
    kb = _results_keyboard(results, query, page)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    else:
        msg = update.message or (update.callback_query and update.callback_query.message)
        if msg:
            await msg.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ── public entry points ───────────────────────────────────────────────────────

async def handle_rt_auto(
    data: str, query, update: Update, context: CallbackContext
) -> None:
    """Search RuTracker by book title (called from Flibusta book card button)."""
    import re
    from src.tg_bot_helpers import book_from_cache

    book_id = data[len("rt_auto_"):]
    await query.answer("🔍 Ищу на RuTracker…")

    book = await book_from_cache(book_id)
    if not book:
        await query.answer("Книга не найдена в кэше", show_alert=True)
        return

    clean_title = re.sub(r"\s*\([a-zA-Z0-9]+\)\s*", " ", book.title).strip()
    search_query = clean_title

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    msg = await context.bot.send_message(
        update.effective_chat.id,
        f"🔍 Ищу на RuTracker: <b>{search_query}</b>…",
        parse_mode=ParseMode.HTML,
    )

    results = await _do_search(search_query, context)
    await msg.delete()

    if not results:
        await context.bot.send_message(
            update.effective_chat.id,
            f"😔 На RuTracker ничего не нашлось по запросу «{search_query}».\n"
            "Попробуйте команду /audiobook для поиска на akniga.org.",
        )
        return

    context.user_data[_RT_RESULTS_KEY] = {"results": results, "query": search_query}
    await _show_rt_results(results, search_query, 1, update, context, edit=False)


async def handle_rt_dl(
    data: str, query, update: Update, context: CallbackContext
) -> None:
    """User clicked a search result — enqueue download."""
    topic_id = data[len("rt_dl_"):]
    await query.answer("Добавляю в очередь…")

    # Find title from cached results
    cached = context.user_data.get(_RT_RESULTS_KEY, {})
    results: list[rutracker.RTopic] = cached.get("results", [])
    title = next((t.title for t in results if t.topic_id == topic_id), f"Топик {topic_id}")

    user = update.effective_user
    chat = update.effective_chat

    # Enqueue
    downloader.enqueue(
        user_id=user.id,
        chat_id=chat.id,
        topic_id=topic_id,
        title=title,
    )

    await query.edit_message_text(
        f"⏳ <b>Добавлено в очередь</b>\n\n«{title}»\n\n"
        "Скачивание займёт некоторое время. Когда скачается — пришлю файлы сюда.",
        parse_mode=ParseMode.HTML,
    )


async def handle_rt_page(
    data: str, query, update: Update, context: CallbackContext
) -> None:
    """Paginate search results."""
    await query.answer()
    page = int(data[len("rt_page_"):])

    cached = context.user_data.get(_RT_RESULTS_KEY, {})
    results = cached.get("results", [])
    query_text = cached.get("query", "")

    if not results:
        await query.edit_message_text("Результаты устарели. Выполните новый поиск.")
        return

    await _show_rt_results(results, query_text, page, update, context, edit=True)


# ── internal ──────────────────────────────────────────────────────────────────

async def _do_search(query: str, context: CallbackContext) -> list[rutracker.RTopic]:
    import asyncio

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, rutracker.search, query)
    except Exception as exc:
        logger.error("RuTracker search error: %s", exc)
        return []
