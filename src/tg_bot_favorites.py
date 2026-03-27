"""Favorites management: display, toggle, shelves, export, author books."""

import io
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import CallbackContext

from src import config, flib
from src import database as db
from src.tg_bot_helpers import (
    FAVORITES_PER_PAGE,
    book_from_cache,
    db_call,
    flib_call,
    safe_edit_or_send,
    save_search_results,
)
from src.tg_bot_nav import push_nav as _push_nav
from src.tg_bot_presentation import escape_html, shelf_label
from src.tg_bot_ui import breadcrumbs, screen, truncate
from src.tg_bot_views import (
    show_book_details_with_favorite,
    show_books_page,
)


async def show_favorites(update: Update, context: CallbackContext, *, page: int = 1):
    """Display favorite books with shelves, search, export."""
    user_id = str(update.effective_user.id)
    tag_filter = context.user_data.get("fav_tag_filter")

    offset = (page - 1) * FAVORITES_PER_PAGE
    favorites, total = await db_call(
        db.get_user_favorites,
        user_id,
        offset,
        FAVORITES_PER_PAGE,
        tag=tag_filter,
    )
    context.user_data["current_favorites_page"] = page

    tag_counts = await db_call(db.get_favorites_count_by_tag, user_id)
    total_all = sum(tag_counts.values())

    if not favorites and not total_all:
        text = screen(
            "⭐ <b>Избранное</b>",
            "У вас пока нет избранных книг.\n\nДобавляйте книги в избранное для быстрого доступа!",
            breadcrumbs("🏠 Меню", "⭐ Избранное"),
        )
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await safe_edit_or_send(update.callback_query, context, text, reply_markup)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return

    total_pages = math.ceil(total / FAVORITES_PER_PAGE) if total > 0 else 1

    shelf_name = shelf_label(tag_filter) if tag_filter else "Все"
    body = f"<b>Полка:</b> {shelf_name}\nВсего: {total} книг"
    if total_pages > 1:
        body += f"  •  Стр. {page}/{total_pages}"
    text = screen("⭐ <b>Избранные книги</b>", body, breadcrumbs("🏠 Меню", "⭐ Избранное"))

    kb = []

    # Shelf filters
    kb.append([InlineKeyboardButton(f"📚 Все ({total_all})", callback_data="shelf_all_1")])

    shelf_buttons = []
    for tag_key, tag_label in config.FAVORITE_SHELVES.items():
        cnt = tag_counts.get(tag_key, 0)
        if cnt > 0 or tag_key == tag_filter:
            icon = tag_label.split()[0]
            shelf_buttons.append(InlineKeyboardButton(f"{icon} {cnt}", callback_data=f"shelf_{tag_key}_1"))
    if shelf_buttons:
        for i in range(0, len(shelf_buttons), 4):
            kb.append(shelf_buttons[i : i + 4])

    # Book list
    if favorites:
        for i, fav in enumerate(favorites, start=offset + 1):
            title = truncate(fav["title"], 28)
            author = truncate(fav["author"], 18)
            shelf_icon = ""
            if fav.get("tags") and fav["tags"] in config.FAVORITE_SHELVES:
                shelf_icon = config.FAVORITE_SHELVES[fav["tags"]].split()[0] + " "
            button_text = f"{shelf_icon}{i}. {title} — {author}"
            kb.append([InlineKeyboardButton(button_text, callback_data=f"fav_book_{fav['book_id']}")])
    else:
        text += "\n<i>На этой полке пока пусто</i>\n"

    # Pagination
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"show_favorites_{page - 1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="current_page"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"show_favorites_{page + 1}"))
    if nav_buttons:
        kb.append(nav_buttons)

    kb.append(
        [
            InlineKeyboardButton("🔍 Найти", callback_data="search_favs"),
            InlineKeyboardButton("📤 Экспорт", callback_data="export_favs"),
        ]
    )
    kb.append(
        [
            InlineKeyboardButton("🔍 Поиск книг", callback_data="menu_search"),
            InlineKeyboardButton("🏠 Меню", callback_data="main_menu"),
        ]
    )

    reply_markup = InlineKeyboardMarkup(kb)

    if update.callback_query:
        await safe_edit_or_send(update.callback_query, context, text, reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def toggle_favorite(book_id: str, update: Update, context: CallbackContext):
    """Add / remove a book from favorites (with confirmation for removal)."""
    user_id = str(update.effective_user.id)

    book = await book_from_cache(book_id)
    if not book:
        await update.callback_query.answer("Книга не найдена", show_alert=True)
        return

    if await db_call(db.is_favorite, user_id, book_id):
        # Show confirmation before removing
        text = f"❓ Удалить <b>{escape_html(truncate(book.title, 40))}</b> из избранного?"
        kb = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_unfav_{book_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"book_{book_id}"),
            ]
        ]
        await update.callback_query.answer()
        await safe_edit_or_send(update.callback_query, context, text, InlineKeyboardMarkup(kb))
        return
    else:
        success = await db_call(db.add_to_favorites, user_id, book_id, book.title, book.author)
        if success:
            await update.callback_query.answer("⭐ Добавлено в избранное!", show_alert=False)
        else:
            await update.callback_query.answer("Уже в избранном", show_alert=False)

    await show_book_details_with_favorite(book_id, update, context)


