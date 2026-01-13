import os
import traceback
import base64
from urllib.error import HTTPError
from functools import wraps
from enum import Enum
import re
from datetime import datetime
from collections import defaultdict
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode

from src import flib
from src import database as db
from src.custom_logging import get_logger

logger = get_logger(__name__)

# Получаем список разрешенных пользователей из переменной окружения
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')
ALLOWED_USERS = [user_id.strip() for user_id in ALLOWED_USERS if user_id.strip()]

# Константы для пагинации
BOOKS_PER_PAGE = 10
FAVORITES_PER_PAGE = 10

# Состояния для ConversationHandler
class SearchState(Enum):
    WAITING_TITLE = 1
    WAITING_AUTHOR = 2
    WAITING_COMBINED = 3


def check_access(func):
    """Декоратор для проверки доступа пользователя"""
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)
        
        # Добавляем/обновляем пользователя в БД
        db.add_or_update_user(
            user_id=user_id,
            username=update.effective_user.username,
            full_name=update.effective_user.full_name,
            is_admin=(ALLOWED_USERS and user_id == ALLOWED_USERS[0])
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
                }
            )
            await update.message.reply_text(
                "⛔ У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору для получения доступа."
            )
            return
        
        return await func(update, context)
    
    return wrapper


def check_callback_access(func):
    """Декоратор для проверки доступа при callback запросах"""
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)
        
        # Обновляем последнюю активность пользователя
        db.add_or_update_user(
            user_id=user_id,
            username=update.effective_user.username,
            full_name=update.effective_user.full_name
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
                }
            )
            query = update.callback_query
            await query.answer("У вас нет доступа к этому боту", show_alert=True)
            return
        
        return await func(update, context)
    
    return wrapper


async def show_main_menu_text(update: Update, context: CallbackContext, is_start: bool = True):
    """Универсальная функция для отображения главного меню"""
    user_name = update.effective_user.first_name or "Книголюб"
    user_id = str(update.effective_user.id)
    
    # Получаем статистику пользователя
    user_stats = db.get_user_stats(user_id)
    favorites_count = user_stats.get('favorites_count', 0)
    search_count = user_stats.get('user_info', {}).get('search_count', 0)
    download_count = user_stats.get('user_info', {}).get('download_count', 0)
    
    # Формируем приветствие в зависимости от команды
    if is_start:
        greeting = f"👋 *Привет, {user_name}!*\n\n📚 *Добро пожаловать в библиотеку Flibusta!*"
    else:
        greeting = "📋 *Справка по командам бота*"
    
    help_text = f"""
{greeting}

━━━━━━━━━━━━━━━━━━━━━
*📊 ВАША СТАТИСТИКА*
━━━━━━━━━━━━━━━━━━━━━
📖 Поисков: {search_count}
📥 Скачиваний: {download_count}
⭐ В избранном: {favorites_count}

━━━━━━━━━━━━━━━━━━━━━
*🔍 КОМАНДЫ ПОИСКА*
━━━━━━━━━━━━━━━━━━━━━

📖 /title `название` - поиск книги по названию
👤 /author `фамилия` - поиск всех книг автора
🎯 /exact `название | автор` - точный поиск книги
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

━━━━━━━━━━━━━━━━━━━━━
*ℹ️ ДОПОЛНИТЕЛЬНО*
━━━━━━━━━━━━━━━━━━━━━

📋 /help - показать это меню
👥 /users - пользователи (админ)
📊 /stats - общая статистика (админ)

_Выберите команду для начала работы!_
    """
    
    # Интерактивные кнопки
    keyboard = [
        [
            InlineKeyboardButton("📖 Поиск книг", callback_data="menu_search"),
            InlineKeyboardButton("⭐ Избранное", callback_data="show_favorites_1")
        ],
        [
            InlineKeyboardButton("📜 История", callback_data="show_history"),
            InlineKeyboardButton("📊 Статистика", callback_data="show_my_stats")
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="show_settings")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


@check_access
async def start_callback(update: Update, context: CallbackContext):
    """Команда /start"""
    await show_main_menu_text(update, context, is_start=True)


@check_access
async def help_command(update: Update, context: CallbackContext):
    """Команда /help"""
    await show_main_menu_text(update, context, is_start=False)

@check_access
async def search_by_title(update: Update, context: CallbackContext) -> None:
    """Поиск только по названию книги"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите название книги после команды\n"
            "Пример: `/title Мастер и Маргарита`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    title = ' '.join(context.args)
    user_id = str(update.effective_user.id)
    
    logger.info(
        msg="search by title",
        extra={
            "command": "search_by_title",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "title": title,
        }
    )
    
    mes = await update.message.reply_text("🔍 Ищу книги по названию...")
    
    try:
        books = flib.scrape_books_by_title(title)
        
        # Записываем в историю поиска
        db.add_search_history(user_id, "title", title, len(books) if books else 0)
        
        if not books:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 По запросу «{title}» ничего не найдено.\n"
                "Попробуйте изменить запрос или использовать другую команду."
            )
            return
        
        # Сохраняем результаты поиска в контексте для пагинации
        context.user_data['search_results'] = books
        context.user_data['search_type'] = 'title'
        context.user_data['search_query'] = title
        context.user_data['current_results_page'] = 1
        
        await show_books_page(books, update, context, mes, page=1)
        
    except Exception as e:
        await handle_error(e, update, context, mes)

# Замените функцию search_by_author в tg_bot.py на эту исправленную версию:

@check_access
async def search_by_author(update: Update, context: CallbackContext) -> None:
    """Поиск всех книг конкретного автора"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите фамилию автора после команды\n"
            "Пример: `/author Толстой`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    author = ' '.join(context.args)
    user_id = str(update.effective_user.id)
    
    logger.info(
        msg="search by author",
        extra={
            "command": "search_by_author", 
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "author": author,
        }
    )
    
    mes = await update.message.reply_text("🔍 Ищу книги автора...")
    
    try:
        authors_books = flib.scrape_books_by_author(author)
        
        # ИСПРАВЛЕНО: проверяем правильно
        if not authors_books or len(authors_books) == 0:
            db.add_search_history(user_id, "author", author, 0)
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 Автор «{author}» не найден.\n"
                "Попробуйте:\n"
                "• Проверить правописание\n"
                "• Использовать только фамилию"
            )
            return
        
        # Объединяем все книги
        all_books = []
        for author_books in authors_books:
            if author_books:  # Проверяем, что список не пустой
                all_books.extend(author_books)
        
        # Если после объединения книг нет
        if not all_books:
            db.add_search_history(user_id, "author", author, 0)
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 У автора «{author}» нет доступных книг."
            )
            return
        
        # Убираем дубликаты
        unique_books = {}
        for book in all_books:
            if book and hasattr(book, 'id'):  # Проверяем, что объект книги валидный
                if book.id not in unique_books:
                    unique_books[book.id] = book
        
        books_list = list(unique_books.values())
        
        # Сортируем по названию, если есть книги
        if books_list:
            books_list.sort(key=lambda x: x.title if hasattr(x, 'title') else '')
        
        # Записываем в историю
        db.add_search_history(user_id, "author", author, len(books_list))
        
        # Сохраняем для пагинации
        context.user_data['search_results'] = books_list
        context.user_data['search_type'] = 'author'
        context.user_data['search_query'] = author
        context.user_data['current_results_page'] = 1
        
        await show_books_page(books_list, update, context, mes, page=1)
        
    except Exception as e:
        logger.error(f"Error in search_by_author: {e}")
        await handle_error(e, update, context, mes)

