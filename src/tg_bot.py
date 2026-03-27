"""Main bot module: callback router, text commands, admin, inline, jobs.

All handler functions are either defined here or re-exported from submodules
so that srv.py can import everything from ``src.tg_bot``.
"""

from urllib.parse import unquote

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import CallbackContext

from src import config, flib
from src import database as db
from src.custom_logging import get_logger
from src.tg_bot_rutracker import (
    handle_rt_auto,
    handle_rt_dl,
    handle_rt_files_page,
    handle_rt_pick,
    handle_rt_page,
)
from src.tg_bot_download import (  # noqa: F401
    get_book_by_format,
    quick_download,
)
from src.tg_bot_favorites import (
    export_favorites,
    show_favorites,
    show_other_books_by_author,
    show_tag_picker,
    toggle_favorite,
)

# ── Helpers (used here + re-exported) ──
from src.tg_bot_helpers import (  # noqa: F401 — re-exported
    ADMIN_USER_ID,
    ALLOWED_USERS,
    book_from_cache,
    cache_get,
    cache_set,
    check_access,
    check_callback_access,
    db_call,
    flib_call,
    handle_error,
    inc_error_stat,
    rate_limit,
    safe_edit_or_send,
    save_search_results,
)
from src.tg_bot_nav import pop_nav as _pop_nav
from src.tg_bot_nav import push_nav as _push_nav
from src.tg_bot_presentation import escape_html, shelf_label
from src.rutracker_downloader import downloader as rt_downloader

# ── Submodule re-exports for srv.py ──
from src.tg_bot_search import (  # noqa: F401
    find_the_book,
    search_by_author,
    search_by_id,
    search_by_title,
    search_exact,
    universal_search,
)
from src.tg_bot_views import (
    show_book_details_with_favorite,
    show_book_meta,
    show_books_page,
    show_main_menu,
    show_main_menu_command,
    show_search_menu,
    show_user_downloads,
    show_user_history,
    show_user_settings,
    show_user_statistics,
)

logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════
#                      COMMANDS
# ════════════════════════════════════════════════════════════


@check_access
async def start_callback(update: Update, context: CallbackContext):
    """Handle /start with optional deep-link (book_ID)."""
    if context.args:
        arg = context.args[0]
        if arg.startswith("book_"):
            book_id = arg[5:]
            if book_id.isdigit():
                mes = await update.message.reply_text("🔍 Загружаю книгу...")
                try:
                    book = await book_from_cache(book_id)
                    await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                    if book:
                        await show_book_details_with_favorite(book_id, update, context)
                    else:
                        await update.message.reply_text(f"😔 Книга с ID {book_id} не найдена.")
                except Exception:
                    try:
                        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                    except (BadRequest, Forbidden):
                        pass
                    await update.message.reply_text("❌ Ошибка при загрузке книги.")
                return

    await show_main_menu_command(update, context, is_start=True)


@check_access
async def help_command(update: Update, context: CallbackContext):
    """/help — full command reference."""
    await show_main_menu_command(update, context, is_start=False)


@check_access
async def favorites_command(update: Update, context: CallbackContext):
    """/favorites"""
    context.user_data["fav_tag_filter"] = None
    await show_favorites(update, context)


@check_access
async def history_command(update: Update, context: CallbackContext):
    """/history"""
    await show_user_history(update, context, from_command=True)


@check_access
async def downloads_command(update: Update, context: CallbackContext):
    """/downloads"""
    await show_user_downloads(update, context, from_command=True)


@check_access
async def mystats_command(update: Update, context: CallbackContext):
    """/mystats"""
    await show_user_statistics(update, context, from_command=True)


@check_access
async def settings_command(update: Update, context: CallbackContext):
    """/settings"""
    await show_user_settings(update, context, from_command=True)


