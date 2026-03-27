"""Telegram handlers for audiobook search and playback (akniga.org)."""

import io
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from src import akniga
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

    # Search by clean title + author first, then title only as fallback
    search_query = f"{clean_title} {book.author}".strip()
    results = await flib_call(akniga.search_audiobooks, search_query)

    if not results:
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

    await _show_audiobook_results(results, book.title, page=1, update=update, context=context)


async def handle_ab_back_results(data: str, query, update: Update, context: CallbackContext) -> None:
    results = context.user_data.get("ab_search_results", [])
    query_text = context.user_data.get("ab_search_query", "")
    if not results:
        await query.answer()
        await query.edit_message_text("Результаты поиска устарели. Используйте /audiobook для нового поиска.")
        return
    await _show_audiobook_results(results, query_text, page=1, update=update, context=context, edit=True)
