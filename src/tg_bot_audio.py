"""Telegram handlers for audiobook search and playback (akniga.org + Bookmate)."""

import io
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from src import akniga
from src import bookmate
from src import database as db
from src.custom_logging import get_logger
from src.tg_bot_helpers import db_call, flib_call

logger = get_logger(__name__)

_CHAPTERS_PER_PAGE = 10


# ────────────────────── Helpers ──────────────────────


def _escape(text: str) -> str:
    """Minimal HTML escaping for Telegram."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chapter_nav_keyboard(book_id: str, chapter_idx: int, total: int) -> InlineKeyboardMarkup:
    """Navigation row: [◀ Prev] [N / M] [▶ Next]."""
    prev_btn = (
        InlineKeyboardButton("◀ Пред", callback_data=f"ab_ch_{book_id}|{chapter_idx - 1}")
        if chapter_idx > 0
        else InlineKeyboardButton("·", callback_data="ab_noop")
    )
    counter_btn = InlineKeyboardButton(
        f"Глава {chapter_idx + 1} / {total}",
        callback_data="ab_noop",
    )
    next_btn = (
        InlineKeyboardButton("▶ След", callback_data=f"ab_ch_{book_id}|{chapter_idx + 1}")
        if chapter_idx < total - 1
        else InlineKeyboardButton("·", callback_data="ab_noop")
    )
    return InlineKeyboardMarkup([[prev_btn, counter_btn, next_btn]])


# ────────────────────── Search command ──────────────────────


async def audiobook_search_command(update: Update, context: CallbackContext) -> None:
    """/audiobook <query> — search audiobooks on akniga.org."""
    user_id = str(update.effective_user.id)
    query = " ".join(context.args).strip() if context.args else ""

    if not query:
        await update.message.reply_text(
            "🎧 <b>Поиск аудиокниг</b>\n\n"
            "Использование: <code>/audiobook Название или Автор</code>\n\n"
            "Пример: <code>/audiobook Достоевский</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    logger.info("audiobook search", extra={"user_id": user_id, "query": query})

    msg = await update.message.reply_text("⏳ Ищу аудиокниги…")

    results = await flib_call(akniga.search_audiobooks, query)

    if not results:
        await msg.edit_text(
            f"😔 По запросу <b>{_escape(query)}</b> ничего не найдено.\n\n"
            "Попробуйте другой запрос.",
            parse_mode=ParseMode.HTML,
        )
        return

    context.user_data["ab_search_results"] = results
    context.user_data["ab_search_query"] = query

    await msg.delete()
    await _show_audiobook_results(results, query, page=1, update=update, context=context)


async def _show_audiobook_results(
    results: list[dict], query: str, page: int,
    update: Update, context: CallbackContext,
    edit: bool = False,
) -> None:
    """Render paginated search results as inline keyboard."""
    per_page = 5
    total_pages = max(1, (len(results) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    chunk = results[start: start + per_page]

    lines = [f"🎧 <b>Аудиокниги по запросу «{_escape(query)}»</b>",
             f"Найдено: {len(results)} | Страница {page}/{total_pages}\n"]

    # Persist book_id→slug mapping so card handler can resolve slug for API calls
    slug_map: dict = context.user_data.setdefault("ab_slug_map", {})
    for item in results:
        bid = item.get("book_id", "")
        sl = item.get("slug", "")
        if bid and sl:
            slug_map[bid] = sl

    buttons = []
    for i, item in enumerate(chunk, start=start + 1):
        title = _escape(item.get("title", "—"))
        author = _escape(item.get("author", ""))
        duration = item.get("duration", "")
        dur_str = f" · {duration}" if duration else ""
        lines.append(f"{i}. <b>{title}</b>{dur_str}\n   <i>{author}</i>")
        # Use book_id (short numeric) in callback_data — Telegram limit is 64 bytes
        ref = item.get("book_id", "") or item.get("slug", "")
        buttons.append([InlineKeyboardButton(
            f"{i}. {item.get('title', '—')[:40]}",
            callback_data=f"ab_card_{ref}",
        )])

    # Pagination row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"ab_page_{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="ab_noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"ab_page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        chat_id = update.effective_chat.id
        await context.bot.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ────────────────────── Book card ──────────────────────


async def show_audiobook_card(slug_or_id: str, update: Update, context: CallbackContext) -> None:
    """Show book card with metadata and [▶ Слушать] button."""
    query = update.callback_query
    user_id = str(update.effective_user.id)

    if query:
        await query.answer("⏳ Загружаю книгу…")

    # Check cache first
    cached = await db_call(db.get_audiobook_cache, slug_or_id)
    if not cached:
        cached = await db_call(db.get_audiobook_cache_by_slug, slug_or_id)

    if cached:
        book_id = cached["book_id"]
        slug = cached["slug"]
        title = cached["title"]
        author = cached["author"]
        narrator = cached["narrator"] or ""
        chapters = cached["chapters"]
        total = cached["total_chapters"]
    else:
        # Full load from site
        msg_sent = None
        if query:
            try:
                await query.edit_message_text("⏳ Загружаю информацию о книге…")
            except Exception:
                pass
        else:
            msg_sent = await context.bot.send_message(
                update.effective_chat.id, "⏳ Загружаю информацию о книге…"
            )

        book, _media = await flib_call(akniga.load_audiobook, slug_or_id)

        if msg_sent:
            try:
                await msg_sent.delete()
            except Exception:
                pass

        if not book:
            text = "❌ Не удалось загрузить книгу. Попробуйте позже."
            if query:
                await query.edit_message_text(text)
            else:
                await context.bot.send_message(update.effective_chat.id, text)
            return

        # Save to cache
        chapters_dicts = [
            {"index": c.index, "title": c.title, "duration_sec": c.duration_sec}
            for c in book.chapters
        ]
        await db_call(
            db.save_audiobook_cache,
            book.book_id, book.slug, book.title, book.author,
            book.narrator, book.cover_url, chapters_dicts, book.total_chapters,
        )

        book_id = book.book_id
        slug = book.slug
        title = book.title
        author = book.author
        narrator = book.narrator
        chapters = chapters_dicts
        total = book.total_chapters

    # Get user's progress for this book
    progress = await db_call(db.get_audiobook_progress, user_id, book_id)
    current_ch = progress["current_chapter"] if progress else 0

    # Build card text
    narrator_line = f"\n🎙 <b>Читает:</b> {_escape(narrator)}" if narrator else ""
    total_line = f"\n📖 <b>Глав:</b> {total}" if total else ""
    progress_line = (
        f"\n▶️ <b>Прогресс:</b> Глава {current_ch + 1} из {total}"
        if progress and total
        else ""
    )

    text = (
        f"🎧 <b>{_escape(title)}</b>\n"
        f"✍️ <b>Автор:</b> {_escape(author)}"
        f"{narrator_line}"
        f"{total_line}"
        f"{progress_line}"
    )

    # Keyboard — always use book_id to stay within Telegram's 64-byte callback_data limit
    ref = book_id
    start_ch = current_ch if progress else 0
    play_label = f"▶ Продолжить (гл. {start_ch + 1})" if progress and start_ch > 0 else "▶ Слушать с начала"

    buttons = [
        [InlineKeyboardButton(play_label, callback_data=f"ab_ch_{ref}|{start_ch}")],
    ]
    if total > 1:
        buttons.append(
            [InlineKeyboardButton("📋 Список глав", callback_data=f"ab_list_{ref}|0")]
        )
    buttons.append([InlineKeyboardButton("◀ К результатам", callback_data="ab_back_results")])

    kb = InlineKeyboardMarkup(buttons)

    if query:
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await context.bot.send_message(
                update.effective_chat.id, text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
    else:
        await context.bot.send_message(
            update.effective_chat.id, text, reply_markup=kb, parse_mode=ParseMode.HTML
        )


# ────────────────────── Chapter list ──────────────────────


async def show_chapters_list(ref: str, page: int, update: Update, context: CallbackContext) -> None:
    """Show paginated chapter list for a book."""
    query = update.callback_query

    cached = await db_call(db.get_audiobook_cache, ref)
    if not cached:
        cached = await db_call(db.get_audiobook_cache_by_slug, ref)
    if not cached:
        await query.answer("Книга не найдена в кэше", show_alert=True)
        return

    chapters = cached["chapters"]
    total = cached["total_chapters"]
    title = cached["title"]
    book_id = cached["book_id"]
    slug = cached["slug"] or book_id
    # Use book_id in all callback_data to stay within Telegram's 64-byte limit
    cb_ref = book_id

    per_page = _CHAPTERS_PER_PAGE
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = chapters[start: start + per_page]

    lines = [f"📋 <b>{_escape(title)}</b> — главы:", ""]
    buttons = []
    for ch in chunk:
        idx = ch["index"] if isinstance(ch, dict) else ch.index
        ch_title = ch["title"] if isinstance(ch, dict) else ch.title
        dur = ch.get("duration_sec", 0) if isinstance(ch, dict) else ch.duration_sec
        dur_str = f" · {akniga._format_duration(dur)}" if dur else ""
        lines.append(f"{idx + 1}. {_escape(ch_title)}{dur_str}")
        buttons.append([InlineKeyboardButton(
            f"{idx + 1}. {ch_title[:45]}",
            callback_data=f"ab_ch_{cb_ref}|{idx}",
        )])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"ab_list_{cb_ref}|{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="ab_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"ab_list_{cb_ref}|{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("◀ К книге", callback_data=f"ab_card_{cb_ref}")])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)
    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await context.bot.send_message(
            update.effective_chat.id, text, reply_markup=kb, parse_mode=ParseMode.HTML
        )


# ────────────────────── Send chapter ──────────────────────


async def send_audio_chapter(
    ref: str, chapter_idx: int, update: Update, context: CallbackContext
) -> None:
    """Download and send a chapter as Telegram audio message."""
    user_id = str(update.effective_user.id)
    query = update.callback_query
    chat_id = update.effective_chat.id

    if query:
        await query.answer("⏳ Загружаю главу…")

    # Load cached metadata
    cached = await db_call(db.get_audiobook_cache, ref)
    if not cached:
        cached = await db_call(db.get_audiobook_cache_by_slug, ref)

    # Resolve slug: DB cache → user_data slug_map → ref as-is
    slug_map: dict = context.user_data.get("ab_slug_map", {})
    slug = ref
    title = ref
    author = ""
    total = 1

    if cached:
        slug = cached["slug"] or cached["book_id"]
        title = cached["title"]
        author = cached["author"]
        total = cached["total_chapters"]
        chapters = cached["chapters"]
        if 0 <= chapter_idx < len(chapters):
            ch = chapters[chapter_idx]
            chapter_title = ch["title"] if isinstance(ch, dict) else ch.title
        else:
            chapter_title = f"Глава {chapter_idx + 1}"
    else:
        # Not cached yet — try slug_map, then ref as-is
        slug = slug_map.get(ref, ref)
        chapter_title = f"Глава {chapter_idx + 1}"

    # Status message
    status_msg = await context.bot.send_message(
        chat_id,
        f"⏳ Загружаю <b>{_escape(chapter_title)}</b>…\n"
        f"<i>Это может занять до минуты</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        mp3_bytes, fetched_title = await flib_call(akniga.fetch_chapter_audio, slug, chapter_idx)
    except Exception as e:
        logger.error("fetch_chapter_audio error", exc_info=e, extra={"slug": slug, "ch": chapter_idx})
        mp3_bytes = None
        fetched_title = chapter_title

    if fetched_title and fetched_title != f"Глава {chapter_idx + 1}":
        chapter_title = fetched_title

    try:
        await status_msg.delete()
    except Exception:
        pass

    if not mp3_bytes:
        await context.bot.send_message(
            chat_id,
            "❌ Не удалось загрузить главу. Возможно, книга требует подписки на сайте.\n"
            "Попробуйте другую главу или книгу.",
        )
        return

    # Update progress
    await db_call(
        db.upsert_audiobook_progress,
        user_id, cached["book_id"] if cached else ref,
        title, author, chapter_idx, total,
    )

    # Send audio
    caption = (
        f"🎧 <b>{_escape(title)}</b>\n"
        f"📖 {_escape(chapter_title)}"
        + (f" · Глава {chapter_idx + 1}/{total}" if total > 1 else "")
    )

    nav_kb = _chapter_nav_keyboard(cached["book_id"] if cached else ref, chapter_idx, total)

    await context.bot.send_audio(
        chat_id=chat_id,
        audio=io.BytesIO(mp3_bytes),
        filename=f"{chapter_title}.mp3",
        title=chapter_title,
        performer=author,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=nav_kb,
    )


# ────────────────────── /listening command ──────────────────────


async def listening_command(update: Update, context: CallbackContext) -> None:
    """/listening — show current audiobook progress."""
    user_id = str(update.effective_user.id)
    progress = await db_call(db.get_user_listening_progress, user_id)

    if not progress:
        await update.message.reply_text(
            "🔇 Вы ещё ничего не слушали.\n\n"
            "Начните с команды <code>/audiobook Название</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    book_title = _escape(progress.get("book_title") or "Неизвестная книга")
    book_author = _escape(progress.get("book_author") or "")
    current = progress.get("current_chapter", 0)
    total = progress.get("total_chapters", 0)
    book_id = progress.get("book_id", "")

    cached = await db_call(db.get_audiobook_cache, book_id)
    ref = book_id  # always use book_id in callback_data (64-byte limit)

    ch_name = ""
    if cached and cached.get("chapters"):
        chapters = cached["chapters"]
        if 0 <= current < len(chapters):
            ch = chapters[current]
            ch_name = ch["title"] if isinstance(ch, dict) else ch.title

    progress_bar = ""
    if total > 0:
        filled = int((current / total) * 10)
        progress_bar = f"\n{'█' * filled}{'░' * (10 - filled)} {current + 1}/{total}"

    text = (
        f"🎧 <b>Сейчас слушаете:</b>\n\n"
        f"📚 <b>{book_title}</b>\n"
        + (f"✍️ {book_author}\n" if book_author else "")
        + (f"▶️ {_escape(ch_name)}\n" if ch_name else "")
        + f"📖 Глава {current + 1}"
        + (f" из {total}" if total else "")
        + progress_bar
    )

    buttons = []
    if current > 0:
        buttons.append(InlineKeyboardButton("◀ Пред", callback_data=f"ab_ch_{ref}|{current - 1}"))
    buttons.append(InlineKeyboardButton("▶ Продолжить", callback_data=f"ab_ch_{ref}|{current}"))
    if total and current < total - 1:
        buttons.append(InlineKeyboardButton("▶▶ След", callback_data=f"ab_ch_{ref}|{current + 1}"))

    kb = InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton("📋 Список глав", callback_data=f"ab_list_{ref}|0")],
        [InlineKeyboardButton("📖 Карточка книги", callback_data=f"ab_card_{ref}")],
    ])

    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ────────────────────── Callback handlers (called from tg_bot.py) ──────────────────────


async def handle_ab_card(data: str, query, update: Update, context: CallbackContext) -> None:
    book_id = data[len("ab_card_"):]
    # Resolve to slug if available (needed for first-time load from akniga.org)
    slug_map: dict = context.user_data.get("ab_slug_map", {})
    slug_or_id = slug_map.get(book_id, book_id)
    await show_audiobook_card(slug_or_id, update, context)


async def handle_ab_ch(data: str, query, update: Update, context: CallbackContext) -> None:
    payload = data[len("ab_ch_"):]
    if "|" not in payload:
        await query.answer("Ошибка формата", show_alert=True)
        return
    ref, idx_str = payload.rsplit("|", 1)
    try:
        chapter_idx = int(idx_str)
    except ValueError:
        await query.answer("Ошибка номера главы", show_alert=True)
        return
    await send_audio_chapter(ref, chapter_idx, update, context)


async def handle_ab_list(data: str, query, update: Update, context: CallbackContext) -> None:
    payload = data[len("ab_list_"):]
    if "|" in payload:
        ref, page_str = payload.rsplit("|", 1)
        try:
            page = int(page_str)
        except ValueError:
            page = 0
    else:
        ref = payload
        page = 0
    await show_chapters_list(ref, page, update, context)


async def handle_ab_page(data: str, query, update: Update, context: CallbackContext) -> None:
    try:
        page = int(data[len("ab_page_"):])
    except ValueError:
        await query.answer()
        return
    results = context.user_data.get("ab_search_results", [])
    query_text = context.user_data.get("ab_search_query", "")
    if not results:
        await query.answer("Результаты устарели. Повторите поиск.", show_alert=True)
        return
    await _show_audiobook_results(results, query_text, page, update, context, edit=True)


async def handle_ab_auto(data: str, query, update: Update, context: CallbackContext) -> None:
    """Search akniga.org by title+author from a Flibusta book card."""
    from src.tg_bot_helpers import book_from_cache

    book_id = data[len("ab_auto_"):]
    await query.answer("🔍 Ищу аудиокнигу…")

    book = await book_from_cache(book_id)
    if not book:
        await query.answer("Книга не найдена в кэше", show_alert=True)
        return

    # Clean title — strip format markers like "(fb2)", "(pdf)" that Flibusta puts in titles
    clean_title = re.sub(r"\s*\([a-zA-Z0-9]+\)\s*", " ", book.title).strip()

    # Show searching status
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    msg = await context.bot.send_message(
        update.effective_chat.id,
        f"🔍 Ищу аудиокнигу: <b>{_escape(clean_title)}</b>…",
        parse_mode=ParseMode.HTML,
    )

    # Search by clean title only — gives the most relevant results.
    # Full-name author query (e.g. "Джон Рональд Руэл Толкин") often misses the target
    # because akniga.org stores author names differently.
    results = await flib_call(akniga.search_audiobooks, clean_title)

    await msg.delete()

    if not results:
        await context.bot.send_message(
            update.effective_chat.id,
            f"😔 Аудиокниги для <b>{_escape(clean_title)}</b> не найдены на akniga.org.\n\n"
            f"Можно поискать вручную: <code>/audiobook {_escape(clean_title)}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    context.user_data["ab_search_results"] = results
    context.user_data["ab_search_query"] = clean_title

    await _show_audiobook_results(results, clean_title, page=1, update=update, context=context)


async def handle_ab_back_results(data: str, query, update: Update, context: CallbackContext) -> None:
    results = context.user_data.get("ab_search_results", [])
    query_text = context.user_data.get("ab_search_query", "")
    if not results:
        await query.answer()
        await query.edit_message_text("Результаты поиска устарели. Используйте /audiobook для нового поиска.")
        return
    await _show_audiobook_results(results, query_text, page=1, update=update, context=context, edit=True)


# ══════════════════════════════════════════════════════════════════════════════
# Bookmate / Яндекс Книги handlers
# ══════════════════════════════════════════════════════════════════════════════

_BM_RESULTS_KEY = "bm_search_results"
_BM_QUERY_KEY = "bm_search_query"


async def _show_bm_results(
    results: list, query_text: str, page: int,
    update: Update, context: CallbackContext, edit: bool = False,
) -> None:
    per_page = 5
    total_pages = max(1, (len(results) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    chunk = results[start: start + per_page]

    lines = [
        f"🎧 <b>Яндекс Книги: «{_escape(query_text)}»</b>",
        f"Найдено: {len(results)} | Страница {page}/{total_pages}\n",
    ]
    buttons = []
    for i, book in enumerate(chunk, start=start + 1):
        authors = ", ".join(book.authors[:2])
        dur = book.duration_fmt
        lines.append(f"{i}. <b>{_escape(book.title)}</b> · {_escape(dur)}\n   <i>{_escape(authors)}</i>")
        label = f"{i}. {book.title[:40]}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"bm_card_{book.uuid}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"bm_page_{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="ab_noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"bm_page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def handle_bm_auto(data: str, query, update: Update, context: CallbackContext) -> None:
    """Search Bookmate/Яндекс by title from a Flibusta book card."""
    from src.tg_bot_helpers import book_from_cache

    book_id = data[len("bm_auto_"):]
    await query.answer("🔍 Ищу в Яндекс Книгах…")

    if not bookmate.is_configured():
        await query.answer("Яндекс Книги не настроены (нет BOOKMATE_SESSION_ID)", show_alert=True)
        return

    book = await book_from_cache(book_id)
    if not book:
        await query.answer("Книга не найдена в кэше", show_alert=True)
        return

    clean_title = re.sub(r"\s*\([a-zA-Z0-9]+\)\s*", " ", book.title).strip()

    msg = await context.bot.send_message(
        update.effective_chat.id,
        f"🔍 Ищу в Яндекс Книгах: <b>{_escape(clean_title)}</b>…",
        parse_mode=ParseMode.HTML,
    )

    results = await flib_call(bookmate.search_audiobooks, clean_title)
    await msg.delete()

    if not results:
        await context.bot.send_message(
            update.effective_chat.id,
            f"😔 Аудиокниги для <b>{_escape(clean_title)}</b> не найдены в Яндекс Книгах.",
            parse_mode=ParseMode.HTML,
        )
        return

    context.user_data[_BM_RESULTS_KEY] = results
    context.user_data[_BM_QUERY_KEY] = clean_title
    await _show_bm_results(results, clean_title, page=1, update=update, context=context)


async def handle_bm_card(data: str, query, update: Update, context: CallbackContext) -> None:
    """Show Bookmate book card with track list."""
    uuid = data[len("bm_card_"):]
    await query.answer("⏳ Загружаю…")

    tracks = await flib_call(bookmate.get_book_tracks, uuid)

    if not tracks:
        await query.answer("Не удалось загрузить треки. Попробуйте позже.", show_alert=True)
        return

    # Find book info from search results
    bm_results: list = context.user_data.get(_BM_RESULTS_KEY, [])
    bk = next((b for b in bm_results if b.uuid == uuid), None)

    title = bk.title if bk else uuid
    authors = ", ".join(bk.authors[:2]) if bk else ""
    dur_total = sum(t.duration_sec for t in tracks)
    h, m = divmod(dur_total // 60, 60)
    dur_str = f"{h} ч {m} мин" if h else f"{m} мин"

    text = (
        f"🎧 <b>{_escape(title)}</b>\n"
        f"✍️ <b>Автор:</b> {_escape(authors)}\n"
        f"⏱ <b>Длительность:</b> {dur_str}\n"
        f"📖 <b>Треков:</b> {len(tracks)}"
    )

    buttons = []
    for t in tracks[:10]:
        h2, m2 = divmod(t.duration_sec // 60, 60)
        dur2 = f"{h2}:{m2:02d}" if h2 else f"{m2} мин"
        label = f"▶ Трек {t.number} · {dur2} · {t.safe_size_bytes // 1024 // 1024}MB"
        buttons.append([InlineKeyboardButton(label, callback_data=f"bm_tr_{uuid}|{t.number}")])

    if len(tracks) > 10:
        buttons.append([InlineKeyboardButton(
            f"📋 Все треки ({len(tracks)})", callback_data=f"bm_list_{uuid}|0"
        )])
    buttons.append([InlineKeyboardButton("◀ К результатам", callback_data="bm_back")])

    kb = InlineKeyboardMarkup(buttons)
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await context.bot.send_message(
            update.effective_chat.id, text, reply_markup=kb, parse_mode=ParseMode.HTML
        )


async def handle_bm_track(data: str, query, update: Update, context: CallbackContext) -> None:
    """Download and send a Bookmate audio track."""
    payload = data[len("bm_tr_"):]
    if "|" not in payload:
        await query.answer("Ошибка формата", show_alert=True)
        return
    uuid, track_num_str = payload.rsplit("|", 1)
    try:
        track_num = int(track_num_str)
    except ValueError:
        await query.answer("Ошибка номера трека", show_alert=True)
        return

    await query.answer("⏳ Загружаю трек…")
    chat_id = update.effective_chat.id

    tracks = await flib_call(bookmate.get_book_tracks, uuid)
    if not tracks:
        await context.bot.send_message(chat_id, "❌ Не удалось получить треки.")
        return

    track = next((t for t in tracks if t.number == track_num), None)
    if not track:
        await context.bot.send_message(chat_id, f"❌ Трек {track_num} не найден.")
        return

    if not track.is_available:
        await context.bot.send_message(chat_id, "⚠️ Этот трек недоступен (требуется подписка).")
        return

    bm_results: list = context.user_data.get(_BM_RESULTS_KEY, [])
    bk = next((b for b in bm_results if b.uuid == uuid), None)
    title = bk.title if bk else uuid
    authors = ", ".join(bk.authors[:2]) if bk else ""

    size_mb = track.safe_size_bytes / 1024 / 1024
    status = await context.bot.send_message(
        chat_id,
        f"⏳ Скачиваю <b>Трек {track_num}</b> ({size_mb:.0f} МБ)…\n"
        f"<i>Может занять до минуты</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        audio_bytes = await flib_call(bookmate.download_track, track.safe_m4a_url, uuid)
    except Exception as exc:
        logger.error("bookmate download error", exc_info=exc)
        await status.delete()
        await context.bot.send_message(chat_id, "❌ Ошибка при скачивании трека. Попробуйте позже.")
        return

    await status.delete()

    h, m = divmod(track.duration_sec // 60, 60)
    dur_str = f"{h}:{m:02d}" if h else f"0:{m:02d}"
    caption = (
        f"🎧 <b>{_escape(title)}</b>\n"
        f"▶ Трек {track_num}/{len(tracks)} · {dur_str}"
    )

    # Navigation keyboard
    nav_row = []
    if track_num > 1:
        nav_row.append(InlineKeyboardButton("◀ Пред", callback_data=f"bm_tr_{uuid}|{track_num - 1}"))
    nav_row.append(InlineKeyboardButton(f"{track_num}/{len(tracks)}", callback_data="ab_noop"))
    if track_num < len(tracks):
        nav_row.append(InlineKeyboardButton("▶ След", callback_data=f"bm_tr_{uuid}|{track_num + 1}"))
    nav_kb = InlineKeyboardMarkup([nav_row, [InlineKeyboardButton("📋 Все треки", callback_data=f"bm_card_{uuid}")]])

    await context.bot.send_audio(
        chat_id=chat_id,
        audio=io.BytesIO(audio_bytes),
        filename=f"{title} - Трек {track_num}.m4a",
        title=f"Трек {track_num}",
        performer=authors,
        duration=track.duration_sec,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=nav_kb,
    )


async def handle_bm_list(data: str, query, update: Update, context: CallbackContext) -> None:
    """Show full paginated track list for a Bookmate book."""
    payload = data[len("bm_list_"):]
    if "|" in payload:
        uuid, page_str = payload.rsplit("|", 1)
        try:
            page = int(page_str)
        except ValueError:
            page = 0
    else:
        uuid = payload
        page = 0

    await query.answer()
    tracks = await flib_call(bookmate.get_book_tracks, uuid)
    if not tracks:
        await query.answer("Не удалось загрузить треки", show_alert=True)
        return

    bm_results: list = context.user_data.get(_BM_RESULTS_KEY, [])
    bk = next((b for b in bm_results if b.uuid == uuid), None)
    title = bk.title if bk else uuid

    per_page = 10
    total_pages = max(1, (len(tracks) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    chunk = tracks[page * per_page: (page + 1) * per_page]

    lines = [f"📋 <b>{_escape(title)}</b> — треки:", ""]
    buttons = []
    for t in chunk:
        h, m = divmod(t.duration_sec // 60, 60)
        dur = f"{h}:{m:02d}" if h else f"{m} мин"
        mb = t.safe_size_bytes // 1024 // 1024
        lines.append(f"{t.number}. {dur} ({mb} МБ)")
        buttons.append([InlineKeyboardButton(
            f"▶ {t.number}. {dur} · {mb}MB",
            callback_data=f"bm_tr_{uuid}|{t.number}",
        )])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"bm_list_{uuid}|{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="ab_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"bm_list_{uuid}|{page + 1}"))
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("◀ К книге", callback_data=f"bm_card_{uuid}")])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def handle_bm_page(data: str, query, update: Update, context: CallbackContext) -> None:
    try:
        page = int(data[len("bm_page_"):])
    except ValueError:
        await query.answer()
        return
    results = context.user_data.get(_BM_RESULTS_KEY, [])
    query_text = context.user_data.get(_BM_QUERY_KEY, "")
    if not results:
        await query.answer("Результаты устарели. Повторите поиск.", show_alert=True)
        return
    await _show_bm_results(results, query_text, page, update, context, edit=True)


async def handle_bm_back(data: str, query, update: Update, context: CallbackContext) -> None:
    results = context.user_data.get(_BM_RESULTS_KEY, [])
    query_text = context.user_data.get(_BM_QUERY_KEY, "")
    if not results:
        await query.answer()
        await query.edit_message_text("Результаты поиска устарели.")
        return
    await _show_bm_results(results, query_text, page=1, update=update, context=context, edit=True)
