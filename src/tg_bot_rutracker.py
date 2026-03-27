"""Telegram handlers for RuTracker audiobook search and download."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from src import database as db
from src import rutracker
from src.config import RUTRACKER_USERNAME
from src.rutracker_downloader import downloader
from src.tg_bot_helpers import check_access, db_call
from src.tg_bot_presentation import escape_html

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

_PAGE_SIZE = 5
_FILES_PER_PAGE = 10
_RT_RESULTS_KEY = "rt_search_results"
_RT_FILES_KEY = "rt_topic_files"
_TG_AUDIO_LIMIT = 49 * 1024 * 1024
_TG_MSG_MAX = 4096


def _fmt_size(raw: str) -> str:
    """Keep the human-readable size string as-is."""
    return raw


def _fmt_bytes(size: int) -> str:
    if size <= 0:
        return "?"
    units = ["B", "KB", "MB", "GB"]
    val = float(size)
    for unit in units:
        if val < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(val)} {unit}"
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{size} B"


_RE_LEADING_NUM = re.compile(r"^0*(\d+)(?:\s*[\.\)\]\-_]\s*(.+))?$", re.UNICODE)


def _human_audio_chapter_label(filename: str) -> str:
    """Понятная подпись вместо сырых 001.mp3 / 002_foo.m4b — главы и разделы."""
    base = Path((filename or "").rsplit("/", 1)[-1]).stem.strip()
    if not base:
        return filename.rsplit("/", 1)[-1] or "?"

    gl = re.search(r"(?i)глава\s*[:#]?\s*(\d+)(?:\s*[.\-—]\s*(.+))?", base)
    if gl:
        n, tail = int(gl.group(1)), (gl.group(2) or "").strip()
        return f"Глава {n} — {tail}" if tail else f"Глава {n}"

    ch = re.search(r"(?i)часть\s*[:#]?\s*(\d+)(?:\s*[.\-—]\s*(.+))?", base)
    if ch:
        n, tail = int(ch.group(1)), (ch.group(2) or "").strip()
        return f"Часть {n} — {tail}" if tail else f"Часть {n}"

    tr = re.search(r"(?i)track\s*0*(\d+)", base)
    if tr:
        return f"Трек {int(tr.group(1))}"

    cd = re.search(r"(?i)(?:cd|диск)\s*0*(\d+)", base)
    if cd:
        return f"Диск {int(cd.group(1))}"

    m = _RE_LEADING_NUM.match(base)
    if m:
        n = int(m.group(1))
        rest = (m.group(2) or "").strip(" -._—")
        if rest:
            return f"Глава {n} — {rest}"
        return f"Глава {n}"

    return base


def _rt_chunk_lines_and_buttons(
    chunk: list[rutracker.FileEntry],
    start_idx: int,
) -> tuple[list[str], list[list[InlineKeyboardButton]]]:
    """Текст и кнопки для страницы списка файлов (человекочитаемые подписи)."""
    lines: list[str] = []
    rows: list[list[InlineKeyboardButton]] = []
    for i, entry in enumerate(chunk, start=start_idx + 1):
        size_str = _fmt_bytes(entry.size_bytes)
        warn = " ⚠️ >49MB" if entry.size_bytes > _TG_AUDIO_LIMIT else ""
        short_name = entry.filename.rsplit("/", 1)[-1]
        human = _human_audio_chapter_label(short_name)
        lines.append(f"{i}. {escape_html(human)} — {size_str}{warn}")
        btn = human if len(human) <= 38 else human[:35] + "…"
        rows.append(
            [InlineKeyboardButton(f"{i}. {btn[:40]}", callback_data=f"rt_pick_{entry.index_in_torrent}")]
        )
    return lines, rows


def _results_text(results: list[rutracker.RTopic], query: str, page: int) -> str:
    total = len(results)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    start = (page - 1) * _PAGE_SIZE
    chunk = results[start : start + _PAGE_SIZE]

    lines = [f"<b>🎧 RuTracker</b> — «{query}» ({total} результ., по убыв. пиров)\n"]
    for i, t in enumerate(chunk, start + 1):
        swarm = t.seeds + t.leeches
        seeds_icon = "🟢" if swarm >= 10 else ("🟡" if swarm >= 3 else "🔴")
        lines.append(
            f"{i}. {t.title[:80]}\n"
            f"   {seeds_icon} {t.seeds} сид • {t.leeches} лич • {_fmt_size(t.size)}"
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

    if not RUTRACKER_USERNAME:
        await query.answer("RuTracker не настроен в .env", show_alert=True)
        return

    book_id = data[len("rt_auto_"):]
    logger.info("rt auto: user=%s book_id=%s", update.effective_user.id, book_id)
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
    logger.info("rt auto: query=%r results=%s", search_query, len(results))
    await msg.delete()

    if not results:
        await context.bot.send_message(
            update.effective_chat.id,
            f"😔 На RuTracker ничего не нашлось по запросу «{search_query}».\n"
            "Попробуйте другой запрос или <code>/audiobook …</code> вручную.",
            parse_mode=ParseMode.HTML,
        )
        return

    context.user_data[_RT_RESULTS_KEY] = {"results": results, "query": search_query}
    await _show_rt_results(results, search_query, 1, update, context, edit=False)


async def handle_rt_dl(
    data: str, query, update: Update, context: CallbackContext
) -> None:
    """User clicked a search result — show chapter/file picker."""
    topic_id = data[len("rt_dl_"):]
    logger.info("rt dl: user=%s topic=%s", update.effective_user.id, topic_id)
    await query.answer("Читаю список файлов…")

    # Find title from cached results
    cached = context.user_data.get(_RT_RESULTS_KEY, {})
    results: list[rutracker.RTopic] = cached.get("results", [])
    title = next((t.title for t in results if t.topic_id == topic_id), f"Топик {topic_id}")

    files, info = await _gather_topic_files_and_info(topic_id)
    logger.info("rt dl: topic=%s files=%s", topic_id, len(files))
    if not files:
        await query.edit_message_text(
            "⚠️ Не удалось получить список аудиофайлов в торренте.\n"
            "Попробуйте другой релиз.",
        )
        return

    page_title = info.title if info else title
    context.user_data[_RT_FILES_KEY] = {
        "topic_id": topic_id,
        "title": page_title,
        "files": files,
        "description": (info.description if info else "") or "",
        "forum_name": (info.forum_name if info else "") or "",
        "topic_url": (info.topic_url if info else "") or f"https://rutracker.org/forum/viewtopic.php?t={topic_id}",
    }
    await _show_rt_topic_files(update, context, page=0, edit=True)


async def handle_rt_pick(
    data: str, query, update: Update, context: CallbackContext
) -> None:
    """Enqueue download for selected file index."""
    try:
        file_index = int(data[len("rt_pick_"):])
    except ValueError:
        await query.answer("Ошибка выбора файла", show_alert=True)
        return

    await query.answer("Добавляю в очередь…")
    cached = context.user_data.get(_RT_FILES_KEY, {})
    topic_id = cached.get("topic_id")
    title = cached.get("title", "RuTracker")
    files: list[rutracker.FileEntry] = cached.get("files", [])
    if not topic_id or not files:
        await query.edit_message_text("Результаты устарели. Откройте список заново.")
        return

    selected = next((f for f in files if f.index_in_torrent == file_index), None)
    if not selected:
        await query.edit_message_text("Файл не найден. Откройте список заново.")
        return

    logger.info(
        "rt pick: user=%s topic=%s file_index=%s filename=%s size=%s",
        update.effective_user.id,
        topic_id,
        file_index,
        selected.filename,
        selected.size_bytes,
    )
    rt_topic = next(
        (
            t
            for t in context.user_data.get(_RT_RESULTS_KEY, {}).get("results", [])
            if t.topic_id == topic_id
        ),
        None,
    )
    task_id = downloader.enqueue(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        topic_id=topic_id,
        title=title,
        file_index=file_index,
        filename=selected.filename,
        file_size=selected.size_bytes,
        seeders=rt_topic.seeds if rt_topic else 0,
        leeches=rt_topic.leeches if rt_topic else 0,
        topic_size=rt_topic.size if rt_topic else "",
    )
    await query.edit_message_text(
        f"⏳ <b>Добавлено в очередь</b>\n\n"
        f"Релиз: «{title}»\n"
        f"Файл: <code>{selected.filename.rsplit('/', 1)[-1]}</code>\n"
        f"Размер: {_fmt_bytes(selected.size_bytes)}\n"
        f"Задача: #{task_id}\n\n"
        "Пришлю аудио, когда загрузится.",
        parse_mode=ParseMode.HTML,
    )


async def handle_rt_files_page(
    data: str, query, update: Update, context: CallbackContext
) -> None:
    """Paginate selected topic files."""
    await query.answer()
    try:
        page = int(data[len("rt_files_page_"):])
    except ValueError:
        return
    await _show_rt_topic_files(update, context, page=page, edit=True)


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


async def _show_rt_topic_files(update: Update, context: CallbackContext, page: int, edit: bool = False) -> None:
    cached = context.user_data.get(_RT_FILES_KEY, {})
    topic_id = cached.get("topic_id")
    title = cached.get("title", "RuTracker")
    files: list[rutracker.FileEntry] = cached.get("files", [])
    description = (cached.get("description") or "").strip()
    forum_name = (cached.get("forum_name") or "").strip()
    topic_url = (cached.get("topic_url") or "").strip()
    if not topic_id or not files:
        if update.callback_query:
            await update.callback_query.edit_message_text("Результаты устарели. Откройте список заново.")
        return

    total = len(files)
    total_pages = max(1, (total + _FILES_PER_PAGE - 1) // _FILES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * _FILES_PER_PAGE
    chunk = files[start : start + _FILES_PER_PAGE]

    lines = [
        f"🎧 <b>{escape_html(title)}</b>",
    ]
    if forum_name:
        lines.append(f"📂 <i>{escape_html(forum_name)}</i>")
    if topic_url:
        lines.append(f'🔗 <a href="{escape_html(topic_url)}">Открыть раздачу на RuTracker</a>')
    lines.append("")
    if page == 0 and description:
        # Подробное описание — только на первой странице (урезаем при нехватке места)
        desc_html = escape_html(description)
        lines.append("📝 <b>Описание раздачи</b>")
        lines.append(f"<i>{desc_html}</i>")
        lines.append("")
    elif page > 0 and description:
        lines.append("<i>… описание раздачи — на первой странице …</i>")
        lines.append("")

    lines.extend(
        [
            f"Выберите главу или раздел для скачивания ({total}):",
            f"Страница {page + 1}/{total_pages}",
            "",
        ]
    )
    chunk_lines, chunk_rows = _rt_chunk_lines_and_buttons(chunk, start)
    lines.extend(chunk_lines)
    rows = chunk_rows

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀", callback_data=f"rt_files_page_{page - 1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="rt_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶", callback_data=f"rt_files_page_{page + 1}"))
    if nav:
        rows.append(nav)

    text = "\n".join(lines)
    if len(text) > _TG_MSG_MAX:
        # Сжимаем описание, чтобы влезли кнопки
        overhead = len(text) - _TG_MSG_MAX + 500
        if page == 0 and description and overhead > 0:
            desc_short = escape_html(description[: max(0, len(description) - overhead - 50)]) + "…"
            lines = [
                f"🎧 <b>{escape_html(title)}</b>",
            ]
            if forum_name:
                lines.append(f"📂 <i>{escape_html(forum_name)}</i>")
            if topic_url:
                lines.append(f'🔗 <a href="{escape_html(topic_url)}">Открыть раздачу на RuTracker</a>')
            lines.extend(["", "📝 <b>Описание раздачи</b>", f"<i>{desc_short}</i>", ""])
            lines.extend(
                [
                    f"Выберите главу или раздел для скачивания ({total}):",
                    f"Страница {page + 1}/{total_pages}",
                    "",
                ]
            )
            chunk_lines2, _ = _rt_chunk_lines_and_buttons(chunk, start)
            lines.extend(chunk_lines2)
            text = "\n".join(lines)
        if len(text) > _TG_MSG_MAX:
            text = text[: _TG_MSG_MAX - 4] + "…"

    if topic_url:
        rows.append([InlineKeyboardButton("🌐 Раздача на RuTracker", url=topic_url)])

    kb = InlineKeyboardMarkup(rows)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        msg = update.message or (update.callback_query and update.callback_query.message)
        if msg:
            await msg.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ── internal ──────────────────────────────────────────────────────────────────


async def _gather_topic_files_and_info(
    topic_id: str,
) -> tuple[list[rutracker.FileEntry], rutracker.RTopicFiles | None]:
    """Параллельно: список аудио из .torrent и страница топика с описанием."""
    loop = asyncio.get_event_loop()
    files_t, info_t = await asyncio.gather(
        loop.run_in_executor(None, rutracker.get_topic_files, topic_id),
        loop.run_in_executor(None, rutracker.get_topic_info, topic_id),
        return_exceptions=True,
    )
    files: list[rutracker.FileEntry] = []
    if isinstance(files_t, Exception):
        logger.exception("RuTracker file list error: topic=%s", topic_id)
    else:
        files = files_t
    info: rutracker.RTopicFiles | None = None
    if isinstance(info_t, Exception):
        logger.warning("RuTracker topic info error: topic=%s err=%s", topic_id, info_t)
    else:
        info = info_t
    return files, info


async def _do_search(query: str, context: CallbackContext) -> list[rutracker.RTopic]:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, rutracker.search, query)
    except Exception as exc:
        logger.exception("RuTracker search error: query=%r", query)
        return []


async def _do_topic_files(topic_id: str, context: CallbackContext) -> list[rutracker.FileEntry]:
    import asyncio

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, rutracker.get_topic_files, topic_id)
    except Exception as exc:
        logger.exception("RuTracker file list error: topic=%s", topic_id)
        return []


# ── /audiobook, /listening (команды) ───────────────────────────────────────────


@check_access
async def audiobook_search_command(update: Update, context: CallbackContext) -> None:
    """Поиск аудиокниг на RuTracker."""
    if not RUTRACKER_USERNAME:
        await update.message.reply_text(
            "⚠️ RuTracker не настроен: задайте <code>RUTRACKER_USERNAME</code> и "
            "<code>RUTRACKER_PASSWORD</code> в .env",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text(
            "🎧 <b>Поиск аудиокниг на RuTracker</b>\n\n"
            "Использование: <code>/audiobook Название или автор</code>\n\n"
            "Пример: <code>/audiobook Достоевский</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user_id = update.effective_user.id
    logger.info("audiobook (RuTracker) search user=%s query=%r", user_id, query)

    msg = await update.message.reply_text("⏳ Ищу на RuTracker…")
    results = await _do_search(query, context)
    try:
        await msg.delete()
    except Exception:
        pass

    if not results:
        await update.message.reply_text(
            f"😔 На RuTracker ничего не найдено по запросу «{escape_html(query)}».\n"
            "Попробуйте другие слова.",
            parse_mode=ParseMode.HTML,
        )
        return

    context.user_data[_RT_RESULTS_KEY] = {"results": results, "query": query}
    await _show_rt_results(results, query, 1, update, context, edit=False)


@check_access
async def listening_command(update: Update, context: CallbackContext) -> None:
    """Активные загрузки аудио с RuTracker."""
    user_id = update.effective_user.id
    rows = await db_call(db.rt_pending_for_user, user_id)
    if not rows:
        extra = ""
        if not RUTRACKER_USERNAME:
            extra = "\n\n⚠️ RuTracker не настроен в .env."
        await update.message.reply_text(
            "🎧 <b>Нет активных загрузок</b>\n\n"
            "Добавьте аудиокнигу с карточки книги или командой "
            "<code>/audiobook запрос</code>."
            + extra,
            parse_mode=ParseMode.HTML,
        )
        return

    lines = ["🎧 <b>Ваша очередь RuTracker</b>\n"]
    for r in rows:
        title = escape_html((r.get("title") or "")[:120])
        st = escape_html(str(r.get("status") or ""))
        fn = escape_html((r.get("filename") or "")[:60])
        lines.append(f"• #{r.get('id')} — <i>{st}</i>\n  {title}")
        if fn:
            lines.append(f"  <code>{fn}</code>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