@check_access
async def setpage_command(update: Update, context: CallbackContext):
    """/setpage — set books per page."""
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите количество книг\nПример: <code>/setpage 20</code>\nДоступно: 5, 10, 20",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        count = int(context.args[0])
        if count not in [5, 10, 20]:
            raise ValueError
        await db_call(db.set_user_preference, user_id, "books_per_page", count)
        await update.message.reply_text(f"✅ Установлено {count} книг на странице")
    except ValueError:
        await update.message.reply_text("❌ Некорректное значение. Используйте 5, 10 или 20")


@check_access
async def setformat_command(update: Update, context: CallbackContext):
    """/setformat — set default download format."""
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите формат\nПример: <code>/setformat epub</code>\nДоступно: fb2, epub, mobi, pdf, djvu",
            parse_mode=ParseMode.HTML,
        )
        return
    format_type = context.args[0].lower()
    if format_type not in config.ALL_FORMATS:
        await update.message.reply_text("❌ Некорректный формат. Используйте: fb2, epub, mobi, pdf, djvu")
        return
    await db_call(db.set_user_preference, user_id, "default_format", format_type)
    await update.message.reply_text(f"✅ Формат по умолчанию: {format_type.upper()}")


# ════════════════════════════════════════════════════════════
#                      ADMIN
# ════════════════════════════════════════════════════════════


@check_access
async def show_stats(update: Update, _: CallbackContext) -> None:
    """Global bot statistics (admin only)."""
    user_id = str(update.effective_user.id)

    if ADMIN_USER_ID and user_id == ADMIN_USER_ID:
        stats = await db_call(db.get_global_stats)

        stats_text = f"""📊 <b>Общая статистика бота</b>

👥 <b>Пользователи:</b>
• Всего: {stats["total_users"]}
• Активных (7 дней): {stats["active_users"]}

📈 <b>Активность:</b>
• Поисков: {stats["total_searches"]}
• Скачиваний: {stats["total_downloads"]}
• В избранном: {stats["total_favorites"]}

🔥 <b>Топ команд:</b>
"""
        for i, cmd in enumerate(stats["top_commands"][:5], 1):
            stats_text += f"{i}. /{cmd['command']}: {cmd['count']} раз\n"

        stats_text += "\n📚 <b>Топ книг:</b>\n"
        for i, book in enumerate(stats["top_books"][:5], 1):
            title = book["title"][:30] + "…" if len(book["title"]) > 30 else book["title"]
            stats_text += f"{i}. {escape_html(title)} ({book['count']} скач.)\n"

        stats_text += "\n✍️ <b>Топ авторов:</b>\n"
        for i, author in enumerate(stats["top_authors"][:5], 1):
            name = author["author"][:25] + "…" if len(author["author"]) > 25 else author["author"]
            stats_text += f"{i}. {escape_html(name)} ({author['count']} скач.)\n"

        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ У вас нет прав для просмотра статистики")