@check_access
async def search_exact(update: Update, context: CallbackContext) -> None:
    """Точный поиск книги по названию и автору"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите название и автора через разделитель |\n"
            "Пример: `/exact Война и мир | Толстой`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    search_text = ' '.join(context.args)
    user_id = str(update.effective_user.id)
    
    if '|' not in search_text:
        await update.message.reply_text(
            "❌ Используйте разделитель | между названием и автором\n"
            "Пример: `/exact Мастер и Маргарита | Булгаков`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    parts = search_text.split('|')
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
        }
    )
    
    mes = await update.message.reply_text("🔍 Выполняю точный поиск...")
    
    try:
        books = flib.scrape_books_mbl(title, author)
        
        # Записываем в историю
        db.add_search_history(user_id, "exact", f"{title} | {author}", len(books) if books else 0)
        
        if not books:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 Книга «{title}» автора «{author}» не найдена.\n"
                "Попробуйте команды /title или /author для более широкого поиска."
            )
            return
        
        # Сохраняем для пагинации
        context.user_data['search_results'] = books
        context.user_data['search_type'] = 'точному поиску'
        context.user_data['search_query'] = f"{title} | {author}"
        context.user_data['current_results_page'] = 1
        
        await show_books_page(books, update, context, mes, page=1)
        
    except Exception as e:
        await handle_error(e, update, context, mes)


@check_access
async def search_by_id(update: Update, context: CallbackContext) -> None:
    """Получить книгу по ID"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите ID книги после команды\n"
            "Пример: `/id 123456`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    book_id = context.args[0]
    user_id = str(update.effective_user.id)
    
    if not book_id.isdigit():
        await update.message.reply_text(
            "❌ ID должен быть числом\n"
            "Пример: `/id 123456`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    logger.info(
        msg="search by id",
        extra={
            "command": "search_by_id",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "book_id": book_id,
        }
    )
    
    mes = await update.message.reply_text("🔍 Получаю информацию о книге...")
    
    try:
        # Проверяем кэш
        cached_book = db.get_cached_book(book_id)
        if cached_book:
            book = flib.Book(book_id)
            book.title = cached_book['title']
            book.author = cached_book['author']
            book.link = cached_book['link']
            book.formats = cached_book['formats']
            book.cover = cached_book['cover']
            book.size = cached_book['size']
        else:
            book = flib.get_book_by_id(book_id)
            if book:
                db.cache_book(book)
        
        # Записываем в историю
        db.add_search_history(user_id, "id", book_id, 1 if book else 0)
        
        if not book:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(f"😔 Книга с ID {book_id} не найдена.")
            return
        
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        
        # Показываем детали книги
        await show_book_details_with_favorite(book_id, update, context)
        
    except Exception as e:
        await handle_error(e, update, context, mes)