async def confirm_remove_favorite(book_id: str, update: Update, context: CallbackContext):
    """Actually remove a book from favorites after confirmation."""
    user_id = str(update.effective_user.id)
    await db_call(db.remove_from_favorites, user_id, book_id)
    await update.callback_query.answer("✅ Удалено из избранного", show_alert=False)
    await show_book_details_with_favorite(book_id, update, context)


async def show_tag_picker(book_id: str, update: Update, context: CallbackContext):
    """Shelf picker for a favorited book."""
    user_id = str(update.effective_user.id)

    if not await db_call(db.is_favorite, user_id, book_id):
        await update.callback_query.answer("Сначала добавьте в избранное", show_alert=True)
        return

    text = "📚 <b>Выберите полку для книги:</b>"
    kb = []
    for tag_key, tag_label in config.FAVORITE_SHELVES.items():
        kb.append([InlineKeyboardButton(tag_label, callback_data=f"set_tag_{book_id}_{tag_key}")])
    kb.append([InlineKeyboardButton("🚫 Без полки", callback_data=f"set_tag_{book_id}_none")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data=f"book_{book_id}")])

    await safe_edit_or_send(update.callback_query, context, text, InlineKeyboardMarkup(kb))


async def export_favorites(update: Update, context: CallbackContext):
    """Export all favorites as a .txt file."""
    user_id = str(update.effective_user.id)
    favorites = await db_call(db.get_all_favorites_for_export, user_id)

    if not favorites:
        await update.callback_query.answer("Избранное пусто", show_alert=True)
        return

    lines = ["📚 Мои избранные книги\n", f"Всего: {len(favorites)} книг\n"]
    lines.append("=" * 40 + "\n")

    for i, fav in enumerate(favorites, 1):
        shelf = ""
        if fav.get("tags") and fav["tags"] in config.FAVORITE_SHELVES:
            shelf = f" [{config.FAVORITE_SHELVES[fav['tags']]}]"
        lines.append(f"{i}. {fav['title']} — {fav['author']}{shelf}")
        lines.append(f"   ID: {fav['book_id']}  |  Добавлено: {fav['added_date'][:10]}")
        if fav.get("notes"):
            lines.append(f"   📝 {fav['notes']}")
        lines.append("")

    content = "\n".join(lines)
    file_obj = io.BytesIO(content.encode("utf-8"))
    file_obj.name = "favorites.txt"

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=file_obj,
        filename="favorites.txt",
        caption=f"📤 Ваши избранные книги ({len(favorites)} шт.)",
    )
    await update.callback_query.answer("📤 Файл отправлен!")


async def show_other_books_by_author(book_id: str, update: Update, context: CallbackContext):
    """Show other books by the same author."""
    book = await book_from_cache(book_id)
    if not book or not book.author_link:
        await update.callback_query.answer("Информация об авторе недоступна", show_alert=True)
        return

    mes_text = f"🔍 Ищу другие книги автора {book.author}..."
    try:
        await update.callback_query.edit_message_text(mes_text)
    except (BadRequest, Forbidden):
        pass

    other_books = await flib_call(
        flib.get_other_books_by_author,
        book.author_link,
        exclude_book_id=book_id,
        limit=20,
    )

    if not other_books:
        text = f"👤 <b>{escape_html(book.author)}</b>\n\nДругих книг не найдено."
        kb = [[InlineKeyboardButton("◀️ Назад", callback_data=f"book_{book_id}")]]
        await safe_edit_or_send(update.callback_query, context, text, InlineKeyboardMarkup(kb))
        return

    save_search_results(context, other_books, f"автору {book.author}", book.author)

    _push_nav(context, {"type": "results", "page": 1})
    await show_books_page(other_books, update, context, None, page=1)