@check_access
async def list_allowed_users(update: Update, _: CallbackContext) -> None:
    """List allowed users (admin only)."""
    user_id = str(update.effective_user.id)

    if ADMIN_USER_ID and user_id == ADMIN_USER_ID:
        if ALLOWED_USERS:
            users_info = []
            for uid in sorted(ALLOWED_USERS):
                user_data = await db_call(db.get_user, uid)
                if user_data:
                    users_info.append(f"• {uid} — {escape_html(user_data.get('full_name', 'Неизвестно'))}")
                else:
                    users_info.append(f"• {uid} — (не в БД)")

            users_list = "\n".join(users_info)
            await update.message.reply_text(
                f"📋 <b>Список разрешенных пользователей:</b>\n\n{users_list}\n\n"
                f"<i>Всего: {len(ALLOWED_USERS)} пользователей</i>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text("⚠️ Список разрешенных пользователей пуст. Доступ открыт для всех.")
    else:
        await update.message.reply_text("❌ У вас нет прав для просмотра этой информации.")


@check_access
async def rt_admin_queue(update: Update, context: CallbackContext) -> None:
    """/rtqueue — RuTracker queue monitor (admin only)."""
    user_id = str(update.effective_user.id)
    if not (ADMIN_USER_ID and user_id == ADMIN_USER_ID):
        await update.message.reply_text("❌ У вас нет прав для просмотра этой информации.")
        return

    # Optional argument: /rtqueue 50
    limit = 20
    if context.args:
        try:
            limit = max(1, min(100, int(context.args[0])))
        except ValueError:
            limit = 20

    tasks = await db_call(db.rt_recent_tasks, limit)
    if not tasks:
        await update.message.reply_text("📭 Очередь RuTracker пока пуста.")
        return

    icon = {
        "pending": "🟡",
        "downloading": "🔵",
        "done": "✅",
        "failed": "❌",
        "cancelled": "⏹️",
    }
    lines = [f"🎧 <b>RuTracker очередь (последние {len(tasks)})</b>", ""]
    for t in tasks:
        st = t.get("status", "pending")
        st_i = icon.get(st, "⚪")
        fname = escape_html((t.get("filename") or "—")[:40])
        title = escape_html((t.get("title") or "—")[:50])
        topic_id = t.get("topic_id", "—")
        created_at = t.get("created_at", 0)
        lines.append(
            f"{st_i} <b>#{t.get('id')}</b> · {st}\n"
            f"👤 user: <code>{t.get('user_id')}</code> · topic: <code>{topic_id}</code>\n"
            f"📄 {fname}\n"
            f"📚 {title}\n"
            f"🕒 ts: <code>{created_at:.0f}</code>\n"
        )

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4092] + "…"
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🗑 Delete all", callback_data="admin_rt_del_all")]]
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@check_access
async def rt_admin_delete_all(update: Update, context: CallbackContext) -> None:
    """/rtdelall — очистить всю очередь RuTracker и файлы (admin only)."""
    user_id = str(update.effective_user.id)
    if not (ADMIN_USER_ID and user_id == ADMIN_USER_ID):
        await update.message.reply_text("❌ У вас нет прав для этой команды.")
        return
    ok, msg = rt_downloader.delete_all_tasks()
    await update.message.reply_text(f"{'✅' if ok else '❌'} {msg}")


@check_access
async def rt_admin_stop(update: Update, context: CallbackContext) -> None:
    """/rtstop <id> — отменить задачу RuTracker (admin only)."""
    user_id = str(update.effective_user.id)
    if not (ADMIN_USER_ID and user_id == ADMIN_USER_ID):
        await update.message.reply_text("❌ У вас нет прав для этой команды.")
        return
    if not context.args:
        await update.message.reply_text(
            "Использование: <code>/rtstop &lt;id&gt;</code>\n"
            "ID смотри в <code>/rtqueue</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Некорректный ID задачи.")
        return
    ok, msg = rt_downloader.cancel_task(task_id)
    await update.message.reply_text(f"{'✅' if ok else '❌'} {msg}")


@check_access
async def rt_admin_delete(update: Update, context: CallbackContext) -> None:
    """/rtdel <id> — удалить задачу из очереди и файлы на диске (admin only)."""
    user_id = str(update.effective_user.id)
    if not (ADMIN_USER_ID and user_id == ADMIN_USER_ID):
        await update.message.reply_text("❌ У вас нет прав для этой команды.")
        return
    if not context.args:
        await update.message.reply_text(
            "Использование: <code>/rtdel &lt;id&gt;</code>\n"
            "ID смотри в <code>/rtqueue</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Некорректный ID задачи.")
        return
    ok, msg = rt_downloader.delete_task(task_id)
    await update.message.reply_text(f"{'✅' if ok else '❌'} {msg}")


# ════════════════════════════════════════════════════════════
#                      CALLBACK ROUTER (dispatch table)
# ════════════════════════════════════════════════════════════


