"""Display / screen-rendering functions."""

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
    send_or_edit_message,
)
from src.tg_bot_nav import reset_nav as _reset_nav
from src.tg_bot_presentation import (
    escape_md,
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

    query_text = f"«{escape_md(search_query)}»" if search_query else "—"
    page_info = f"  •  стр. {page}/{total_pages}" if total_pages > 1 else ""
    header_text = f"🔍 Результаты по {search_type}: {query_text}\nНайдено: {total_books}{page_info}\n"

    # Batch-check favorites (N+1 → 1 query)
    book_ids = [book.id for book in page_books]
    fav_set = await db_call(db.are_favorites, user_id, book_ids)

    body_lines = []
    for i, book in enumerate(page_books, start=start_idx + 1):
        star = " ⭐" if book.id in fav_set else ""
        title = truncate(escape_md(book.title), 60)
        author = escape_md(book.author) if book.author else "—"

        meta_parts = []
        if book.year:
            meta_parts.append(book.year)
        fmts = _format_book_formats(book)
        if fmts:
            meta_parts.append(fmts)
        meta_str = f"  ({', '.join(meta_parts)})" if meta_parts else ""

        body_lines.append(f"*{i}.* {title}{star}")
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

    # Compact action buttons: rows of [number + title] [⬇️]
    for i, book in enumerate(page_books, start=start_idx + 1):
        btn_title = truncate(book.title, 30)
        kb.append(
            [
                InlineKeyboardButton(f"{i}. {btn_title}", callback_data=f"book_{book.id}"),
                InlineKeyboardButton("📥", callback_data=f"qd_{book.id}"),
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
            kb.append(quick_nav)

    kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])

    reply_markup = InlineKeyboardMarkup(kb)

    if mes:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )
    else:
        query = update.callback_query
        try:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
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
                parse_mode=ParseMode.MARKDOWN,
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
    if book.size:
        detail_bits.append(f"📊 {book.size}")
    if book.formats:
        detail_bits.append(f"📁 {len(book.formats)} форматов")

    compact_info = "  •  ".join(detail_bits)
    capt = f"📖 *{escape_md(book.title)}*\n✍️ _{escape_md(book.author)}_\n"
    if compact_info:
        capt += f"{compact_info}\n"
    capt += f"\n🔗 [Страница на сайте]({book.link})"

    annotation_short = ""
    has_full_annotation = False
    if book.annotation:
        if len(book.annotation) > 250:
            annotation_short = escape_md(book.annotation[:247]) + "…"
            has_full_annotation = True
        else:
            annotation_short = escape_md(book.annotation)

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

    kb.append([InlineKeyboardButton("ℹ️ Подробнее о книге", callback_data=f"book_meta_{book_id}")])

    if has_full_annotation:
        kb.append([InlineKeyboardButton("📝 Полная аннотация", callback_data=f"full_ann_{book_id}")])

    if book.author_link:
        kb.append(
            [
                InlineKeyboardButton(
                    f"👤 Другие книги: {truncate(escape_md(book.author), 25)}",
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
        full_text += f"\n\n📝 _{annotation_short}_"

    if book.cover:
        try:
            await flib_call(flib.download_book_cover, book)
            c_full_path = os.path.join(config.BOOKS_DIR, book_id, "cover.jpg")
            if not os.path.exists(c_full_path):
                raise FileNotFoundError("Cover not found")

            photo_caption = capt
            if annotation_short and len(photo_caption) + len(annotation_short) + 10 < 1024:
                photo_caption += f"\n\n📝 _{annotation_short}_"

            if len(photo_caption) > 1024:
                photo_caption = photo_caption[:1020] + "…"

            with open(c_full_path, "rb") as cover:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=cover,
                    caption=photo_caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN,
                )
                if update.callback_query:
                    try:
                        await update.callback_query.delete_message()
                    except (BadRequest, Forbidden):
                        pass
        except (OSError, BadRequest, Forbidden):
            await send_or_edit_message(update, context, full_text, reply_markup)
    else:
        await send_or_edit_message(update, context, full_text, reply_markup)


async def show_book_meta(book_id: str, update: Update, context: CallbackContext):
    """Show extended metadata for a book."""
    book = await book_from_cache(book_id)
    if not book:
        await update.callback_query.answer("Книга не найдена", show_alert=True)
        return

    lines = [
        f"📖 *{escape_md(book.title)}*",
        f"✍️ _{escape_md(book.author)}_",
    ]
    if book.genres:
        lines.append(f"📂 Жанры: {escape_md(', '.join(book.genres[:8]))}")
    if book.series:
        lines.append(f"📚 Серия: {escape_md(book.series)}")
    if book.year:
        lines.append(f"📅 Год: {book.year}")
    if book.size:
        lines.append(f"📊 Размер: {book.size}")
    if book.rating:
        lines.append(f"⭐ Рейтинг: {book.rating}")
    lines.append(f"🔗 [Страница на сайте]({book.link})")

    text = screen(
        "ℹ️ *Подробности книги*",
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

    greeting = (
        f"👋 *Привет, {escape_md(user_name)}!*\n\n📚 *Добро пожаловать в библиотеку Flibusta!*"
        if is_start
        else "📋 *Справка по командам бота*"
    )

    help_text = f"""{greeting}

━━━━━━━━━━━━━━━━━━━━━
*📊 ВАША СТАТИСТИКА*  {level}
━━━━━━━━━━━━━━━━━━━━━
📖 Поисков: {sc}
📥 Скачиваний: {dc}
⭐ В избранном: {fc}

━━━━━━━━━━━━━━━━━━━━━
*🔍 КОМАНДЫ ПОИСКА*
━━━━━━━━━━━━━━━━━━━━━

📖 /title `название` - поиск по названию
👤 /author `фамилия` - поиск по автору
🎯 /exact `название | автор` - точный поиск
🆔 /id `номер` - получить книгу по ID
🔍 /search - универсальный поиск

━━━━━━━━━━━━━━━━━━━━━
*⭐ ЛИЧНЫЙ КАБИНЕТ*
━━━━━━━━━━━━━━━━━━━━━

⭐ /favorites - мои избранные книги
📜 /history - история поиска
📥 /downloads - история скачиваний
⚙️ /settings - настройки
📊 /mystats - моя статистика

_Выберите команду для начала работы!_
    """

    reply_markup = InlineKeyboardMarkup(_main_menu_keyboard(last))
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def show_main_menu(update: Update, context: CallbackContext):
    """Main menu (callback version — edits message)."""
    user_name = update.effective_user.first_name or "Книголюб"
    user_id = str(update.effective_user.id)
    _reset_nav(context)

    sc, dc, fc, level, last = await _build_main_menu_data(user_id, user_name)

    text = screen(
        "🏠 *Главное меню*",
        (
            f"Привет, {escape_md(user_name)}!  {level}\n\n"
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


async def show_search_menu(update: Update, context: CallbackContext):
    """Search-method chooser screen."""
    text = screen(
        "🔍 *Меню поиска*",
        (
            "Выберите способ поиска:\n\n"
            "📖 По названию — найти книги по названию\n"
            "👤 По автору — все книги автора\n"
            "🎯 Точный поиск — название + автор\n"
            "🆔 По ID — если знаете номер книги\n\n"
            "Используйте команды:\n"
            "• `/title название`\n"
            "• `/author фамилия`\n"
            "• `/exact название | автор`\n"
            "• `/id номер`\n\n"
            "💡 Или просто отправьте название книги текстом!"
        ),
        breadcrumbs("🏠 Меню", "🔍 Поиск"),
    )

    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ]
    ]
    await safe_edit_or_send(update.callback_query, context, text, InlineKeyboardMarkup(keyboard))


# ════════════════════════════════════════════════════════════
#                      UNIFIED SCREENS (command + callback)
# ════════════════════════════════════════════════════════════


async def show_user_history(update: Update, context: CallbackContext, *, from_command: bool = False):
    """Search history screen (works as both command response and callback edit)."""
    user_id = str(update.effective_user.id)
    history = await db_call(db.get_user_search_history, user_id, limit=15)

    if not history:
        text = screen(
            "📜 *История поиска*",
            "История пуста\n\nНачните поиск с команд:\n• /title\n• /author\n• /exact",
            breadcrumbs("🏠 Меню", "📜 История"),
        )
    else:
        text = screen("📜 *История поиска (последние 15)*", "", breadcrumbs("🏠 Меню", "📜 История")) + "\n\n"
        for item in history:
            timestamp = item["timestamp"][:16]
            command = item["command"]
            q = truncate(item["query"], 30)
            results = item["results_count"]
            text += f"🕐 {timestamp}\n"
            text += f"   `/{command}`: «{escape_md(q)}» ({results} рез.)\n\n"

    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_downloads(update: Update, context: CallbackContext, *, from_command: bool = False):
    """Downloads history screen."""
    user_id = str(update.effective_user.id)
    downloads = await db_call(db.get_user_downloads, user_id, limit=15)

    if not downloads:
        text = screen("📥 *История скачиваний*", "Пока пусто", breadcrumbs("🏠 Меню", "📥 Скачивания"))
    else:
        text = screen("📥 *История скачиваний (последние 15)*", "", breadcrumbs("🏠 Меню", "📥 Скачивания")) + "\n\n"
        for item in downloads:
            timestamp = item["download_date"][:16]
            title = truncate(item["title"], 30)
            author = truncate(item["author"], 20)
            format_type = item["format"]
            text += f"🕐 {timestamp}\n"
            text += f"   📖 {escape_md(title)}\n"
            text += f"   ✍️ {escape_md(author)}\n"
            text += f"   📁 Формат: {format_type}\n\n"

    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
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
        "📊 *Ваша статистика*",
        (
            f"🏆 Уровень: *{level}*\n"
            f"_{nxt}_\n\n"
            f"👤 ID: `{user_id}`\n"
            f"📅 Регистрация: {user_info.get('first_seen', 'Неизвестно')[:10]}\n"
            f"📅 Активность: {user_info.get('last_seen', 'Неизвестно')[:16]}\n\n"
            f"📈 *Активность:*\n"
            f"• Поисков: {search_count}\n"
            f"• Скачиваний: {download_count}\n"
            f"• В избранном: {favorites_count}\n\n"
            "👤 *Любимые авторы:*\n"
        ),
        breadcrumbs("🏠 Меню", "📊 Статистика"),
    )

    if favorite_authors:
        for i, author in enumerate(favorite_authors[:5], 1):
            text += f"{i}. {escape_md(author['author'])} ({author['count']} книг)\n"
    else:
        text += "Пока нет данных\n"

    if recent_downloads:
        text += "\n📚 *Последние скачивания:*\n"
        for dl in recent_downloads[:3]:
            title = truncate(dl["title"], 25)
            text += f"• {escape_md(title)}\n"

    text += "\n🏆 *Уровни:*\n"
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
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_settings(update: Update, context: CallbackContext, *, from_command: bool = False):
    """User settings screen."""
    user_id = str(update.effective_user.id)
    books_per_page = await db_call(db.get_user_preference, user_id, "books_per_page", config.BOOKS_PER_PAGE_DEFAULT)
    default_format = await db_call(db.get_user_preference, user_id, "default_format", "fb2")

    text = screen(
        "⚙️ *Настройки*",
        (
            f"📄 Книг на странице: `{books_per_page}`\n"
            f"📁 Формат по умолчанию: `{default_format}`\n\n"
            "_Настройки сохраняются автоматически_"
        ),
        breadcrumbs("🏠 Меню", "⚙️ Настройки"),
    )

    keyboard = [
        [
            InlineKeyboardButton("📄 5", callback_data="set_per_page_5"),
            InlineKeyboardButton("📄 10", callback_data="set_per_page_10"),
            InlineKeyboardButton("📄 20", callback_data="set_per_page_20"),
        ],
        [
            InlineKeyboardButton("FB2", callback_data="set_format_fb2"),
            InlineKeyboardButton("EPUB", callback_data="set_format_epub"),
            InlineKeyboardButton("MOBI", callback_data="set_format_mobi"),
            InlineKeyboardButton("PDF", callback_data="set_format_pdf"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_command:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)
