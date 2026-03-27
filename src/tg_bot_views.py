"""Display / screen-rendering functions (HTML mode)."""

import math
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import CallbackContext

from src import config, flib
from src import database as db
from src.tg_bot_helpers import (
    book_from_cache,
    db_call,
    flib_call,
    safe_edit_or_send,
)
from src.tg_bot_nav import reset_nav as _reset_nav
from src.tg_bot_presentation import (
    escape_html,
    get_user_level,
    next_level_info,
)
from src.tg_bot_ui import DIVIDER, breadcrumbs, screen, truncate

# ════════════════════════════════════════════════════════════
#                      BOOK LIST / DETAILS
# ════════════════════════════════════════════════════════════


def _format_book_formats(book) -> str:
    """Return a short comma-separated string of available format names."""
    if not book.formats:
        return ""
    fmts = [f.strip("() ").lower() for f in book.formats]
    return ", ".join(fmts)


async def show_books_page(books, update: Update, context: CallbackContext, mes, page: int = 1):
    """Render a page of search results with book details in text and compact action buttons."""
    user_id = str(update.effective_user.id)
    per_page = await db_call(db.get_user_preference, user_id, "books_per_page", config.BOOKS_PER_PAGE_DEFAULT)
    total_books = len(books)
    total_pages = math.ceil(total_books / per_page) if per_page else 1

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    context.user_data["current_results_page"] = page

    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_books)
    page_books = books[start_idx:end_idx]

    search_type = context.user_data.get("search_type", "поиску")
    search_query = context.user_data.get("search_query", "")

    query_text = f"«{escape_html(search_query)}»" if search_query else "—"
    page_info = f"  •  стр. {page}/{total_pages}" if total_pages > 1 else ""
    header_text = f"🔍 Результаты по {search_type}: {query_text}\nНайдено: {total_books}{page_info}\n"

    # Batch-check favorites (N+1 → 1 query)
    book_ids = [book.id for book in page_books]
    fav_set = await db_call(db.are_favorites, user_id, book_ids)

    # Default format for quick-download button label
    default_fmt = await db_call(db.get_user_preference, user_id, "default_format", "fb2")

    body_lines = []
    for i, book in enumerate(page_books, start=start_idx + 1):
        star = " ⭐" if book.id in fav_set else ""
        title = truncate(escape_html(book.title), 60)
        author = escape_html(book.author) if book.author else "—"

        meta_parts = []
        if book.year:
            meta_parts.append(book.year)
        fmts = _format_book_formats(book)
        if fmts:
            meta_parts.append(fmts)
        meta_str = f"  ({', '.join(meta_parts)})" if meta_parts else ""

        body_lines.append(f"<b>{i}.</b> {title}{star}")
        body_lines.append(f"     ✍️ {author}{meta_str}")

    text = header_text + DIVIDER + "\n" + "\n".join(body_lines)

    kb = []

    # Sort buttons — only if there's something to sort
    if total_books > 1:
        kb.append(
            [
                InlineKeyboardButton("А-Я ↕", callback_data="sort_title"),
                InlineKeyboardButton("👤 ↕", callback_data="sort_author"),
                InlineKeyboardButton("↺ Исходный", callback_data="sort_default"),
            ]
        )

    # Compact action buttons: rows of [number + title] [⬇️ format]
    for i, book in enumerate(page_books, start=start_idx + 1):
        btn_title = truncate(book.title, 30)
        kb.append(
            [
                InlineKeyboardButton(f"{i}. {btn_title}", callback_data=f"book_{book.id}"),
                InlineKeyboardButton(f"📥 {default_fmt}", callback_data=f"qd_{book.id}"),
            ]
        )

    # Page navigation
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page - 1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="current_page"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{page + 1}"))
    if nav_buttons:
        kb.append(nav_buttons)

    if total_pages > 5:
        quick_nav = []
        if page > 3:
            quick_nav.append(InlineKeyboardButton("⏮ 1", callback_data="page_1"))
        if page < total_pages - 2:
            quick_nav.append(InlineKeyboardButton(f"{total_pages} ⏭", callback_data=f"page_{total_pages}"))
        if quick_nav:
            # Add page-jump button
            quick_nav.append(InlineKeyboardButton("📄 Стр.", callback_data="page_jump"))
            kb.append(quick_nav)

    kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])

    reply_markup = InlineKeyboardMarkup(kb)

    if mes:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
    else:
        query = update.callback_query
        try:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except (BadRequest, Forbidden):
            try:
                await query.delete_message()
            except (BadRequest, Forbidden):
                pass
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )


async def show_book_details_with_favorite(book_id: str, update: Update, context: CallbackContext):
    """Show book card: annotation, genres, formats, share, author books."""
    user_id = str(update.effective_user.id)

    book = await book_from_cache(book_id)

    if not book:
        error_msg = "Книга не найдена"
        if update.callback_query:
            await update.callback_query.answer(error_msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(error_msg)
        return

    is_fav = await db_call(db.is_favorite, user_id, book_id)

    detail_bits = []
    if book.year:
        detail_bits.append(f"📅 {book.year}")
    if book.rating:
        detail_bits.append(f"⭐ {book.rating}")
    if book.size:
        detail_bits.append(f"📊 {book.size}")
    if book.formats:
        detail_bits.append(f"📁 {len(book.formats)} форматов")

    compact_info = "  •  ".join(detail_bits)
    capt = f"📖 <b>{escape_html(book.title)}</b>\n✍️ <i>{escape_html(book.author)}</i>\n"
    if compact_info:
        capt += f"{compact_info}\n"
    capt += f'\n🔗 <a href="{book.link}">Страница на сайте</a>'

    annotation_short = ""
    has_full_annotation = False
    if book.annotation:
        if len(book.annotation) > 250:
            annotation_short = escape_html(book.annotation[:247]) + "…"
            has_full_annotation = True
        else:
            annotation_short = escape_html(book.annotation)

    # ── Buttons ──
    kb = []

    fav_text = "💔 Из избранного" if is_fav else "⭐ В избранное"
    fav_row = [InlineKeyboardButton(fav_text, callback_data=f"toggle_favorite_{book_id}")]
    if is_fav:
        fav_row.append(InlineKeyboardButton("📚 Полка", callback_data=f"pick_shelf_{book_id}"))
    kb.append(fav_row)

    if book.formats:
        format_keys = list(book.formats.keys())
        context.user_data.setdefault("book_format_map", {})[book_id] = format_keys

        default_fmt = await db_call(db.get_user_preference, user_id, "default_format", "fb2")
        quick_fmt = None
        for fmt_key in format_keys:
            if default_fmt in fmt_key.lower():
                quick_fmt = fmt_key
                break
        if not quick_fmt:
            quick_fmt = next(iter(format_keys), None)
        if not quick_fmt:
            quick_fmt = default_fmt

        quick_idx = format_keys.index(quick_fmt) if quick_fmt in format_keys else 0
        quick_label = quick_fmt.strip("()") if quick_fmt else default_fmt
        kb.append(
            [
                InlineKeyboardButton(
                    f"⚡ Скачать быстро ({quick_label})",
                    callback_data=f"fmt_{book_id}_{quick_idx}",
                )
            ]
        )

    fmt_buttons = []
    for idx, b_format in enumerate(book.formats):
        short_name = b_format.strip("() ").upper()
        fmt_buttons.append(
            InlineKeyboardButton(
                f"📥 {short_name}",
                callback_data=f"fmt_{book_id}_{idx}",
            )
        )
    for i in range(0, len(fmt_buttons), 3):
        kb.append(fmt_buttons[i : i + 3])

    from src.config import RUTRACKER_USERNAME
    if RUTRACKER_USERNAME:
        kb.append(
            [InlineKeyboardButton("🎧 Аудиокнига", callback_data=f"rt_auto_{book_id}")]
        )

    kb.append([InlineKeyboardButton("ℹ️ Подробнее о книге", callback_data=f"book_meta_{book_id}")])

    if has_full_annotation:
        kb.append([InlineKeyboardButton("📝 Полная аннотация", callback_data=f"full_ann_{book_id}")])

    if book.author_link:
        kb.append(
            [
                InlineKeyboardButton(
                    f"👤 Другие книги: {truncate(book.author, 25)}",
                    callback_data=f"author_books_{book_id}",
                )
            ]
        )

    bot_username = context.bot.username or "bot"
    share_url = f"https://t.me/{bot_username}?start=book_{book_id}"
    kb.append([InlineKeyboardButton("📤 Поделиться", url=share_url)])

    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_results")])

    reply_markup = InlineKeyboardMarkup(kb)

    full_text = capt
    if annotation_short:
        full_text += f"\n\n📝 <i>{annotation_short}</i>"

    # Always delete previous message first, then send new (avoids photo→text flicker)
    if update.callback_query:
        try:
            await update.callback_query.delete_message()
        except (BadRequest, Forbidden):
            pass

    if book.cover:
        try:
            await flib_call(flib.download_book_cover, book)
            c_full_path = os.path.join(config.BOOKS_DIR, book_id, "cover.jpg")
            if not os.path.exists(c_full_path):
                raise FileNotFoundError("Cover not found")

            photo_caption = capt
            if annotation_short and len(photo_caption) + len(annotation_short) + 10 < 1024:
                photo_caption += f"\n\n📝 <i>{annotation_short}</i>"

            if len(photo_caption) > 1024:
                photo_caption = photo_caption[:1020] + "…"

            with open(c_full_path, "rb") as cover:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=cover,
                    caption=photo_caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
        except (OSError, BadRequest, Forbidden):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=full_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=full_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )


async def show_book_meta(book_id: str, update: Update, context: CallbackContext):
    """Show extended metadata for a book."""
    book = await book_from_cache(book_id)
    if not book:
        await update.callback_query.answer("Книга не найдена", show_alert=True)
        return

    lines = [
        f"📖 <b>{escape_html(book.title)}</b>",
        f"✍️ <i>{escape_html(book.author)}</i>",
    ]
    if book.genres:
        lines.append(f"📂 Жанры: {escape_html(', '.join(book.genres[:8]))}")
    if book.series:
        lines.append(f"📚 Серия: {escape_html(book.series)}")
    if book.year:
        lines.append(f"📅 Год: {book.year}")
    if book.size:
        lines.append(f"📊 Размер: {book.size}")
    if book.rating:
        lines.append(f"⭐ Рейтинг: {book.rating}")
    lines.append(f'🔗 <a href="{book.link}">Страница на сайте</a>')

    text = screen(
        "ℹ️ <b>Подробности книги</b>",
        "\n".join(lines),
        breadcrumbs("🏠 Меню", "📖 Книга", "ℹ️ Подробности"),
    )
    kb = [[InlineKeyboardButton("◀️ К карточке", callback_data=f"book_{book_id}")]]
    await safe_edit_or_send(update.callback_query, context, text, InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════
#                      MENU SCREENS
# ════════════════════════════════════════════════════════════


async def _build_main_menu_data(user_id: str, user_name: str):
    """Shared data for main-menu variants."""
    user_stats = await db_call(db.get_user_stats, user_id)
    favorites_count = user_stats.get("favorites_count", 0)
    search_count = user_stats.get("user_info", {}).get("search_count", 0)
    download_count = user_stats.get("user_info", {}).get("download_count", 0)
    level = get_user_level(search_count, download_count)
    last = await db_call(db.get_last_search, user_id)
    return search_count, download_count, favorites_count, level, last


def _main_menu_keyboard(last_search: dict | None):
    keyboard = [
        [
            InlineKeyboardButton("📖 Поиск книг", callback_data="menu_search"),
            InlineKeyboardButton("⭐ Избранное", callback_data="show_favorites_1"),
        ],
        [
            InlineKeyboardButton("📚 Я читаю / слушаю", callback_data="now_reading"),
        ],
        [
            InlineKeyboardButton("📜 История", callback_data="show_history"),
            InlineKeyboardButton("📊 Статистика", callback_data="show_my_stats"),
        ],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="show_settings")],
    ]
    if last_search:
        q_short = truncate(last_search["query"], 20)
        keyboard.append(
            [
                InlineKeyboardButton(f"🔄 Повторить: «{q_short}»", callback_data="repeat_search"),
            ]
        )
    return keyboard