async def _render_nav_entry(entry: dict, update: Update, context: CallbackContext):
    view = entry.get("type")
    if view == "results":
        books = context.user_data.get("search_results", [])
        if books:
            await show_books_page(books, update, context, None, entry.get("page", 1))
        else:
            await update.callback_query.answer("Результаты поиска не найдены", show_alert=True)
    elif view == "favorites":
        await show_favorites(update, context)
    elif view == "history":
        await show_user_history(update, context)
    elif view == "stats":
        await show_user_statistics(update, context)
    elif view == "settings":
        await show_user_settings(update, context)
    elif view == "search_menu":
        await show_search_menu(update, context)
    else:
        await show_main_menu(update, context)


# ── Prefix-based handlers ──


async def _handle_toggle_favorite(data: str, query, update: Update, context: CallbackContext):
    book_id = data[len("toggle_favorite_") :]
    await toggle_favorite(book_id, update, context)


async def _handle_get_book_by_format(data: str, query, update: Update, context: CallbackContext):
    try:
        data_part = data[len("get_book_by_format_") :]
        if "|" in data_part:
            book_id, format_encoded = data_part.split("|", 1)
            book_format = unquote(format_encoded)
            await get_book_by_format(book_id, book_format, update, context)
        else:
            parts = data.split("_", 4)
            if len(parts) >= 5:
                book_id = parts[3]
                format_encoded = parts[4]
                book_format = unquote(format_encoded)
                await get_book_by_format(book_id, book_format, update, context)
    except (ValueError, BadRequest) as e:
        logger.error(f"Error decoding format: {e}", exc_info=e)
        await query.answer("Ошибка при обработке формата", show_alert=True)


async def _handle_fmt(data: str, query, update: Update, context: CallbackContext):
    try:
        _, book_id, idx_str = data.split("_", 2)
        fmt_idx = int(idx_str)
        fmt_map = context.user_data.get("book_format_map", {})
        book_formats = fmt_map.get(book_id) or []
        if 0 <= fmt_idx < len(book_formats):
            await get_book_by_format(book_id, book_formats[fmt_idx], update, context)
        else:
            await query.answer("Формат устарел. Откройте карточку книги заново.", show_alert=True)
    except (ValueError, IndexError):
        await query.answer("Ошибка выбора формата", show_alert=True)


async def _handle_qd(data: str, query, update: Update, context: CallbackContext):
    book_id = data[3:]
    await quick_download(book_id, update, context)