@check_access
async def universal_search(update: Update, _: CallbackContext):
    """Старый интерфейс поиска для обратной совместимости"""
    await update.message.reply_text(
        "🔍 *Универсальный поиск*\n\n"
        "Введите название книги (без автора) ИЛИ добавьте фамилию автора на новой строке.\n"
        "\n"
        "*Пример:*\n"
        "```\n"
        "1984\n"
        "Оруэлл\n"
        "```\n"
        "\n💡 *Совет:* Используйте новые команды для более точного поиска:\n"
        "• /title - поиск по названию\n"
        "• /author - поиск по автору\n"
        "• /exact - точный поиск",
        parse_mode=ParseMode.MARKDOWN
    )

@check_access
async def find_the_book(update: Update, context: CallbackContext) -> None:
    """Обработка текстовых сообщений - интерпретируем как поиск по названию"""
    # Проверяем, не является ли это командой
    if update.message.text.startswith('/'):
        return
    
    user_id = str(update.effective_user.id)
    search_string = update.message.text.strip()
    
    # Если в тексте есть перенос строки, используем старую логику (название + автор)
    if "\n" in search_string:
        # Старая логика для обратной совместимости
        title, author = search_string.split("\n", maxsplit=1)
        
        logger.info(
            msg="combined search",
            extra={
                "command": "find_the_book",
                "user_id": user_id,
                "user_name": update.effective_user.name,
                "user_full_name": update.effective_user.full_name,
                "book_name": title,
                "author": author,
            }
        )
        
        mes = await update.message.reply_text("🔍 Ищу книгу по названию и автору...")
        
        try:
            books = flib.scrape_books_mbl(title, author)
            
            # Записываем в историю
            db.add_search_history(user_id, "exact", f"{title} | {author}", len(books) if books else 0)
            
            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(
                    f"😔 Книга «{title}» автора «{author}» не найдена.\n"
                    "Попробуйте использовать команды /title или /author для более широкого поиска."
                )
                return
            
            # Сохраняем для пагинации
            context.user_data['search_results'] = books
            context.user_data['search_type'] = 'точному поиску'
            context.user_data['search_query'] = f"{title} | {author}"
            context.user_data['current_results_page'] = 1
            
            await show_books_page(books, update, context, mes, page=1)
            
        except Exception as e:
            await handle_error(e, update, context, mes)
    
    else:
        # Простой текст интерпретируем как поиск по названию
        logger.info(
            msg="search by title (text message)",
            extra={
                "command": "find_the_book",
                "user_id": user_id,
                "user_name": update.effective_user.name,
                "user_full_name": update.effective_user.full_name,
                "book_name": search_string,
            }
        )
        
        mes = await update.message.reply_text("🔍 Ищу книги по названию...")
        
        try:
            books = flib.scrape_books_by_title(search_string)
            
            # Записываем в историю поиска
            db.add_search_history(user_id, "title", search_string, len(books) if books else 0)
            
            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                
                # Предлагаем альтернативы
                await update.message.reply_text(
                    f"😔 По запросу «{search_string}» книги не найдены.\n\n"
                    "💡 *Попробуйте:*\n"
                    "• Проверить правописание\n"
                    "• Использовать `/author` для поиска по автору\n"
                    "• Добавить автора на новой строке для точного поиска:\n"
                    f"```\n{search_string}\nФамилия автора\n```",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Сохраняем результаты поиска в контексте для пагинации
            context.user_data['search_results'] = books
            context.user_data['search_type'] = 'названию'
            context.user_data['search_query'] = search_string
            context.user_data['current_results_page'] = 1
            
            await show_books_page(books, update, context, mes, page=1)
            
        except Exception as e:
            await handle_error(e, update, context, mes)

async def handle_error(error, update: Update, context: CallbackContext, mes):
    """Обработка ошибок"""
    try:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
    except Exception:
        pass  # Игнорируем ошибки при удалении сообщения
    
    try:
        await update.message.reply_text(
            "❌ Произошла ошибка при выполнении запроса.\n"
            "Попробуйте позже или используйте другую команду."
        )
    except Exception:
        pass  # Игнорируем ошибки при отправке сообщения
    
    # Правильное логирование исключений
    logger.error(
        "Error occurred",
        exc_info=error,
        extra={
            "user_id": str(update.effective_user.id) if update.effective_user else None,
            "error_type": type(error).__name__,
            "error_message": str(error)
        }
    )

async def show_books_page(books, update: Update, context: CallbackContext, mes, page: int = 1):
    """Отображение страницы с результатами поиска"""
    total_books = len(books)
    total_pages = math.ceil(total_books / BOOKS_PER_PAGE)
    
    # Проверяем корректность страницы
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages
    
    # Сохраняем текущую страницу в контексте
    context.user_data['current_results_page'] = page
    
    # Вычисляем индексы для текущей страницы
    start_idx = (page - 1) * BOOKS_PER_PAGE
    end_idx = min(start_idx + BOOKS_PER_PAGE, total_books)
    page_books = books[start_idx:end_idx]
    
    # Формируем заголовок
    search_type = context.user_data.get('search_type', 'поиску')
    search_query = context.user_data.get('search_query', '')
    
    header_text = f"""
📚 *Результаты по {search_type}: «{search_query}»*

Найдено: {total_books} книг
Страница {page} из {total_pages}
    """
    
    # Создаем кнопки для книг
    kb = []
    user_id = str(update.effective_user.id)
    
    for i, book in enumerate(page_books, start=start_idx + 1):
        # Проверяем, есть ли книга в избранном
        is_fav = db.is_favorite(user_id, book.id)
        star = "⭐ " if is_fav else ""
        
        # Сокращаем длинные названия
        title = book.title[:35] + "..." if len(book.title) > 35 else book.title
        author = book.author[:20] + "..." if len(book.author) > 20 else book.author
        
        text = f"{star}{i}. {title} - {author}"
        callback_data = f"book_{book.id}"
        kb.append([InlineKeyboardButton(text, callback_data=callback_data)])
    
    # Добавляем кнопки навигации
    nav_buttons = []
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}"))
    
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="current_page"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"page_{page+1}"))
    
    if nav_buttons:
        kb.append(nav_buttons)
    
    # Добавляем кнопки быстрой навигации для большого количества страниц
    if total_pages > 5:
        quick_nav = []
        if page > 3:
            quick_nav.append(InlineKeyboardButton("⏮ В начало", callback_data="page_1"))
        if page < total_pages - 2:
            quick_nav.append(InlineKeyboardButton("В конец ⏭", callback_data=f"page_{total_pages}"))
        if quick_nav:
            kb.append(quick_nav)
    
    # Кнопка главного меню
    kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(kb)
    
    # Обновляем или отправляем сообщение
    if mes:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        await update.message.reply_text(
            header_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        # Для callback queries
        query = update.callback_query
        await query.edit_message_text(
            header_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )


async def show_book_details_with_favorite(book_id: str, update: Update, context: CallbackContext):
    """Показать детали книги с кнопкой избранного"""
    user_id = str(update.effective_user.id)
    
    # Проверяем кэш
    cached_book = db.get_cached_book(book_id)
    if cached_book:
        book = flib.Book(book_id)
        book.title = cached_book['title']
        book.author = cached_book['author']
        book.link = cached_book['link']
        book.formats = cached_book['formats']
        book.cover = cached_book['cover']
        book.size = cached_book['size']
        book.series = cached_book.get('series', '')
        book.year = cached_book.get('year', '')
    else:
        book = flib.get_book_by_id(book_id)
        if book:
            db.cache_book(book)
    
    if not book:
        error_msg = "Книга не найдена"
        if update.callback_query:
            await update.callback_query.answer(error_msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(error_msg)
        return
    
    # Проверяем, есть ли в избранном
    is_fav = db.is_favorite(user_id, book_id)
    
    # Формируем описание
    capt = f"""
📖 *{book.title}*
✍️ _{book.author}_
"""
    if hasattr(book, 'series') and book.series:
        capt += f"📚 Серия: {book.series}\n"
    if hasattr(book, 'year') and book.year:
        capt += f"📅 Год: {book.year}\n"
    if book.size:
        capt += f"📊 Размер: {book.size}\n"
    
    capt += f"\n🔗 [Ссылка на сайт]({book.link})"
    
    # Создаем кнопки
    kb = []
    
    # Кнопка избранного
    fav_text = "⭐ Убрать из избранного" if is_fav else "⭐ Добавить в избранное"
    kb.append([InlineKeyboardButton(fav_text, callback_data=f"toggle_favorite_{book_id}")])
    
    # Кнопки форматов
    for b_format in book.formats:
        text = f"📥 Скачать {b_format}"
        # Используем base64 для безопасной передачи формата (может содержать спецсимволы)
        format_encoded = base64.b64encode(b_format.encode('utf-8')).decode('ascii')
        callback_data = f"get_book_by_format_{book_id}_{format_encoded}"
        kb.append([InlineKeyboardButton(text, callback_data=callback_data)])
    
    # Кнопка назад
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_results")])
    
    reply_markup = InlineKeyboardMarkup(kb)
    
    # Отправляем или обновляем сообщение
    if book.cover:
        try:
            flib.download_book_cover(book)
            # Используем абсолютный путь для надежности
            books_dir = os.path.join(os.getcwd(), "books")
            c_full_path = os.path.join(books_dir, book_id, "cover.jpg")
            if not os.path.exists(c_full_path):
                raise FileNotFoundError("Cover not found")
            with open(c_full_path, "rb") as cover:
                # Отправляем фото (одинаково для callback и message)
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=cover,
                    caption=capt,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                # Удаляем предыдущее сообщение если это callback
                if update.callback_query:
                    await update.callback_query.delete_message()
        except Exception:
            # Если не удалось отправить фото, отправляем текст
            text = "[обложка недоступна]\n\n" + capt
            await _send_or_edit_message(update, context, text, reply_markup)
    else:
        # Нет обложки, отправляем текст
        text = "[обложки нет]\n\n" + capt
        await _send_or_edit_message(update, context, text, reply_markup)


async def _send_or_edit_message(update: Update, context: CallbackContext, text: str, reply_markup):
    """Вспомогательная функция для отправки или редактирования сообщения"""
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )


@check_access
async def show_favorites(update: Update, context: CallbackContext):
    """Показать избранные книги"""
    user_id = str(update.effective_user.id)
    page = 1
    
    # Если вызвано из callback, получаем страницу
    if update.callback_query:
        callback_data = update.callback_query.data
        if callback_data.startswith("show_favorites_"):
            page = int(callback_data.split("_")[2])
    
    # Получаем избранное с пагинацией
    offset = (page - 1) * FAVORITES_PER_PAGE
    favorites, total = db.get_user_favorites(user_id, offset, FAVORITES_PER_PAGE)
    
    if not favorites:
        text = "⭐ *Избранное*\n\nУ вас пока нет избранных книг.\n\nДобавляйте книги в избранное для быстрого доступа!"
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return
    
    total_pages = math.ceil(total / FAVORITES_PER_PAGE)
    
    text = f"""
⭐ *Избранные книги*

Всего: {total} книг
Страница {page} из {total_pages}

━━━━━━━━━━━━━━━━━━━━━
    """
    
    # Создаем кнопки для книг
    kb = []
    for i, fav in enumerate(favorites, start=offset + 1):
        title = fav['title'][:35] + "..." if len(fav['title']) > 35 else fav['title']
        author = fav['author'][:20] + "..." if len(fav['author']) > 20 else fav['author']
        
        button_text = f"{i}. {title} - {author}"
        callback_data = f"fav_book_{fav['book_id']}"
        kb.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"show_favorites_{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="current_page"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"show_favorites_{page+1}"))
    
    if nav_buttons:
        kb.append(nav_buttons)
    
    # Дополнительные кнопки
    kb.append([
        InlineKeyboardButton("🔍 Поиск", callback_data="menu_search"),
        InlineKeyboardButton("🏠 Меню", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(kb)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def toggle_favorite(book_id: str, update: Update, context: CallbackContext):
    """Добавить/удалить книгу из избранного"""
    user_id = str(update.effective_user.id)
    
    # Получаем информацию о книге
    book = flib.get_book_by_id(book_id)
    if not book:
        await update.callback_query.answer("Книга не найдена", show_alert=True)
        return
    
    # Проверяем текущий статус
    if db.is_favorite(user_id, book_id):
        # Удаляем из избранного
        db.remove_from_favorites(user_id, book_id)
        await update.callback_query.answer("✅ Удалено из избранного", show_alert=False)
    else:
        # Добавляем в избранное
        success = db.add_to_favorites(user_id, book_id, book.title, book.author)
        if success:
            await update.callback_query.answer("⭐ Добавлено в избранное!", show_alert=False)
        else:
            await update.callback_query.answer("Уже в избранном", show_alert=False)
    
    # Обновляем сообщение с деталями книги
    await show_book_details_with_favorite(book_id, update, context)


async def get_book_by_format(book_id: str, book_format: str, update: Update, context: CallbackContext):
    """Скачивание книги в выбранном формате"""
    user_id = str(update.effective_user.id)
    
    logger.info(
        msg="get book by format",
        extra={
            "command": "get_book_by_format",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "book_id": book_id,
            "format": book_format,
        }
    )
    
    if update.callback_query:
        await update.callback_query.answer("⏳ Начинаю скачивание...")
    
    mes = await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="⏳ Подождите, скачиваю книгу..."
    )
    
    try:
        book = flib.get_book_by_id(book_id)
        if not book:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Книга не найдена."
            )
            return
        
        b_content, b_filename = flib.download_book(book, book_format)
        
        if b_content and b_filename:
            # Записываем в БД
            db.add_download(user_id, book_id, book.title, book.author, book_format)
            
            await context.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=b_content, 
                filename=b_filename,
                caption=f"✅ Книга успешно загружена!\n📖 {book.title}\n✍️ {book.author}"
            )
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        else:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Произошла ошибка при скачивании книги.\nПопробуйте другой формат."
            )
    except Exception as e:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        logger.error(
            "Error downloading book",
            exc_info=e,
            extra={"user_id": user_id, "book_id": book_id, "format": book_format}
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Произошла ошибка при скачивании книги.\nПопробуйте позже."
        )


