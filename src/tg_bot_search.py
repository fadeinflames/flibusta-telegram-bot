"""Search command handlers (/title, /author, /exact, /id, /search, text messages)."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from src import config, flib
from src import database as db
from src.custom_logging import get_logger
from src.tg_bot_helpers import (
    book_from_cache,
    cache_get,
    cache_set,
    check_access,
    db_call,
    flib_call,
    handle_error,
    perform_title_search,
    rate_limit,
    save_search_results,
)
from src.tg_bot_presentation import escape_html
from src.tg_bot_views import show_book_details_with_favorite, show_books_page

logger = get_logger(__name__)


@check_access
@rate_limit(1.0)
async def search_by_title(update: Update, context: CallbackContext) -> None:
    """Search books by title (/title)."""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите название книги после команды\nПример: <code>/title Мастер и Маргарита</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    title = " ".join(context.args)
    user_id = str(update.effective_user.id)

    logger.info(
        msg="search by title",
        extra={
            "command": "search_by_title",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "title": title,
        },
    )

    mes = await update.message.reply_text("🔍 Ищу книги по названию...")

    try:
        books, search_type, hist_cmd, hist_query = await perform_title_search(title, user_id)

        await db_call(db.add_search_history, user_id, hist_cmd, hist_query, len(books) if books else 0)

        if not books:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 По запросу «{title}» ничего не найдено.\n"
                "Попробуйте изменить запрос или использовать другую команду."
            )
            return

        save_search_results(context, books, search_type, title)
        await show_books_page(books, update, context, mes, page=1)

    except Exception as e:
        await handle_error(e, update, context, mes)


@check_access
@rate_limit(1.0)
async def search_by_author(update: Update, context: CallbackContext) -> None:
    """Search books by author (/author)."""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите фамилию автора после команды\nПример: <code>/author Толстой</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    author = " ".join(context.args)
    user_id = str(update.effective_user.id)

    logger.info(
        msg="search by author",
        extra={
            "command": "search_by_author",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "author": author,
        },
    )

    mes = await update.message.reply_text("🔍 Ищу книги автора...")

    try:
        cache_key = f"author:{author}"
        authors_books = cache_get(cache_key)
        if authors_books is None:
            authors_books = await flib_call(flib.scrape_books_by_author, author)
            cache_set(cache_key, authors_books)

        if not authors_books:
            await db_call(db.add_search_history, user_id, "author", author, 0)
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 Автор «{author}» не найден.\nПопробуйте:\n• Проверить правописание\n• Использовать только фамилию"
            )
            return

        all_books = []
        for author_books in authors_books:
            if author_books:
                all_books.extend(author_books)

        if not all_books:
            await db_call(db.add_search_history, user_id, "author", author, 0)
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(f"😔 У автора «{author}» нет доступных книг.")
            return

        unique_books: dict[str, flib.Book] = {}
        for book in all_books:
            if book and hasattr(book, "id") and book.id not in unique_books:
                unique_books[book.id] = book

        books_list = sorted(unique_books.values(), key=lambda x: x.title if x.title else "")

        await db_call(db.add_search_history, user_id, "author", author, len(books_list))

        save_search_results(context, books_list, "автору", author)
        await show_books_page(books_list, update, context, mes, page=1)

    except Exception as e:
        logger.error(f"Error in search_by_author: {e}")
        await handle_error(e, update, context, mes)


@check_access
@rate_limit(1.0)
async def search_exact(update: Update, context: CallbackContext) -> None:
    """Exact search by title + author (/exact)."""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите название и автора через разделитель |\nПример: <code>/exact Война и мир | Толстой</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    search_text = " ".join(context.args)
    user_id = str(update.effective_user.id)

    if "|" not in search_text:
        await update.message.reply_text(
            "❌ Используйте разделитель | между названием и автором\n"
            "Пример: <code>/exact Мастер и Маргарита | Булгаков</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = search_text.split("|")
    title = parts[0].strip()
    author = parts[1].strip()

    logger.info(
        msg="exact search",
        extra={
            "command": "search_exact",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "title": title,
            "author": author,
        },
    )

    mes = await update.message.reply_text("🔍 Выполняю точный поиск...")

    try:
        cache_key = f"exact:{title}|{author}"
        books = cache_get(cache_key)
        if books is None:
            books = await flib_call(flib.scrape_books_mbl, title, author)
            cache_set(cache_key, books)

        await db_call(db.add_search_history, user_id, "exact", f"{title} | {author}", len(books) if books else 0)

        if not books:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 Книга «{title}» автора «{author}» не найдена.\n"
                "Попробуйте команды /title или /author для более широкого поиска."
            )
            return

        save_search_results(context, books, "точному поиску", f"{title} | {author}")
        await show_books_page(books, update, context, mes, page=1)

    except Exception as e:
        await handle_error(e, update, context, mes)


@check_access
@rate_limit(1.0)
async def search_by_id(update: Update, context: CallbackContext) -> None:
    """Fetch a book by ID (/id)."""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите ID книги после команды\nПример: <code>/id 123456</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    book_id = context.args[0]
    user_id = str(update.effective_user.id)

    if not book_id.isdigit():
        await update.message.reply_text(
            "❌ ID должен быть числом\nПример: <code>/id 123456</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    logger.info(
        msg="search by id",
        extra={
            "command": "search_by_id",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "book_id": book_id,
        },
    )

    mes = await update.message.reply_text("🔍 Получаю информацию о книге...")

    try:
        book = await book_from_cache(book_id)
        await db_call(db.add_search_history, user_id, "id", book_id, 1 if book else 0)

        if not book:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(f"😔 Книга с ID {book_id} не найдена.")
            return

        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        await show_book_details_with_favorite(book_id, update, context)

    except Exception as e:
        await handle_error(e, update, context, mes)


@check_access
async def universal_search(update: Update, _: CallbackContext):
    """Legacy search hint (/search)."""
    await update.message.reply_text(
        "🔍 <b>Универсальный поиск</b>\n\n"
        "Введите название книги (без автора) ИЛИ добавьте фамилию автора на новой строке.\n"
        "\n"
        "<b>Пример:</b>\n"
        "<pre>\n"
        "1984\n"
        "Оруэлл\n"
        "</pre>\n"
        "\n💡 <b>Совет:</b> Используйте новые команды для более точного поиска:\n"
        "• /title - поиск по названию\n"
        "• /author - поиск по автору\n"
        "• /exact - точный поиск",
        parse_mode=ParseMode.HTML,
    )


@check_access
@rate_limit(1.0)
async def find_the_book(update: Update, context: CallbackContext) -> None:
    """Handle plain text messages — search or interactive input."""
    if update.message.text.startswith("/"):
        return

    user_id = str(update.effective_user.id)
    search_string = update.message.text.strip()

    # ── Check if we're awaiting interactive input ──
    awaiting = context.user_data.get("awaiting")

    if awaiting == "fav_search":
        context.user_data.pop("awaiting", None)
        results = await db_call(db.search_favorites, user_id, search_string)
        if not results:
            await update.message.reply_text(
                f"😔 В избранном ничего не найдено по запросу «{search_string}».",
            )
            return

        text = f"🔍 <b>Поиск в избранном: «{escape_html(search_string)}»</b>\n\nНайдено: {len(results)}\n"
        kb = []
        for i, fav in enumerate(results[:20], 1):
            title = fav["title"][:30] + "…" if len(fav["title"]) > 30 else fav["title"]
            author = fav["author"][:18] + "…" if len(fav["author"]) > 18 else fav["author"]
            shelf_icon = ""
            if fav.get("tags") and fav["tags"] in config.FAVORITE_SHELVES:
                shelf_icon = config.FAVORITE_SHELVES[fav["tags"]].split()[0] + " "
            kb.append(
                [
                    InlineKeyboardButton(
                        f"{shelf_icon}{i}. {title} — {author}",
                        callback_data=f"fav_book_{fav['book_id']}",
                    )
                ]
            )
        kb.append(
            [
                InlineKeyboardButton("⭐ Все избранное", callback_data="show_favorites_1"),
                InlineKeyboardButton("🏠 Меню", callback_data="main_menu"),
            ]
        )
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    if awaiting == "page_jump":
        context.user_data.pop("awaiting", None)
        if search_string.isdigit():
            page = int(search_string)
            books = context.user_data.get("search_results", [])
            if books:
                await show_books_page(books, update, context, None, page)
                return
        await update.message.reply_text("❌ Введите номер страницы (число).")
        return

    if awaiting == "title_search":
        context.user_data.pop("awaiting", None)
        # Delegate to title search logic
        mes = await update.message.reply_text("🔍 Ищу книги по названию...")
        try:
            books, search_type, hist_cmd, hist_query = await perform_title_search(search_string, user_id)
            await db_call(db.add_search_history, user_id, hist_cmd, hist_query, len(books) if books else 0)
            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(f"😔 По запросу «{search_string}» ничего не найдено.")
                return
            save_search_results(context, books, search_type, search_string)
            await show_books_page(books, update, context, mes, page=1)
        except Exception as e:
            await handle_error(e, update, context, mes)
        return

    if awaiting == "author_search":
        context.user_data.pop("awaiting", None)
        mes = await update.message.reply_text("🔍 Ищу книги автора...")
        try:
            cache_key = f"author:{search_string}"
            authors_books = cache_get(cache_key)
            if authors_books is None:
                authors_books = await flib_call(flib.scrape_books_by_author, search_string)
                cache_set(cache_key, authors_books)
            if not authors_books:
                await db_call(db.add_search_history, user_id, "author", search_string, 0)
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(f"😔 Автор «{search_string}» не найден.")
                return
            all_books = []
            for group in authors_books:
                if group:
                    all_books.extend(group)
            unique: dict[str, flib.Book] = {}
            for b in all_books:
                unique.setdefault(b.id, b)
            books_list = sorted(unique.values(), key=lambda x: x.title or "")
            await db_call(db.add_search_history, user_id, "author", search_string, len(books_list))
            save_search_results(context, books_list, "автору", search_string)
            await show_books_page(books_list, update, context, mes, page=1)
        except Exception as e:
            await handle_error(e, update, context, mes)
        return

    if awaiting == "exact_search":
        context.user_data.pop("awaiting", None)
        if "|" not in search_string:
            await update.message.reply_text(
                "❌ Используйте формат: <code>название | автор</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        parts = search_string.split("|", 1)
        title_part = parts[0].strip()
        author_part = parts[1].strip()
        mes = await update.message.reply_text("🔍 Выполняю точный поиск...")
        try:
            cache_key = f"exact:{title_part}|{author_part}"
            books = cache_get(cache_key)
            if books is None:
                books = await flib_call(flib.scrape_books_mbl, title_part, author_part)
                cache_set(cache_key, books)
            await db_call(
                db.add_search_history, user_id, "exact", f"{title_part} | {author_part}", len(books) if books else 0
            )
            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(f"😔 Книга «{title_part}» автора «{author_part}» не найдена.")
                return
            save_search_results(context, books, "точному поиску", f"{title_part} | {author_part}")
            await show_books_page(books, update, context, mes, page=1)
        except Exception as e:
            await handle_error(e, update, context, mes)
        return

    if awaiting == "id_search":
        context.user_data.pop("awaiting", None)
        if not search_string.isdigit():
            await update.message.reply_text("❌ ID должен быть числом.")
            return
        mes = await update.message.reply_text("🔍 Получаю информацию о книге...")
        try:
            book = await book_from_cache(search_string)
            await db_call(db.add_search_history, user_id, "id", search_string, 1 if book else 0)
            if not book:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(f"😔 Книга с ID {search_string} не найдена.")
                return
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await show_book_details_with_favorite(search_string, update, context)
        except Exception as e:
            await handle_error(e, update, context, mes)
        return

    # ── Multi-line: title + author ──
    if "\n" in search_string:
        title, author = search_string.split("\n", maxsplit=1)

        logger.info(
            msg="combined search",
            extra={
                "command": "find_the_book",
                "user_id": user_id,
                "user_name": update.effective_user.name,
                "book_name": title,
                "author": author,
            },
        )

        mes = await update.message.reply_text("🔍 Ищу книгу по названию и автору...")

        try:
            cache_key = f"exact:{title}|{author}"
            books = cache_get(cache_key)
            if books is None:
                books = await flib_call(flib.scrape_books_mbl, title, author)
                cache_set(cache_key, books)

            await db_call(
                db.add_search_history,
                user_id,
                "exact",
                f"{title} | {author}",
                len(books) if books else 0,
            )

            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(
                    f"😔 Книга «{title}» автора «{author}» не найдена.\n"
                    "Попробуйте использовать команды /title или /author для более широкого поиска."
                )
                return

            save_search_results(context, books, "точному поиску", f"{title} | {author}")
            await show_books_page(books, update, context, mes, page=1)

        except Exception as e:
            await handle_error(e, update, context, mes)

    # ── Single-line: title search with fallback ──
    else:
        logger.info(
            msg="search by title (text message)",
            extra={
                "command": "find_the_book",
                "user_id": user_id,
                "user_name": update.effective_user.name,
                "book_name": search_string,
            },
        )

        mes = await update.message.reply_text("🔍 Ищу книги по названию...")

        try:
            books, search_type, hist_cmd, hist_query = await perform_title_search(search_string, user_id)

            await db_call(db.add_search_history, user_id, hist_cmd, hist_query, len(books) if books else 0)

            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(
                    f"😔 По запросу «{search_string}» книги не найдены.\n\n"
                    "💡 <b>Попробуйте:</b>\n"
                    "• Проверить правописание\n"
                    "• Использовать /author для поиска по автору\n"
                    "• Использовать <code>/exact название | автор</code> для точного поиска",
                    parse_mode=ParseMode.HTML,
                )
                return

            save_search_results(context, books, search_type, search_string)
            await show_books_page(books, update, context, mes, page=1)

        except Exception as e:
            await handle_error(e, update, context, mes)