async def _handle_set_per_page(data: str, query, update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    try:
        count = int(data.split("_")[3])
        if count in [5, 10, 20]:
            await db_call(db.set_user_preference, user_id, "books_per_page", count)
            await query.answer(f"✅ Установлено {count} книг на странице", show_alert=False)
            await show_user_settings(update, context)
    except (ValueError, IndexError):
        await query.answer("Ошибка при установке настройки", show_alert=True)


async def _handle_set_format(data: str, query, update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    try:
        format_type = data.split("_")[2].lower()
        if format_type in config.ALL_FORMATS:
            await db_call(db.set_user_preference, user_id, "default_format", format_type)
            await query.answer(f"✅ Формат: {format_type.upper()}", show_alert=False)
            await show_user_settings(update, context)
    except (ValueError, IndexError):
        await query.answer("Ошибка при установке формата", show_alert=True)


async def _handle_set_tag(data: str, query, update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    parts = data.split("_", 3)
    if len(parts) >= 4:
        book_id = parts[2]
        tag = parts[3]
        if tag == "none":
            tag = ""
        await db_call(db.update_favorite_tags, user_id, book_id, tag)
        label = shelf_label(tag) if tag else "без полки"
        await query.answer(f"✅ Полка: {label}", show_alert=False)
        await show_book_details_with_favorite(book_id, update, context)


async def _handle_pick_shelf(data: str, query, update: Update, context: CallbackContext):
    book_id = data[len("pick_shelf_") :]
    await query.answer()
    await show_tag_picker(book_id, update, context)


async def _handle_full_ann(data: str, query, update: Update, context: CallbackContext):
    from src.tg_bot_ui import breadcrumbs as _breadcrumbs
    from src.tg_bot_ui import screen as _screen

    book_id = data[len("full_ann_") :]
    book = await book_from_cache(book_id)
    if book and book.annotation:
        ann_text = _screen(
            "📝 <b>Аннотация</b>",
            f"📖 <i>{escape_html(book.title)}</i>\n\n{escape_html(book.annotation)}",
            _breadcrumbs("🏠 Меню", "📖 Книга", "📝 Аннотация"),
        )
        if len(ann_text) > 4096:
            ann_text = ann_text[:4092] + "…"
        kb = [[InlineKeyboardButton("◀️ К книге", callback_data=f"book_{book_id}")]]
        await query.answer()
        await safe_edit_or_send(query, context, ann_text, InlineKeyboardMarkup(kb))
    else:
        await query.answer("Аннотация недоступна", show_alert=True)


async def _handle_book_meta(data: str, query, update: Update, context: CallbackContext):
    book_id = data[len("book_meta_") :]
    await query.answer()
    await show_book_meta(book_id, update, context)


async def _handle_author_books(data: str, query, update: Update, context: CallbackContext):
    book_id = data[len("author_books_") :]
    await query.answer("🔍 Ищу книги автора...")
    await show_other_books_by_author(book_id, update, context)


async def _handle_shelf(data: str, query, update: Update, context: CallbackContext):
    parts = data.split("_")
    if len(parts) >= 3:
        tag = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 1
        context.user_data["fav_tag_filter"] = None if tag == "all" else tag
        await query.answer()
        await show_favorites(update, context, page=page)


async def _handle_page(data: str, query, update: Update, context: CallbackContext):
    try:
        page = int(data.split("_")[1])
        books = context.user_data.get("search_results", [])
        if books:
            await show_books_page(books, update, context, None, page)
    except (ValueError, IndexError):
        pass


async def _handle_book(data: str, query, update: Update, context: CallbackContext):
    book_id = data.split("_")[1]
    current_page = context.user_data.get("current_results_page", 1)
    _push_nav(context, {"type": "results", "page": current_page})
    await show_book_details_with_favorite(book_id, update, context)


async def _handle_show_favorites(data: str, query, update: Update, context: CallbackContext):
    page = int(data.split("_")[2])
    _push_nav(context, {"type": "main_menu"})
    await show_favorites(update, context, page=page)


async def _handle_fav_book(data: str, query, update: Update, context: CallbackContext):
    book_id = data.split("_")[2]
    fav_page = context.user_data.get("current_favorites_page", 1)
    _push_nav(context, {"type": "favorites", "page": fav_page})
    await show_book_details_with_favorite(book_id, update, context)


# Prefix dispatch: (prefix, handler, needs_answer_before)
# handlers that do their own query.answer() have needs_answer_before=False
_PREFIX_HANDLERS = [
    ("toggle_favorite_", _handle_toggle_favorite, False),
    ("get_book_by_format_", _handle_get_book_by_format, False),
    ("fmt_", _handle_fmt, False),
    ("qd_", _handle_qd, False),
    ("set_per_page_", _handle_set_per_page, False),
    ("set_format_", _handle_set_format, False),
    ("set_tag_", _handle_set_tag, False),
    ("pick_shelf_", _handle_pick_shelf, False),
    ("full_ann_", _handle_full_ann, False),
    ("book_meta_", _handle_book_meta, False),
    ("author_books_", _handle_author_books, False),
    ("shelf_", _handle_shelf, False),
    # These need a default answer() before dispatch
    ("page_", _handle_page, True),
    ("book_", _handle_book, True),
    ("show_favorites_", _handle_show_favorites, True),
    ("fav_book_", _handle_fav_book, True),
    # Аудиокниги (RuTracker)
    ("rt_auto_", handle_rt_auto, False),
    ("rt_dl_", handle_rt_dl, False),
    ("rt_pick_", handle_rt_pick, False),
    ("rt_files_page_", handle_rt_files_page, True),
    ("rt_page_", handle_rt_page, True),
]


@check_callback_access
async def button(update: Update, context: CallbackContext) -> None:
    """Central callback-query router (dispatch-table based)."""
    query = update.callback_query
    data = query.data

    # ── Exact-match handlers ──
    if data == "current_page":
        await query.answer("Вы на этой странице")
        return

    if data in ("ab_noop", "rt_noop"):
        await query.answer()
        return

    if data == "admin_rt_del_all":
        user_id = str(update.effective_user.id)
        if not (ADMIN_USER_ID and user_id == ADMIN_USER_ID):
            await query.answer("Нет доступа", show_alert=True)
            return
        await query.answer("Удаляю…")
        ok, msg = rt_downloader.delete_all_tasks()
        summary = f"🗑 <b>Очередь очищена</b>\n\n{escape_html(msg)}"
        try:
            await query.edit_message_text(summary, parse_mode=ParseMode.HTML)
        except BadRequest:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🗑 Очередь очищена\n\n{msg}",
            )
        return

    if data == "page_jump":
        context.user_data["awaiting"] = "page_jump"
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📄 Введите номер страницы:",
        )
        return

    # Interactive search menu buttons
    if data in ("await_title_search", "await_author_search", "await_exact_search", "await_id_search"):
        awaiting_map = {
            "await_title_search": ("title_search", "📖 Введите название книги:"),
            "await_author_search": ("author_search", "👤 Введите фамилию автора:"),
            "await_exact_search": ("exact_search", "🎯 Введите в формате: <code>название | автор</code>"),
            "await_id_search": ("id_search", "🆔 Введите ID книги (число):"),
        }
        awaiting_key, prompt = awaiting_map[data]
        context.user_data["awaiting"] = awaiting_key
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=prompt,
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Sorting ──
    if data in ("sort_title", "sort_author", "sort_default"):
        books = context.user_data.get("search_results", [])
        if not books:
            await query.answer("Нет результатов")
            return
        if data == "sort_title":
            books.sort(key=lambda b: b.title.lower() if b.title else "")
            await query.answer("🔤 Отсортировано по названию")
        elif data == "sort_author":
            books.sort(key=lambda b: b.author.lower() if b.author else "")
            await query.answer("👤 Отсортировано по автору")
        else:
            original = context.user_data.get("search_results_original", [])
            if original:
                context.user_data["search_results"] = list(original)
                books = context.user_data["search_results"]
            await query.answer("↩️ Исходный порядок")
        context.user_data["current_results_page"] = 1
        await show_books_page(books, update, context, None, page=1)
        return

    # ── Favorites: search ──
    if data == "search_favs":
        context.user_data["awaiting"] = "fav_search"
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔍 Введите запрос для поиска в избранном (название или автор):",
        )
        return

    # ── Favorites: export ──
    if data == "export_favs":
        await query.answer("📤 Готовлю файл...")
        await export_favorites(update, context)
        return

    # ── Repeat last search ──
    if data == "repeat_search":
        user_id = str(update.effective_user.id)
        last = await db_call(db.get_last_search, user_id)
        if not last:
            await query.answer("Нет предыдущих поисков", show_alert=True)
            return
        await query.answer("🔄 Повторяю поиск...")
        cmd = last["command"]
        q = last["query"]

        cache_key = f"{cmd}:{q}"
        books = cache_get(cache_key)
        if books is None:
            if cmd == "author":
                raw = await flib_call(flib.scrape_books_by_author, q)
                if raw:
                    all_b = []
                    for group in raw:
                        all_b.extend(group)
                    unique: dict[str, flib.Book] = {}
                    for b in all_b:
                        unique.setdefault(b.id, b)
                    books = list(unique.values())
                else:
                    books = None
            elif cmd == "exact" and "|" in q:
                t, a = q.split("|", 1)
                books = await flib_call(flib.scrape_books_mbl, t.strip(), a.strip())
            else:
                books = await flib_call(flib.scrape_books_by_title, q)
            cache_set(cache_key, books)

        if not books:
            try:
                await query.edit_message_text(f"😔 По запросу «{q}» ничего не найдено.")
            except (BadRequest, Forbidden):
                pass
            return

        save_search_results(context, books, cmd, q)
        await show_books_page(books, update, context, None, page=1)
        return

    # ── Navigation exact matches ──
    if data == "main_menu":
        await query.answer()
        await show_main_menu(update, context)
        return

    if data == "menu_search":
        await query.answer()
        _push_nav(context, {"type": "main_menu"})
        await show_search_menu(update, context)
        return

    if data == "show_history":
        await query.answer()
        _push_nav(context, {"type": "main_menu"})
        await show_user_history(update, context)
        return

    if data == "show_my_stats":
        await query.answer()
        _push_nav(context, {"type": "main_menu"})
        await show_user_statistics(update, context)
        return

    if data == "show_settings":
        await query.answer()
        _push_nav(context, {"type": "main_menu"})
        await show_user_settings(update, context)
        return

    if data in ("back_to_results", "nav_back"):
        await query.answer()
        prev = _pop_nav(context)
        if prev:
            await _render_nav_entry(prev, update, context)
        else:
            await show_main_menu(update, context)
        return

    # ── Prefix-based dispatch ──
    for prefix, handler, needs_answer in _PREFIX_HANDLERS:
        if data.startswith(prefix):
            if needs_answer:
                await query.answer()
            await handler(data, query, update, context)
            return

    # ── Legacy callback format ──
    if " " in data:
        await query.answer()
        command, arg = data.split(" ", maxsplit=1)
        if command == "find_book_by_id":
            await show_book_details_with_favorite(arg, update, context)
        elif command == "get_book_by_format" and "+" in arg:
            book_id, book_format = arg.split("+", maxsplit=1)
            await get_book_by_format(book_id, book_format, update, context)