@check_callback_access
async def button(update: Update, context: CallbackContext) -> None:
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = str(update.effective_user.id)
    
    # Обработка нажатия на текущую страницу (ничего не делаем)
    if data == "current_page":
        await query.answer("Вы на этой странице")
        return
    
    # Навигация по страницам
    if data.startswith("page_"):
        try:
            page = int(data.split("_")[1])
            books = context.user_data.get('search_results', [])
            if books:
                await show_books_page(books, update, context, None, page)
            else:
                await query.answer("Результаты поиска не найдены", show_alert=True)
        except (ValueError, IndexError):
            await query.answer("Ошибка при переходе на страницу", show_alert=True)
        return
    
    # Просмотр книги
    if data.startswith("book_"):
        book_id = data.split("_")[1]
        # Сохраняем текущую страницу результатов для кнопки "Назад"
        # Используем текущую страницу или последнюю сохраненную, или 1 по умолчанию
        current_page = context.user_data.get('current_results_page', 
                                             context.user_data.get('last_results_page', 1))
        context.user_data['last_results_page'] = current_page
        await show_book_details_with_favorite(book_id, update, context)
        return
    
    # Избранное
    if data.startswith("show_favorites_"):
        await show_favorites(update, context)
        return
    
    if data.startswith("fav_book_"):
        book_id = data.split("_")[2]
        await show_book_details_with_favorite(book_id, update, context)
        return
    
    if data.startswith("toggle_favorite_"):
        book_id = data.split("_")[2]
        await toggle_favorite(book_id, update, context)
        return
    
    # Главное меню
    if data == "main_menu":
        await show_main_menu(update, context)
        return
    
    # Меню поиска
    if data == "menu_search":
        await show_search_menu(update, context)
        return
    
    # История
    if data == "show_history":
        await show_user_history(update, context)
        return
    
    # Статистика
    if data == "show_my_stats":
        await show_user_statistics(update, context)
        return
    
    # Настройки
    if data == "show_settings":
        await show_user_settings(update, context)
        return
    
    # Назад к результатам
    if data == "back_to_results":
        books = context.user_data.get('search_results', [])
        if books:
            # Восстанавливаем последнюю страницу результатов или используем страницу 1
            last_page = context.user_data.get('last_results_page', 1)
            await show_books_page(books, update, context, None, last_page)
        else:
            await query.answer("Результаты поиска не найдены", show_alert=True)
        return
    
    # Обработка скачивания книги по формату
    if data.startswith("get_book_by_format_"):
        parts = data.split("_", 4)  # get_book_by_format_{book_id}_{format_encoded}
        if len(parts) >= 5:
            book_id = parts[3]
            format_encoded = parts[4]
            try:
                book_format = base64.b64decode(format_encoded.encode('ascii')).decode('utf-8')
                await get_book_by_format(book_id, book_format, update, context)
            except Exception as e:
                logger.error(f"Error decoding format: {e}", exc_info=e)
                await query.answer("Ошибка при обработке формата", show_alert=True)
        return
    
    # Обработка настроек
    if data.startswith("set_per_page_"):
        try:
            count = int(data.split("_")[3])
            if count in [5, 10, 20]:
                user_id = str(update.effective_user.id)
                db.set_user_preference(user_id, 'books_per_page', count)
                global BOOKS_PER_PAGE
                BOOKS_PER_PAGE = count
                await query.answer(f"✅ Установлено {count} книг на странице", show_alert=False)
                await show_user_settings(update, context)
        except (ValueError, IndexError):
            await query.answer("Ошибка при установке настройки", show_alert=True)
        return
    
    if data.startswith("set_format_"):
        try:
            format_type = data.split("_")[2].lower()
            if format_type in ['fb2', 'epub', 'mobi', 'pdf', 'djvu']:
                user_id = str(update.effective_user.id)
                db.set_user_preference(user_id, 'default_format', format_type)
                await query.answer(f"✅ Установлен формат: {format_type.upper()}", show_alert=False)
                await show_user_settings(update, context)
        except (ValueError, IndexError):
            await query.answer("Ошибка при установке формата", show_alert=True)
        return
    
    # Обработка старых callback'ов для обратной совместимости
    if " " in data:
        command, arg = data.split(" ", maxsplit=1)
        if command == "find_book_by_id":
            await show_book_details_with_favorite(arg, update, context)
        elif command == "get_book_by_format":
            # Старый формат: "get_book_by_format book_id+format"
            if "+" in arg:
                book_id, book_format = arg.split("+", maxsplit=1)
                await get_book_by_format(book_id, book_format, update, context)
            return