async def show_main_menu_command(update: Update, context: CallbackContext, *, is_start: bool = True):
    """Main menu for /start and /help (sends new message)."""
    user_name = update.effective_user.first_name or "Книголюб"
    user_id = str(update.effective_user.id)
    sc, dc, fc, level, last = await _build_main_menu_data(user_id, user_name)

    if is_start:
        # Short greeting for /start
        help_text = (
            f"👋 <b>Привет, {escape_html(user_name)}!</b>\n\n"
            f"📚 <b>Добро пожаловать в библиотеку Flibusta!</b>\n\n"
            f"{DIVIDER}\n"
            f"<b>📊 ВАША СТАТИСТИКА</b>  {level}\n"
            f"{DIVIDER}\n"
            f"📖 Поисков: {sc}\n"
            f"📥 Скачиваний: {dc}\n"
            f"⭐ В избранном: {fc}\n\n"
            f"<i>Выберите действие кнопками ниже или отправьте название книги текстом!</i>"
        )
    else:
        # Full /help with command reference
        help_text = f"""📋 <b>Справка по командам бота</b>

{DIVIDER}
<b>📊 ВАША СТАТИСТИКА</b>  {level}
{DIVIDER}
📖 Поисков: {sc}
📥 Скачиваний: {dc}
⭐ В избранном: {fc}

{DIVIDER}
<b>🔍 КОМАНДЫ ПОИСКА</b>
{DIVIDER}

📖 /title <code>название</code> - поиск по названию
👤 /author <code>фамилия</code> - поиск по автору
🎯 /exact <code>название | автор</code> - точный поиск
🆔 /id <code>номер</code> - получить книгу по ID
🔍 /search - универсальный поиск

{DIVIDER}
<b>⭐ ЛИЧНЫЙ КАБИНЕТ</b>
{DIVIDER}

⭐ /favorites - мои избранные книги
📜 /history - история поиска
📥 /downloads - история скачиваний
⚙️ /settings - настройки
📊 /mystats - моя статистика

<i>Выберите команду для начала работы!</i>"""

    reply_markup = InlineKeyboardMarkup(_main_menu_keyboard(last))
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def show_main_menu(update: Update, context: CallbackContext):
    """Main menu (callback version — edits message)."""
    user_name = update.effective_user.first_name or "Книголюб"
    user_id = str(update.effective_user.id)
    _reset_nav(context)

    sc, dc, fc, level, last = await _build_main_menu_data(user_id, user_name)

    text = screen(
        "🏠 <b>Главное меню</b>",
        (
            f"Привет, {escape_html(user_name)}!  {level}\n\n"
            f"📊 Статистика:\n"
            f"• Поисков: {sc}\n"
            f"• Скачиваний: {dc}\n"
            f"• В избранном: {fc}\n\n"
            f"{next_level_info(sc, dc)}"
        ),
        breadcrumbs("🏠 Меню"),
    )

    reply_markup = InlineKeyboardMarkup(_main_menu_keyboard(last))
    await safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_now_reading(update: Update, context: CallbackContext, *, edit: bool = False) -> None:
    """Экран «Я читаю / слушаю»: прогресс по аудио RuTracker и очередь загрузок."""
    user_id = update.effective_user.id
    rows = await db_call(db.reading_progress_list, user_id, limit=15)
    pending = await db_call(db.rt_pending_for_user, user_id)

    body_lines: list[str] = []
    kb_rows = []

    if rows:
        body_lines.append("<b>Аудиокниги (RuTracker)</b>")
        for r in rows:
            title = escape_html((r.get("title") or "Без названия")[:100])
            cur = int(r.get("current_chapter") or 0)
            tot = int(r.get("total_chapters") or 1)
            body_lines.append(f"• {title}\n  Файл {cur + 1} из {tot}")
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        f"▶ Продолжить: {title[:36]}",
                        callback_data=f"reading_go_{r['id']}",
                    )
                ]
            )
    else:
        body_lines.append(
            "Пока нет сохранённого прогресса по аудио.\n"
            "Выберите файл в раздаче RuTracker — бот запомнит главу."
        )

    if pending:
        body_lines.append("")
        body_lines.append(f"<b>В очереди загрузок</b> ({len(pending)}):")
        for p in pending[:8]:
            st = escape_html(str(p.get("status") or ""))
            t = escape_html((p.get("title") or "")[:70])
            body_lines.append(f"• #{p.get('id')} — <i>{st}</i> — {t}")

    text = screen(
        "📚 <b>Я читаю / слушаю</b>",
        "\n\n".join(body_lines),
        breadcrumbs("🏠 Меню", "📚 Сейчас"),
    )
    kb_rows.append(
        [
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ]
    )
    reply_markup = InlineKeyboardMarkup(kb_rows)

    if edit and update.callback_query:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )


async def show_search_menu(update: Update, context: CallbackContext):
    """Search-method chooser screen with interactive buttons."""
    text = screen(
        "🔍 <b>Меню поиска</b>",
        (
            "Выберите способ поиска:\n\n"
            "📖 <b>По названию</b> — найти книги по названию\n"
            "👤 <b>По автору</b> — все книги автора\n"
            "🎯 <b>Точный поиск</b> — название + автор\n"
            "🆔 <b>По ID</b> — если знаете номер книги\n\n"
            "💡 Или просто отправьте название книги текстом!"
        ),
        breadcrumbs("🏠 Меню", "🔍 Поиск"),
    )

    keyboard = [
        [
            InlineKeyboardButton("📖 По названию", callback_data="await_title_search"),
            InlineKeyboardButton("👤 По автору", callback_data="await_author_search"),
        ],
        [
            InlineKeyboardButton("🎯 Точный поиск", callback_data="await_exact_search"),
            InlineKeyboardButton("🆔 По ID", callback_data="await_id_search"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ],
    ]
    await safe_edit_or_send(update.callback_query, context, text, InlineKeyboardMarkup(keyboard))


# ════════════════════════════════════════════════════════════
#                      UNIFIED SCREENS (command + callback)
# ════════════════════════════════════════════════════════════


HISTORY_PER_PAGE = 15


async def show_user_history(update: Update, context: CallbackContext, *, from_command: bool = False, page: int = 1):
    """Search history screen with pagination and clear button."""
    user_id = str(update.effective_user.id)
    offset = (page - 1) * HISTORY_PER_PAGE
    history, total = await db_call(db.get_user_search_history_paginated, user_id, offset, HISTORY_PER_PAGE)
    total_pages = math.ceil(total / HISTORY_PER_PAGE) if total > 0 else 1

    if not history and total == 0:
        text = screen(
            "📜 <b>История поиска</b>",
            "История пуста\n\nНачните поиск с команд:\n• /title\n• /author\n• /exact",
            breadcrumbs("🏠 Меню", "📜 История"),
        )
    else:
        page_info = f"  •  стр. {page}/{total_pages}" if total_pages > 1 else ""
        text = screen(f"📜 <b>История поиска ({total} записей{page_info})</b>", "", breadcrumbs("🏠 Меню", "📜 История")) + "\n\n"
        for item in history:
            timestamp = item["timestamp"][:16]
            command = item["command"]
            q = truncate(item["query"], 30)
            results = item["results_count"]
            text += f"🕐 {timestamp}\n"
            text += f"   <code>/{command}</code>: «{escape_html(q)}» ({results} рез.)\n\n"

    keyboard = []

    # Pagination
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"history_page_{page - 1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="current_page"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"history_page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    if total > 0:
        keyboard.append([InlineKeyboardButton("🗑 Очистить историю", callback_data="clear_search_history")])

    keyboard.append(
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_downloads(update: Update, context: CallbackContext, *, from_command: bool = False):
    """Downloads history screen."""
    user_id = str(update.effective_user.id)
    downloads = await db_call(db.get_user_downloads, user_id, limit=15)

    if not downloads:
        text = screen("📥 <b>История скачиваний</b>", "Пока пусто", breadcrumbs("🏠 Меню", "📥 Скачивания"))
    else:
        text = (
            screen("📥 <b>История скачиваний (последние 15)</b>", "", breadcrumbs("🏠 Меню", "📥 Скачивания")) + "\n\n"
        )
        for item in downloads:
            timestamp = item["download_date"][:16]
            title = truncate(item["title"], 30)
            author = truncate(item["author"], 20)
            format_type = item["format"]
            text += f"🕐 {timestamp}\n"
            text += f"   📖 {escape_html(title)}\n"
            text += f"   ✍️ {escape_html(author)}\n"
            text += f"   📁 Формат: {format_type}\n\n"

    keyboard = []
    if downloads:
        keyboard.append([InlineKeyboardButton("🗑 Очистить историю", callback_data="clear_download_history")])
    keyboard.append(
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_statistics(update: Update, context: CallbackContext, *, from_command: bool = False):
    """User statistics + achievements screen."""
    user_id = str(update.effective_user.id)
    stats = await db_call(db.get_user_stats, user_id)

    user_info = stats.get("user_info", {})
    favorites_count = stats.get("favorites_count", 0)
    favorite_authors = stats.get("favorite_authors", [])
    recent_downloads = stats.get("recent_downloads", [])
    search_count = user_info.get("search_count", 0)
    download_count = user_info.get("download_count", 0)
    level = get_user_level(search_count, download_count)
    nxt = next_level_info(search_count, download_count)

    text = screen(
        "📊 <b>Ваша статистика</b>",
        (
            f"🏆 Уровень: <b>{level}</b>\n"
            f"<i>{nxt}</i>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"📅 Регистрация: {user_info.get('first_seen', 'Неизвестно')[:10]}\n"
            f"📅 Активность: {user_info.get('last_seen', 'Неизвестно')[:16]}\n\n"
            f"📈 <b>Активность:</b>\n"
            f"• Поисков: {search_count}\n"
            f"• Скачиваний: {download_count}\n"
            f"• В избранном: {favorites_count}\n\n"
            "👤 <b>Любимые авторы:</b>\n"
        ),
        breadcrumbs("🏠 Меню", "📊 Статистика"),
    )

    if favorite_authors:
        for i, author in enumerate(favorite_authors[:5], 1):
            text += f"{i}. {escape_html(author['author'])} ({author['count']} книг)\n"
    else:
        text += "Пока нет данных\n"

    if recent_downloads:
        text += "\n📚 <b>Последние скачивания:</b>\n"
        for dl in recent_downloads[:3]:
            title = truncate(dl["title"], 25)
            text += f"• {escape_html(title)}\n"

    text += "\n🏆 <b>Уровни:</b>\n"
    for lvl in config.ACHIEVEMENT_LEVELS:
        marker = "▸" if lvl["name"] == level else "▹"
        text += f"{marker} {lvl['name']} — {lvl['searches']}+ поисков, {lvl['downloads']}+ скачиваний\n"

    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_settings(update: Update, context: CallbackContext, *, from_command: bool = False):
    """User settings screen with highlighted active values."""
    user_id = str(update.effective_user.id)
    books_per_page = await db_call(db.get_user_preference, user_id, "books_per_page", config.BOOKS_PER_PAGE_DEFAULT)
    default_format = await db_call(db.get_user_preference, user_id, "default_format", "fb2")

    text = screen(
        "⚙️ <b>Настройки</b>",
        (
            f"📄 Книг на странице: <code>{books_per_page}</code>\n"
            f"📁 Формат по умолчанию: <code>{default_format}</code>\n\n"
            "<i>Настройки сохраняются автоматически</i>"
        ),
        breadcrumbs("🏠 Меню", "⚙️ Настройки"),
    )

    # Highlight active page count
    page_buttons = []
    for count in [5, 10, 20]:
        label = f"✅ {count}" if books_per_page == count else f"📄 {count}"
        page_buttons.append(InlineKeyboardButton(label, callback_data=f"set_per_page_{count}"))

    # Highlight active format
    fmt_buttons = []
    for fmt in config.ALL_FORMATS:
        label = f"✅ {fmt.upper()}" if default_format == fmt else fmt.upper()
        fmt_buttons.append(InlineKeyboardButton(label, callback_data=f"set_format_{fmt}"))

    keyboard = [
        page_buttons,
        fmt_buttons,
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)


# ════════════════════════════════════════════════════════════
#                      NOW READING / LISTENING
# ════════════════════════════════════════════════════════════


async def show_now_reading(update: Update, context: CallbackContext, *, from_command: bool = False):
    """Screen showing books and audiobooks currently being read/listened to."""
    user_id = str(update.effective_user.id)

    reading_books = await db_call(db.get_reading_books, user_id)
    audio_progress = await db_call(db.get_all_user_audiobook_progress, user_id)

    has_content = bool(reading_books) or bool(audio_progress)

    if not has_content:
        text = screen(
            "📖 <b>Я читаю / слушаю</b>",
            (
                "Здесь пока пусто.\n\n"
                "📗 Добавляйте книги на полку «Читаю» из избранного\n"
                "🎧 Слушайте аудиокниги через /audiobook или карточку книги"
            ),
            breadcrumbs("🏠 Меню", "📖 Читаю"),
        )
        keyboard = [
            [
                InlineKeyboardButton("📖 Поиск книг", callback_data="menu_search"),
                InlineKeyboardButton("🏠 Меню", callback_data="main_menu"),
            ]
        ]
    else:
        body_parts = []
        kb = []

        if reading_books:
            body_parts.append("<b>📗 Читаю сейчас:</b>")
            for i, book in enumerate(reading_books, 1):
                title = truncate(escape_html(book["title"]), 35)
                author = truncate(escape_html(book["author"]), 20)
                body_parts.append(f"{i}. {title}\n     ✍️ {author}")
                kb.append(
                    [
                        InlineKeyboardButton(
                            f"📗 {truncate(book['title'], 30)}",
                            callback_data=f"book_{book['book_id']}",
                        ),
                    ]
                )

        if audio_progress:
            if reading_books:
                body_parts.append("")
            body_parts.append("<b>🎧 Слушаю:</b>")
            for i, ap in enumerate(audio_progress, 1):
                title = truncate(escape_html(ap["book_title"]), 35)
                author = truncate(escape_html(ap["book_author"]), 20)
                ch = ap["current_chapter"]
                total = ap["total_chapters"]
                progress_pct = round(ch / total * 100) if total > 0 else 0
                bar = _progress_bar(ch, total)
                body_parts.append(
                    f"{i}. {title}\n"
                    f"     ✍️ {author}\n"
                    f"     {bar} {ch}/{total} глав ({progress_pct}%)"
                )
                kb.append(
                    [
                        InlineKeyboardButton(
                            f"🎧 {truncate(ap['book_title'], 25)} ({ch}/{total})",
                            callback_data=f"audio_continue_{ap['book_id']}",
                        ),
                    ]
                )

        text = screen(
            "📖 <b>Я читаю / слушаю</b>",
            "\n".join(body_parts),
            breadcrumbs("🏠 Меню", "📖 Читаю"),
        )
        keyboard = kb
        keyboard.append(
            [
                InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
                InlineKeyboardButton("🏠 Меню", callback_data="main_menu"),
            ]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)


def _progress_bar(current: int, total: int, width: int = 10) -> str:
    """Build a text-based progress bar."""
    if total <= 0:
        return "░" * width
    filled = round(current / total * width)
    return "▓" * filled + "░" * (width - filled)