# ════════════════════════════════════════════════════════════
#                      INLINE QUERY
# ════════════════════════════════════════════════════════════


async def inline_query(update: Update, context: CallbackContext) -> None:
    """Inline mode: quick title search with pagination."""
    if ALLOWED_USERS:
        uid = str(update.effective_user.id)
        if uid not in ALLOWED_USERS:
            return

    query_text = update.inline_query.query.strip()
    if not query_text or len(query_text) < 3:
        return

    # Parse offset for pagination
    raw_offset = update.inline_query.offset
    offset = int(raw_offset) if raw_offset and raw_offset.isdigit() else 0

    cache_key = f"inline:{query_text}"
    books = cache_get(cache_key)
    if books is None:
        books = await flib_call(flib.scrape_books_by_title, query_text) or []
        cache_set(cache_key, books)

    bot_username = context.bot.username or "bot"

    page_size = 10
    page_books = books[offset : offset + page_size]
    next_offset = str(offset + page_size) if offset + page_size < len(books) else ""

    results = []
    for book in page_books:
        deep_link = f"https://t.me/{bot_username}?start=book_{book.id}"
        results.append(
            InlineQueryResultArticle(
                id=str(book.id),
                title=f"{book.title} — {book.author}",
                description=f"ID: {book.id}  •  {book.link}",
                input_message_content=InputTextMessageContent(
                    f"📖 <b>{escape_html(book.title)}</b>\n"
                    f"✍️ <i>{escape_html(book.author)}</i>\n\n"
                    f'🔗 <a href="{deep_link}">Открыть в боте</a>',
                    parse_mode=ParseMode.HTML,
                ),
            )
        )
    await update.inline_query.answer(results, cache_time=10, next_offset=next_offset)


# ════════════════════════════════════════════════════════════
#                      JOBS & ERROR HANDLER
# ════════════════════════════════════════════════════════════


async def cleanup_job(context: CallbackContext):
    """Daily cleanup of stale data."""
    await db_call(db.cleanup_old_data, days=30)
    await flib_call(flib.cleanup_old_files, days=30)
    logger.info("Database cleanup completed")


async def app_error_handler(update: object, context: CallbackContext) -> None:
    """Global PTB error handler."""
    if context.error:
        inc_error_stat(context, context.error)
    logger.error("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        except (BadRequest, Forbidden):
            pass