async def show_main_menu(update: Update, context: CallbackContext):
    """Показать главное меню"""
    user_name = update.effective_user.first_name or "Книголюб"
    user_id = str(update.effective_user.id)
    
    # Получаем статистику
    user_stats = db.get_user_stats(user_id)
    favorites_count = user_stats.get('favorites_count', 0)
    search_count = user_stats.get('user_info', {}).get('search_count', 0)
    download_count = user_stats.get('user_info', {}).get('download_count', 0)
    
    text = f"""
🏠 *Главное меню*

Привет, {user_name}!

📊 Ваша статистика:
• Поисков: {search_count}
• Скачиваний: {download_count}
• В избранном: {favorites_count}

Выберите действие:
    """
    
    keyboard = [
        [
            InlineKeyboardButton("📖 Поиск книг", callback_data="menu_search"),
            InlineKeyboardButton("⭐ Избранное", callback_data="show_favorites_1")
        ],
        [
            InlineKeyboardButton("📜 История", callback_data="show_history"),
            InlineKeyboardButton("📊 Статистика", callback_data="show_my_stats")
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="show_settings")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def show_search_menu(update: Update, context: CallbackContext):
    """Показать меню поиска"""
    text = """
🔍 *Меню поиска*

Выберите способ поиска:

📖 По названию - найти книги по названию
👤 По автору - все книги автора
🎯 Точный поиск - название + автор
🆔 По ID - если знаете номер книги

Используйте команды:
• `/title название`
• `/author фамилия`
• `/exact название | автор`
• `/id номер`
    """
    
    keyboard = [
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def show_user_history(update: Update, context: CallbackContext):
    """Показать историю поиска пользователя"""
    user_id = str(update.effective_user.id)
    history = db.get_user_search_history(user_id, limit=10)
    
    if not history:
        text = "📜 *История поиска*\n\nИстория пуста"
    else:
        text = "📜 *История поиска*\n\n"
        for item in history:
            timestamp = item['timestamp'][:16]  # Убираем секунды
            command = item['command']
            query = item['query'][:30] + "..." if len(item['query']) > 30 else item['query']
            results = item['results_count']
            
            text += f"🕐 {timestamp}\n"
            text += f"   /{command}: «{query}» ({results} рез.)\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def show_user_statistics(update: Update, context: CallbackContext):
    """Показать статистику пользователя"""
    user_id = str(update.effective_user.id)
    stats = db.get_user_stats(user_id)
    
    user_info = stats.get('user_info', {})
    favorites_count = stats.get('favorites_count', 0)
    favorite_authors = stats.get('favorite_authors', [])
    
    text = f"""
📊 *Ваша статистика*

📅 Дата регистрации: {user_info.get('first_seen', 'Неизвестно')[:10]}
📅 Последняя активность: {user_info.get('last_seen', 'Неизвестно')[:16]}

📈 *Активность:*
• Поисков: {user_info.get('search_count', 0)}
• Скачиваний: {user_info.get('download_count', 0)}
• В избранном: {favorites_count}

👤 *Любимые авторы:*
"""
    
    if favorite_authors:
        for i, author in enumerate(favorite_authors[:5], 1):
            text += f"{i}. {author['author']} ({author['count']} книг)\n"
    else:
        text += "Пока нет данных\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def show_user_settings(update: Update, context: CallbackContext):
    """Показать настройки пользователя"""
    user_id = str(update.effective_user.id)
    
    # Получаем текущие настройки
    books_per_page = db.get_user_preference(user_id, 'books_per_page', BOOKS_PER_PAGE)
    default_format = db.get_user_preference(user_id, 'default_format', 'fb2')
    
    text = f"""
⚙️ *Настройки*

📄 Книг на странице: {books_per_page}
📁 Формат по умолчанию: {default_format}

_Настройки сохраняются автоматически_
    """
    
    keyboard = [
        [
            InlineKeyboardButton("📄 5", callback_data="set_per_page_5"),
            InlineKeyboardButton("📄 10", callback_data="set_per_page_10"),
            InlineKeyboardButton("📄 20", callback_data="set_per_page_20")
        ],
        [
            InlineKeyboardButton("FB2", callback_data="set_format_fb2"),
            InlineKeyboardButton("EPUB", callback_data="set_format_epub"),
            InlineKeyboardButton("MOBI", callback_data="set_format_mobi")
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


# Команды для работы с избранным и историей
@check_access
async def favorites_command(update: Update, context: CallbackContext):
    """Команда для показа избранного"""
    await show_favorites(update, context)


@check_access
async def history_command(update: Update, context: CallbackContext):
    """Команда для показа истории"""
    user_id = str(update.effective_user.id)
    history = db.get_user_search_history(user_id, limit=15)
    
    if not history:
        text = "📜 *История поиска*\n\nИстория пуста\n\nНачните поиск с команд:\n• /title\n• /author\n• /exact"
    else:
        text = "📜 *История поиска (последние 15)*\n\n"
        for item in history:
            timestamp = item['timestamp'][:16]
            command = item['command']
            query = item['query'][:30] + "..." if len(item['query']) > 30 else item['query']
            results = item['results_count']
            
            text += f"🕐 {timestamp}\n"
            text += f"   `/{command}`: «{query}» ({results} рез.)\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@check_access
async def downloads_command(update: Update, context: CallbackContext):
    """Команда для показа истории скачиваний"""
    user_id = str(update.effective_user.id)
    downloads = db.get_user_downloads(user_id, limit=15)
    
    if not downloads:
        text = "📥 *История скачиваний*\n\nПока пусто"
    else:
        text = "📥 *История скачиваний (последние 15)*\n\n"
        for item in downloads:
            timestamp = item['download_date'][:16]
            title = item['title'][:30] + "..." if len(item['title']) > 30 else item['title']
            author = item['author'][:20] + "..." if len(item['author']) > 20 else item['author']
            format_type = item['format']
            
            text += f"🕐 {timestamp}\n"
            text += f"   📖 {title}\n"
            text += f"   ✍️ {author}\n"
            text += f"   📁 Формат: {format_type}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@check_access
async def mystats_command(update: Update, context: CallbackContext):
    """Команда для показа личной статистики"""
    user_id = str(update.effective_user.id)
    stats = db.get_user_stats(user_id)
    
    user_info = stats.get('user_info', {})
    favorites_count = stats.get('favorites_count', 0)
    favorite_authors = stats.get('favorite_authors', [])
    recent_downloads = stats.get('recent_downloads', [])
    
    text = f"""
📊 *Ваша статистика*

👤 *Профиль:*
• ID: `{user_id}`
• Имя: {user_info.get('full_name', 'Неизвестно')}
• Username: @{user_info.get('username', 'нет')}

📅 *Даты:*
• Регистрация: {user_info.get('first_seen', 'Неизвестно')[:10]}
• Последняя активность: {user_info.get('last_seen', 'Неизвестно')[:16]}

📈 *Активность:*
• Поисков: {user_info.get('search_count', 0)}
• Скачиваний: {user_info.get('download_count', 0)}
• В избранном: {favorites_count}

👤 *Топ-5 любимых авторов:*
"""
    
    if favorite_authors:
        for i, author in enumerate(favorite_authors[:5], 1):
            text += f"{i}. {author['author']} — {author['count']} книг\n"
    else:
        text += "Пока нет данных\n"
    
    text += "\n📚 *Последние скачивания:*\n"
    if recent_downloads:
        for download in recent_downloads[:3]:
            title = download['title'][:25] + "..." if len(download['title']) > 25 else download['title']
            text += f"• {title}\n"
    else:
        text += "Пока нет скачиваний\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@check_access
async def settings_command(update: Update, context: CallbackContext):
    """Команда для показа настроек"""
    user_id = str(update.effective_user.id)
    
    # Получаем текущие настройки
    books_per_page = db.get_user_preference(user_id, 'books_per_page', BOOKS_PER_PAGE)
    default_format = db.get_user_preference(user_id, 'default_format', 'fb2')
    notifications = db.get_user_preference(user_id, 'notifications', True)
    
    text = f"""
⚙️ *Настройки*

*Текущие параметры:*
📄 Книг на странице: `{books_per_page}`
📁 Формат по умолчанию: `{default_format}`
🔔 Уведомления: `{'Включены' if notifications else 'Выключены'}`

*Команды для изменения:*
• `/setpage [5|10|20]` - книг на странице
• `/setformat [fb2|epub|mobi|pdf]` - формат по умолчанию

*Примеры:*
`/setpage 20`
`/setformat epub`
    """
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@check_access
async def setpage_command(update: Update, context: CallbackContext):
    """Установить количество книг на странице"""
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите количество книг\n"
            "Пример: `/setpage 20`\n"
            "Доступно: 5, 10, 20",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        count = int(context.args[0])
        if count not in [5, 10, 20]:
            raise ValueError
        
        db.set_user_preference(user_id, 'books_per_page', count)
        global BOOKS_PER_PAGE
        BOOKS_PER_PAGE = count
        
        await update.message.reply_text(f"✅ Установлено {count} книг на странице")
    except ValueError:
        await update.message.reply_text("❌ Некорректное значение. Используйте 5, 10 или 20")


@check_access
async def setformat_command(update: Update, context: CallbackContext):
    """Установить формат по умолчанию"""
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите формат\n"
            "Пример: `/setformat epub`\n"
            "Доступно: fb2, epub, mobi, pdf, djvu",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    format_type = context.args[0].lower()
    if format_type not in ['fb2', 'epub', 'mobi', 'pdf', 'djvu']:
        await update.message.reply_text("❌ Некорректный формат. Используйте: fb2, epub, mobi, pdf, djvu")
        return
    
    db.set_user_preference(user_id, 'default_format', format_type)
    await update.message.reply_text(f"✅ Установлен формат по умолчанию: {format_type.upper()}")


@check_access
async def show_stats(update: Update, _: CallbackContext) -> None:
    """Показать общую статистику (только для админа)"""
    user_id = str(update.effective_user.id)
    
    # Проверяем, является ли пользователь админом
    if ALLOWED_USERS and user_id == ALLOWED_USERS[0]:
        stats = db.get_global_stats()
        
        stats_text = f"""
📊 *Общая статистика бота*

👥 *Пользователи:*
• Всего: {stats['total_users']}
• Активных (7 дней): {stats['active_users']}

📈 *Активность:*
• Поисков: {stats['total_searches']}
• Скачиваний: {stats['total_downloads']}
• В избранном: {stats['total_favorites']}

🔥 *Топ команд:*
"""
        for i, cmd in enumerate(stats['top_commands'][:5], 1):
            stats_text += f"{i}. /{cmd['command']}: {cmd['count']} раз\n"
        
        stats_text += "\n📚 *Топ книг:*\n"
        for i, book in enumerate(stats['top_books'][:5], 1):
            title = book['title'][:30] + "..." if len(book['title']) > 30 else book['title']
            stats_text += f"{i}. {title} ({book['count']} скач.)\n"
        
        stats_text += "\n✍️ *Топ авторов:*\n"
        for i, author in enumerate(stats['top_authors'][:5], 1):
            name = author['author'][:25] + "..." if len(author['author']) > 25 else author['author']
            stats_text += f"{i}. {name} ({author['count']} скач.)\n"
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ У вас нет прав для просмотра статистики")


@check_access
async def list_allowed_users(update: Update, _: CallbackContext) -> None:
    """Команда для отображения списка разрешенных пользователей (только для админов)"""
    user_id = str(update.effective_user.id)
    
    # Проверяем, является ли пользователь первым в списке (админом)
    if ALLOWED_USERS and user_id == ALLOWED_USERS[0]:
        if ALLOWED_USERS:
            # Получаем информацию о пользователях из БД
            users_info = []
            for uid in ALLOWED_USERS:
                user_data = db.get_user(uid)
                if user_data:
                    users_info.append(f"• {uid} - {user_data.get('full_name', 'Неизвестно')}")
                else:
                    users_info.append(f"• {uid} - (не в БД)")
            
            users_list = "\n".join(users_info)
            await update.message.reply_text(
                f"📋 *Список разрешенных пользователей:*\n\n{users_list}\n\n"
                f"_Всего: {len(ALLOWED_USERS)} пользователей_",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("⚠️ Список разрешенных пользователей пуст. Доступ открыт для всех.")
    else:
        await update.message.reply_text("❌ У вас нет прав для просмотра этой информации.")


# Функция для периодической очистки старых данных
async def cleanup_job(context: CallbackContext):
    """Задача для очистки старых данных"""
    db.cleanup_old_data(days=30)
    logger.info("Database cleanup completed")
