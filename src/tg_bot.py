import os
import io
import time
import re
import math
from urllib.parse import quote, unquote
from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import CallbackContext
from telegram.constants import ParseMode

from src import flib
from src import database as db
from src import config
from src.custom_logging import get_logger

logger = get_logger(__name__)

# ────────────────────── Caches & state ──────────────────────

# In-memory search cache: key -> (timestamp, value)
_SEARCH_CACHE: "dict[str, tuple[float, object]]" = {}

# Навигационный стек
_NAV_STACK_KEY = "nav_stack"
_MAX_NAV_STACK = 10

# Получаем список разрешенных пользователей из переменной окружения
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')
ALLOWED_USERS = [user_id.strip() for user_id in ALLOWED_USERS if user_id.strip()]

# Константы для пагинации (только как fallback — реальные значения из БД пользователя)
FAVORITES_PER_PAGE = config.FAVORITES_PER_PAGE_DEFAULT


# ────────────────────── Helpers ──────────────────────

def _cache_get(key: str):
    item = _SEARCH_CACHE.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > config.SEARCH_CACHE_TTL_SEC:
        _SEARCH_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value):
    _SEARCH_CACHE[key] = (time.time(), value)
    if len(_SEARCH_CACHE) > config.SEARCH_CACHE_MAX_SIZE:
        oldest_key = sorted(_SEARCH_CACHE.items(), key=lambda x: x[1][0])[0][0]
        _SEARCH_CACHE.pop(oldest_key, None)


def _inc_error_stat(context: CallbackContext, error: Exception):
    stats = context.bot_data.setdefault("error_stats", {})
    name = type(error).__name__
    stats[name] = stats.get(name, 0) + 1


def _push_nav(context: CallbackContext, entry: dict):
    stack = context.user_data.setdefault(_NAV_STACK_KEY, [])
    if stack and stack[-1] == entry:
        return
    stack.append(entry)
    if len(stack) > _MAX_NAV_STACK:
        stack.pop(0)


def _pop_nav(context: CallbackContext):
    stack = context.user_data.get(_NAV_STACK_KEY, [])
    return stack.pop() if stack else None


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


def _escape_md(text: str) -> str:
    """Escape MarkdownV1 special characters in user-provided text."""
    if not text:
        return ""
    for ch in ('_', '*', '`', '['):
        text = text.replace(ch, f'\\{ch}')
    return text


async def _safe_edit_or_send(query, context: CallbackContext, text: str,
                             reply_markup, parse_mode=ParseMode.MARKDOWN):
    """Edit message text; if it fails (e.g. previous message was a photo),
    delete old message and send a new one."""
    try:
        await query.edit_message_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
    except Exception:
        try:
            await query.delete_message()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


def _book_from_cache(book_id: str):
    """Restore a Book from DB cache, or fetch from Flibusta."""
    cached = db.get_cached_book(book_id)
    if cached:
        book = flib.Book(book_id)
        book.title = cached['title']
        book.author = cached['author']
        book.link = cached['link']
        book.formats = cached['formats']
        book.cover = cached['cover']
        book.size = cached['size']
        book.series = cached.get('series', '')
        book.year = cached.get('year', '')
        book.annotation = cached.get('annotation', '')
        book.genres = cached.get('genres', [])
        book.rating = cached.get('rating', '')
        book.author_link = cached.get('author_link', '')
        return book
    book = flib.get_book_by_id(book_id)
    if book:
        db.cache_book(book)
    return book


def _get_user_level(search_count: int, download_count: int) -> str:
    """Определить уровень достижения пользователя."""
    level = config.ACHIEVEMENT_LEVELS[0]
    for lvl in config.ACHIEVEMENT_LEVELS:
        if search_count >= lvl["searches"] and download_count >= lvl["downloads"]:
            level = lvl
    return level["name"]


def _next_level_info(search_count: int, download_count: int) -> str:
    """Информация о следующем уровне."""
    for i, lvl in enumerate(config.ACHIEVEMENT_LEVELS):
        if search_count < lvl["searches"] or download_count < lvl["downloads"]:
            need_s = max(0, lvl["searches"] - search_count)
            need_d = max(0, lvl["downloads"] - download_count)
            parts = []
            if need_s > 0:
                parts.append(f"{need_s} поисков")
            if need_d > 0:
                parts.append(f"{need_d} скачиваний")
            return f"До «{lvl['name']}»: {', '.join(parts)}"
    return "Максимальный уровень достигнут! 🎉"


def _shelf_label(tag: str) -> str:
    """Получить человекочитаемое название полки."""
    return config.FAVORITE_SHELVES.get(tag, tag or "Все")


# ────────────────────── Access decorators ──────────────────────

def check_access(func):
    """Декоратор для проверки доступа пользователя"""
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)
        
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


def rate_limit(min_interval_sec: float = 1.0):
    """Простой rate-limit на пользователя."""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
            user_id = str(update.effective_user.id)
            last_key = f"last_request_{func.__name__}"
            last_time = context.user_data.get(last_key, 0)
            now = time.time()
            if now - last_time < min_interval_sec:
                await update.message.reply_text("⏳ Слишком часто. Подождите пару секунд.")
                return
            context.user_data[last_key] = now
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


def check_callback_access(func):
    """Декоратор для проверки доступа при callback запросах"""
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)
        
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


# ════════════════════════════════════════════════════════════
#                      COMMANDS
# ════════════════════════════════════════════════════════════

async def show_main_menu_text(update: Update, context: CallbackContext, is_start: bool = True):
    """Универсальная функция для отображения главного меню"""
    user_name = update.effective_user.first_name or "Книголюб"
    user_id = str(update.effective_user.id)
    
    user_stats = db.get_user_stats(user_id)
    favorites_count = user_stats.get('favorites_count', 0)
    search_count = user_stats.get('user_info', {}).get('search_count', 0)
    download_count = user_stats.get('user_info', {}).get('download_count', 0)
    level = _get_user_level(search_count, download_count)
    
    if is_start:
        greeting = f"👋 *Привет, {_escape_md(user_name)}!*\n\n📚 *Добро пожаловать в библиотеку Flibusta!*"
    else:
        greeting = "📋 *Справка по командам бота*"
    
    help_text = f"""{greeting}

━━━━━━━━━━━━━━━━━━━━━
*📊 ВАША СТАТИСТИКА*  {level}
━━━━━━━━━━━━━━━━━━━━━
📖 Поисков: {search_count}
📥 Скачиваний: {download_count}
⭐ В избранном: {favorites_count}

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
        ],
    ]

    # Кнопка «повторить последний поиск»
    last = db.get_last_search(user_id)
    if last:
        q_short = last['query'][:20] + '…' if len(last['query']) > 20 else last['query']
        keyboard.append([
            InlineKeyboardButton(f"🔄 Повторить: «{q_short}»", callback_data="repeat_search")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


@check_access
async def start_callback(update: Update, context: CallbackContext):
    """Команда /start — с поддержкой deep links (book_ID)"""
    # Deep link: /start book_123456
    if context.args:
        arg = context.args[0]
        if arg.startswith("book_"):
            book_id = arg[5:]
            if book_id.isdigit():
                mes = await update.message.reply_text("🔍 Загружаю книгу...")
                try:
                    book = _book_from_cache(book_id)
                    await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                    if book:
                        await show_book_details_with_favorite(book_id, update, context)
                    else:
                        await update.message.reply_text(f"😔 Книга с ID {book_id} не найдена.")
                except Exception:
                    await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                    await update.message.reply_text("❌ Ошибка при загрузке книги.")
                return

    await show_main_menu_text(update, context, is_start=True)


@check_access
async def help_command(update: Update, context: CallbackContext):
    """Команда /help"""
    await show_main_menu_text(update, context, is_start=False)


@check_access
@rate_limit(1.0)
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
        cache_key = f"title:{title}"
        books = _cache_get(cache_key)
        if books is None:
            books = flib.scrape_books_by_title(title)
            _cache_set(cache_key, books)
        
        db.add_search_history(user_id, "title", title, len(books) if books else 0)
        
        if not books:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 По запросу «{title}» ничего не найдено.\n"
                "Попробуйте изменить запрос или использовать другую команду."
            )
            return
        
        context.user_data['search_results'] = books
        context.user_data['search_results_original'] = list(books)
        context.user_data['search_type'] = 'title'
        context.user_data['search_query'] = title
        context.user_data['current_results_page'] = 1
        
        await show_books_page(books, update, context, mes, page=1)
        
    except Exception as e:
        await handle_error(e, update, context, mes)


@check_access
@rate_limit(1.0)
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
        cache_key = f"author:{author}"
        authors_books = _cache_get(cache_key)
        if authors_books is None:
            authors_books = flib.scrape_books_by_author(author)
            _cache_set(cache_key, authors_books)
        
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
        
        all_books = []
        for author_books in authors_books:
            if author_books:
                all_books.extend(author_books)
        
        if not all_books:
            db.add_search_history(user_id, "author", author, 0)
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 У автора «{author}» нет доступных книг."
            )
            return
        
        unique_books = {}
        for book in all_books:
            if book and hasattr(book, 'id'):
                if book.id not in unique_books:
                    unique_books[book.id] = book
        
        books_list = list(unique_books.values())
        
        if books_list:
            books_list.sort(key=lambda x: x.title if hasattr(x, 'title') else '')
        
        db.add_search_history(user_id, "author", author, len(books_list))
        
        context.user_data['search_results'] = books_list
        context.user_data['search_results_original'] = list(books_list)
        context.user_data['search_type'] = 'author'
        context.user_data['search_query'] = author
        context.user_data['current_results_page'] = 1
        
        await show_books_page(books_list, update, context, mes, page=1)
        
    except Exception as e:
        logger.error(f"Error in search_by_author: {e}")
        await handle_error(e, update, context, mes)


@check_access
@rate_limit(1.0)
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
        cache_key = f"exact:{title}|{author}"
        books = _cache_get(cache_key)
        if books is None:
            books = flib.scrape_books_mbl(title, author)
            _cache_set(cache_key, books)
        
        db.add_search_history(user_id, "exact", f"{title} | {author}", len(books) if books else 0)
        
        if not books:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 Книга «{title}» автора «{author}» не найдена.\n"
                "Попробуйте команды /title или /author для более широкого поиска."
            )
            return
        
        context.user_data['search_results'] = books
        context.user_data['search_results_original'] = list(books)
        context.user_data['search_type'] = 'точному поиску'
        context.user_data['search_query'] = f"{title} | {author}"
        context.user_data['current_results_page'] = 1
        
        await show_books_page(books, update, context, mes, page=1)
        
    except Exception as e:
        await handle_error(e, update, context, mes)


@check_access
@rate_limit(1.0)
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
        book = _book_from_cache(book_id)
        
        db.add_search_history(user_id, "id", book_id, 1 if book else 0)
        
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
@rate_limit(1.0)
async def find_the_book(update: Update, context: CallbackContext) -> None:
    """Обработка текстовых сообщений — поиск или интерактивный ввод"""
    if update.message.text.startswith('/'):
        return
    
    user_id = str(update.effective_user.id)
    search_string = update.message.text.strip()

    # ── Проверяем, ожидаем ли мы ввод для поиска в избранном ──
    awaiting = context.user_data.get('awaiting')
    if awaiting == 'fav_search':
        context.user_data.pop('awaiting', None)
        results = db.search_favorites(user_id, search_string)
        if not results:
            await update.message.reply_text(
                f"😔 В избранном ничего не найдено по запросу «{search_string}».",
            )
            return
        # Показываем результаты поиска в избранном
        text = f"🔍 *Поиск в избранном: «{_escape_md(search_string)}»*\n\nНайдено: {len(results)}\n"
        kb = []
        for i, fav in enumerate(results[:20], 1):
            title = fav['title'][:30] + "…" if len(fav['title']) > 30 else fav['title']
            author = fav['author'][:18] + "…" if len(fav['author']) > 18 else fav['author']
            shelf_icon = ""
            if fav.get('tags') and fav['tags'] in config.FAVORITE_SHELVES:
                shelf_icon = config.FAVORITE_SHELVES[fav['tags']].split()[0] + " "
            kb.append([InlineKeyboardButton(
                f"{shelf_icon}{i}. {title} — {author}",
                callback_data=f"fav_book_{fav['book_id']}"
            )])
        kb.append([
            InlineKeyboardButton("⭐ Все избранное", callback_data="show_favorites_1"),
            InlineKeyboardButton("🏠 Меню", callback_data="main_menu"),
        ])
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    # ── Обычный поиск ──
    if "\n" in search_string:
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
            cache_key = f"exact:{title}|{author}"
            books = _cache_get(cache_key)
            if books is None:
                books = flib.scrape_books_mbl(title, author)
                _cache_set(cache_key, books)
            
            db.add_search_history(user_id, "exact", f"{title} | {author}", len(books) if books else 0)
            
            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                await update.message.reply_text(
                    f"😔 Книга «{title}» автора «{author}» не найдена.\n"
                    "Попробуйте использовать команды /title или /author для более широкого поиска."
                )
                return
            
            context.user_data['search_results'] = books
            context.user_data['search_results_original'] = list(books)
            context.user_data['search_type'] = 'точному поиску'
            context.user_data['search_query'] = f"{title} | {author}"
            context.user_data['current_results_page'] = 1
            
            await show_books_page(books, update, context, mes, page=1)
            
        except Exception as e:
            await handle_error(e, update, context, mes)
    
    else:
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
            cache_key = f"title:{search_string}"
            books = _cache_get(cache_key)
            if books is None:
                books = flib.scrape_books_by_title(search_string)
                _cache_set(cache_key, books)
            
            db.add_search_history(user_id, "title", search_string, len(books) if books else 0)
            
            if not books:
                await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
                
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
            
            context.user_data['search_results'] = books
            context.user_data['search_results_original'] = list(books)
            context.user_data['search_type'] = 'названию'
            context.user_data['search_query'] = search_string
            context.user_data['current_results_page'] = 1
            
            await show_books_page(books, update, context, mes, page=1)
            
        except Exception as e:
            await handle_error(e, update, context, mes)


# ════════════════════════════════════════════════════════════
#                      DISPLAY FUNCTIONS
# ════════════════════════════════════════════════════════════

async def handle_error(error, update: Update, context: CallbackContext, mes):
    """Обработка ошибок"""
    try:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
    except Exception:
        pass
    
    try:
        await update.message.reply_text(
            "❌ Произошла ошибка при выполнении запроса.\n"
            "Попробуйте позже или используйте другую команду."
        )
    except Exception:
        pass
    
    _inc_error_stat(context, error)
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
    """Отображение страницы с результатами поиска — с сортировкой и быстрым скачиванием"""
    user_id = str(update.effective_user.id)
    per_page = db.get_user_preference(user_id, 'books_per_page', config.BOOKS_PER_PAGE_DEFAULT)
    total_books = len(books)
    total_pages = math.ceil(total_books / per_page) if per_page else 1
    
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages
    
    context.user_data['current_results_page'] = page
    
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_books)
    page_books = books[start_idx:end_idx]
    
    search_type = context.user_data.get('search_type', 'поиску')
    search_query = context.user_data.get('search_query', '')
    
    header_text = f"""📚 *Результаты по {search_type}: «{_escape_md(search_query)}»*

Найдено: {total_books} книг  •  Стр. {page}/{total_pages}
    """
    
    kb = []

    # Кнопки сортировки (компактные)
    sort_row = [
        InlineKeyboardButton("🔤 Название", callback_data="sort_title"),
        InlineKeyboardButton("👤 Автор", callback_data="sort_author"),
        InlineKeyboardButton("↩️ Исходный", callback_data="sort_default"),
    ]
    kb.append(sort_row)

    # Книги с кнопкой быстрого скачивания
    for i, book in enumerate(page_books, start=start_idx + 1):
        is_fav = db.is_favorite(user_id, book.id)
        star = "⭐" if is_fav else ""
        
        title = book.title[:30] + "…" if len(book.title) > 30 else book.title
        author = book.author[:18] + "…" if len(book.author) > 18 else book.author
        
        text = f"{star}{i}. {title} — {author}"
        row = [
            InlineKeyboardButton(text, callback_data=f"book_{book.id}"),
            InlineKeyboardButton("⚡", callback_data=f"qd_{book.id}"),
        ]
        kb.append(row)
    
    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="current_page"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
    if nav_buttons:
        kb.append(nav_buttons)
    
    if total_pages > 5:
        quick_nav = []
        if page > 3:
            quick_nav.append(InlineKeyboardButton("⏮", callback_data="page_1"))
        if page < total_pages - 2:
            quick_nav.append(InlineKeyboardButton("⏭", callback_data=f"page_{total_pages}"))
        if quick_nav:
            kb.append(quick_nav)
    
    kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(kb)
    
    if mes:
        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        await update.message.reply_text(
            header_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        query = update.callback_query
        try:
            await query.edit_message_text(
                header_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except Exception:
            try:
                await query.delete_message()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=header_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )


async def show_book_details_with_favorite(book_id: str, update: Update, context: CallbackContext):
    """Показать детали книги: аннотация, жанры, форматы, share, author books"""
    user_id = str(update.effective_user.id)
    
    book = _book_from_cache(book_id)
    
    if not book:
        error_msg = "Книга не найдена"
        if update.callback_query:
            await update.callback_query.answer(error_msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(error_msg)
        return
    
    is_fav = db.is_favorite(user_id, book_id)
    
    # ── Формируем описание ──
    capt = f"📖 *{_escape_md(book.title)}*\n✍️ _{_escape_md(book.author)}_\n"

    if book.genres:
        genres_str = ', '.join(book.genres[:4])
        capt += f"📂 {_escape_md(genres_str)}\n"
    if book.series:
        capt += f"📚 Серия: {_escape_md(book.series)}\n"
    if book.year:
        capt += f"📅 Год: {book.year}\n"
    if book.size:
        capt += f"📊 Размер: {book.size}\n"
    if book.rating:
        capt += f"⭐ Рейтинг: {book.rating}\n"
    
    capt += f"\n🔗 [Страница на сайте]({book.link})"

    # Аннотация (вставляем в сообщение, а не в caption)
    annotation_short = ""
    has_full_annotation = False
    if book.annotation:
        if len(book.annotation) > 250:
            annotation_short = _escape_md(book.annotation[:247]) + "…"
            has_full_annotation = True
        else:
            annotation_short = _escape_md(book.annotation)
    
    # ── Кнопки ──
    kb = []
    
    # Избранное + полка
    fav_text = "💔 Из избранного" if is_fav else "⭐ В избранное"
    fav_row = [InlineKeyboardButton(fav_text, callback_data=f"toggle_favorite_{book_id}")]
    if is_fav:
        fav_row.append(InlineKeyboardButton("📚 Полка", callback_data=f"pick_shelf_{book_id}"))
    kb.append(fav_row)

    # Быстрое скачивание (формат по умолчанию)
    if book.formats:
        default_fmt = db.get_user_preference(user_id, 'default_format', 'fb2')
        quick_fmt = None
        for fmt_key in book.formats:
            if default_fmt in fmt_key.lower():
                quick_fmt = fmt_key
                break
        if not quick_fmt:
            quick_fmt = next(iter(book.formats))
        quick_label = quick_fmt.strip('()') if quick_fmt else default_fmt
        format_encoded = quote(quick_fmt, safe="")
        kb.append([InlineKeyboardButton(
            f"⚡ Скачать быстро ({quick_label})",
            callback_data=f"get_book_by_format_{book_id}|{format_encoded}"
        )])

    # Горизонтальные кнопки форматов (по 2–3 в ряд)
    fmt_buttons = []
    for b_format in book.formats:
        short_name = b_format.strip('() ').upper()
        format_encoded = quote(b_format, safe="")
        fmt_buttons.append(InlineKeyboardButton(
            f"📥 {short_name}",
            callback_data=f"get_book_by_format_{book_id}|{format_encoded}"
        ))
    # Группируем по 3 в ряд
    for i in range(0, len(fmt_buttons), 3):
        kb.append(fmt_buttons[i:i+3])
    
    # Kindle
    kindle_email = db.get_user_preference(user_id, 'kindle_email')
    if kindle_email:
        kb.append([InlineKeyboardButton("📤 На Kindle", callback_data=f"send_kindle_{book_id}")])

    # Аннотация (полная)
    if has_full_annotation:
        kb.append([InlineKeyboardButton("📝 Полная аннотация", callback_data=f"full_ann_{book_id}")])

    # Другие книги автора
    if book.author_link:
        kb.append([InlineKeyboardButton(
            f"👤 Другие книги: {_escape_md(book.author)[:25]}",
            callback_data=f"author_books_{book_id}"
        )])

    # Поделиться
    bot_username = context.bot.username if context.bot.username else "bot"
    share_url = f"https://t.me/{bot_username}?start=book_{book_id}"
    kb.append([InlineKeyboardButton("📤 Поделиться", url=share_url)])

    # Назад
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_results")])
    
    reply_markup = InlineKeyboardMarkup(kb)

    # ── Подготавливаем длинный текст для текстового сообщения ──
    full_text = capt
    if annotation_short:
        full_text += f"\n\n📝 _{annotation_short}_"
    
    # ── Отправляем ──
    if book.cover:
        try:
            flib.download_book_cover(book)
            c_full_path = os.path.join(config.BOOKS_DIR, book_id, "cover.jpg")
            if not os.path.exists(c_full_path):
                raise FileNotFoundError("Cover not found")

            # Caption лимит 1024 символа — обрезаем если надо
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
                    parse_mode=ParseMode.MARKDOWN
                )
                if update.callback_query:
                    try:
                        await update.callback_query.delete_message()
                    except Exception:
                        pass
        except Exception:
            await _send_or_edit_message(update, context, full_text, reply_markup)
    else:
        await _send_or_edit_message(update, context, full_text, reply_markup)


async def _send_or_edit_message(update: Update, context: CallbackContext, text: str, reply_markup):
    """Вспомогательная функция для отправки или редактирования сообщения"""
    if len(text) > 4096:
        text = text[:4092] + "…"
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            try:
                await update.callback_query.delete_message()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
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


# ════════════════════════════════════════════════════════════
#                      FAVORITES
# ════════════════════════════════════════════════════════════

@check_access
async def show_favorites(update: Update, context: CallbackContext):
    """Показать избранные книги с полками, поиском и экспортом"""
    user_id = str(update.effective_user.id)
    page = 1
    tag_filter = context.user_data.get('fav_tag_filter')  # None = все
    
    if update.callback_query:
        callback_data = update.callback_query.data
        if callback_data.startswith("show_favorites_"):
            page = int(callback_data.split("_")[2])
    
    offset = (page - 1) * FAVORITES_PER_PAGE
    favorites, total = db.get_user_favorites(user_id, offset, FAVORITES_PER_PAGE, tag=tag_filter)
    context.user_data['current_favorites_page'] = page
    
    # Получаем количество по полкам
    tag_counts = db.get_favorites_count_by_tag(user_id)
    total_all = sum(tag_counts.values())

    if not favorites and not total_all:
        text = "⭐ *Избранное*\n\nУ вас пока нет избранных книг.\n\nДобавляйте книги в избранное для быстрого доступа!"
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await _safe_edit_or_send(update.callback_query, context, text, reply_markup)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return
    
    total_pages = math.ceil(total / FAVORITES_PER_PAGE) if total > 0 else 1

    # Заголовок
    shelf_name = _shelf_label(tag_filter) if tag_filter else "Все"
    text = f"⭐ *Избранные книги* — {shelf_name}\n\nВсего: {total} книг"
    if total_pages > 1:
        text += f"  •  Стр. {page}/{total_pages}"
    text += "\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    kb = []

    # ── Фильтры по полкам ──
    shelf_row = [InlineKeyboardButton(
        f"📚 Все ({total_all})" if not tag_filter else f"📚 Все ({total_all})",
        callback_data="shelf_all_1"
    )]
    kb.append(shelf_row)

    shelf_buttons = []
    for tag_key, tag_label in config.FAVORITE_SHELVES.items():
        cnt = tag_counts.get(tag_key, 0)
        if cnt > 0 or tag_key == tag_filter:
            icon = tag_label.split()[0]
            shelf_buttons.append(InlineKeyboardButton(
                f"{icon} {cnt}", callback_data=f"shelf_{tag_key}_1"
            ))
    if shelf_buttons:
        # По 4 в ряд
        for i in range(0, len(shelf_buttons), 4):
            kb.append(shelf_buttons[i:i+4])

    # ── Список книг ──
    if favorites:
        for i, fav in enumerate(favorites, start=offset + 1):
            title = fav['title'][:28] + "…" if len(fav['title']) > 28 else fav['title']
            author = fav['author'][:18] + "…" if len(fav['author']) > 18 else fav['author']
            
            shelf_icon = ""
            if fav.get('tags') and fav['tags'] in config.FAVORITE_SHELVES:
                shelf_icon = config.FAVORITE_SHELVES[fav['tags']].split()[0] + " "
            
            button_text = f"{shelf_icon}{i}. {title} — {author}"
            kb.append([InlineKeyboardButton(button_text, callback_data=f"fav_book_{fav['book_id']}")])
    else:
        text += "\n_На этой полке пока пусто_\n"
    
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
    
    # Утилиты
    kb.append([
        InlineKeyboardButton("🔍 Найти", callback_data="search_favs"),
        InlineKeyboardButton("📤 Экспорт", callback_data="export_favs"),
    ])
    kb.append([
        InlineKeyboardButton("🔍 Поиск книг", callback_data="menu_search"),
        InlineKeyboardButton("🏠 Меню", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(kb)
    
    if update.callback_query:
        await _safe_edit_or_send(update.callback_query, context, text, reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def toggle_favorite(book_id: str, update: Update, context: CallbackContext):
    """Добавить/удалить книгу из избранного"""
    user_id = str(update.effective_user.id)
    
    book = _book_from_cache(book_id)
    if not book:
        await update.callback_query.answer("Книга не найдена", show_alert=True)
        return
    
    if db.is_favorite(user_id, book_id):
        db.remove_from_favorites(user_id, book_id)
        await update.callback_query.answer("✅ Удалено из избранного", show_alert=False)
    else:
        success = db.add_to_favorites(user_id, book_id, book.title, book.author)
        if success:
            await update.callback_query.answer("⭐ Добавлено в избранное!", show_alert=False)
        else:
            await update.callback_query.answer("Уже в избранном", show_alert=False)
    
    await show_book_details_with_favorite(book_id, update, context)


async def show_tag_picker(book_id: str, update: Update, context: CallbackContext):
    """Показать выбор полки для книги"""
    user_id = str(update.effective_user.id)

    # Проверяем, что книга в избранном
    if not db.is_favorite(user_id, book_id):
        await update.callback_query.answer("Сначала добавьте в избранное", show_alert=True)
        return

    text = "📚 *Выберите полку для книги:*"
    kb = []
    for tag_key, tag_label in config.FAVORITE_SHELVES.items():
        kb.append([InlineKeyboardButton(tag_label, callback_data=f"set_tag_{book_id}_{tag_key}")])
    kb.append([InlineKeyboardButton("🚫 Без полки", callback_data=f"set_tag_{book_id}_none")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data=f"book_{book_id}")])

    reply_markup = InlineKeyboardMarkup(kb)
    await _safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def export_favorites(update: Update, context: CallbackContext):
    """Экспортировать избранное в текстовый файл"""
    user_id = str(update.effective_user.id)
    favorites = db.get_all_favorites_for_export(user_id)

    if not favorites:
        await update.callback_query.answer("Избранное пусто", show_alert=True)
        return

    lines = ["📚 Мои избранные книги\n", f"Всего: {len(favorites)} книг\n"]
    lines.append("=" * 40 + "\n")

    for i, fav in enumerate(favorites, 1):
        shelf = ""
        if fav.get('tags') and fav['tags'] in config.FAVORITE_SHELVES:
            shelf = f" [{config.FAVORITE_SHELVES[fav['tags']]}]"
        lines.append(f"{i}. {fav['title']} — {fav['author']}{shelf}")
        lines.append(f"   ID: {fav['book_id']}  |  Добавлено: {fav['added_date'][:10]}")
        if fav.get('notes'):
            lines.append(f"   📝 {fav['notes']}")
        lines.append("")

    content = "\n".join(lines)
    file_obj = io.BytesIO(content.encode("utf-8"))
    file_obj.name = "favorites.txt"

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=file_obj,
        filename="favorites.txt",
        caption=f"📤 Ваши избранные книги ({len(favorites)} шт.)"
    )
    await update.callback_query.answer("📤 Файл отправлен!")


async def show_other_books_by_author(book_id: str, update: Update, context: CallbackContext):
    """Показать другие книги автора"""
    book = _book_from_cache(book_id)
    if not book or not book.author_link:
        await update.callback_query.answer("Информация об авторе недоступна", show_alert=True)
        return

    mes_text = f"🔍 Ищу другие книги автора {book.author}..."
    try:
        await update.callback_query.edit_message_text(mes_text)
    except Exception:
        pass

    other_books = flib.get_other_books_by_author(book.author_link, exclude_book_id=book_id, limit=20)
    
    if not other_books:
        text = f"👤 *{_escape_md(book.author)}*\n\nДругих книг не найдено."
        kb = [[InlineKeyboardButton("◀️ Назад", callback_data=f"book_{book_id}")]]
        reply_markup = InlineKeyboardMarkup(kb)
        await _safe_edit_or_send(update.callback_query, context, text, reply_markup)
        return

    # Сохраняем для навигации
    context.user_data['search_results'] = other_books
    context.user_data['search_results_original'] = list(other_books)
    context.user_data['search_type'] = f'автору {book.author}'
    context.user_data['search_query'] = book.author
    context.user_data['current_results_page'] = 1

    # Пушим текущую книгу в стек навигации
    _push_nav(context, {"type": "results", "page": 1})

    await show_books_page(other_books, update, context, None, page=1)


# ════════════════════════════════════════════════════════════
#                      DOWNLOAD
# ════════════════════════════════════════════════════════════

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
        book = _book_from_cache(book_id)
        if not book:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Книга не найдена."
            )
            return
        
        b_content, b_filename = flib.download_book(book, book_format)
        
        if b_content and b_filename:
            db.add_download(user_id, book_id, book.title, book.author, book_format)
            
            await context.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=b_content, 
                filename=b_filename,
                caption=f"✅ Книга загружена!\n📖 {book.title}\n✍️ {book.author}"
            )
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        else:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Ошибка при скачивании книги.\nПопробуйте другой формат."
            )
    except Exception as e:
        try:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        except Exception:
            pass
        logger.error(
            "Error downloading book",
            exc_info=e,
            extra={"user_id": user_id, "book_id": book_id, "format": book_format}
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка при скачивании книги.\nПопробуйте позже."
        )


async def quick_download(book_id: str, update: Update, context: CallbackContext):
    """Быстрое скачивание в формате по умолчанию"""
    user_id = str(update.effective_user.id)
    default_fmt = db.get_user_preference(user_id, 'default_format', 'fb2')

    if update.callback_query:
        await update.callback_query.answer(f"⏳ Скачиваю ({default_fmt})...")

    mes = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"⏳ Быстрое скачивание ({default_fmt})..."
    )

    try:
        book = _book_from_cache(book_id)
        if not book or not book.formats:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Книга не найдена или нет форматов."
            )
            return

        # Ищем подходящий формат
        selected = None
        for fmt_key in book.formats:
            if default_fmt in fmt_key.lower():
                selected = fmt_key
                break
        if not selected:
            selected = next(iter(book.formats))

        b_content, b_filename = flib.download_book(book, selected)
        if b_content and b_filename:
            db.add_download(user_id, book_id, book.title, book.author, selected)
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=b_content,
                filename=b_filename,
                caption=f"✅ {book.title}\n✍️ {book.author}"
            )
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        else:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Ошибка скачивания. Откройте карточку книги для выбора формата."
            )
    except Exception as e:
        try:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        except Exception:
            pass
        logger.error("Quick download error", exc_info=e)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка скачивания."
        )


async def send_book_to_kindle(book_id: str, update: Update, context: CallbackContext):
    """Скачать книгу и отправить на Kindle email (SMTP)"""
    user_id = str(update.effective_user.id)
    kindle_email = db.get_user_preference(user_id, 'kindle_email')
    if not kindle_email:
        await update.callback_query.answer("Сначала настройте Kindle email: /setkindle", show_alert=True)
        return

    if update.callback_query:
        await update.callback_query.answer("⏳ Готовлю книгу для Kindle...")

    mes = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Подождите, готовлю книгу для Kindle..."
    )

    try:
        book = _book_from_cache(book_id)
        if not book:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Книга не найдена."
            )
            return

        # Выбираем формат, совместимый с Kindle
        preferred_format = db.get_user_preference(user_id, 'default_format', 'epub')
        selected_format = None
        for kindle_fmt in config.KINDLE_FORMATS:
            for fmt_key in book.formats:
                if kindle_fmt in fmt_key.lower():
                    selected_format = fmt_key
                    break
            if selected_format:
                break

        if not selected_format:
            selected_format = next(iter(book.formats.keys()), None)

        if not selected_format:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Нет доступных форматов."
            )
            return

        b_content, b_filename = flib.download_book(book, selected_format)
        if not b_content or not b_filename:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Не удалось скачать книгу."
            )
            return

        await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)

        # Отправляем файл пользователю с инструкцией
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=b_content,
            filename=b_filename,
            caption=(
                f"📤 *Для отправки на Kindle:*\n"
                f"Перешлите этот файл на `{kindle_email}` "
                f"через приложение Send to Kindle или email\\.\n\n"
                f"📖 {_escape_md(book.title)}\n"
                f"✍️ {_escape_md(book.author)}"
            ),
            parse_mode=ParseMode.MARKDOWN,
        )

    except Exception as e:
        try:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        except Exception:
            pass
        logger.error("Error preparing Kindle file", exc_info=e)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка подготовки файла для Kindle."
        )


# ════════════════════════════════════════════════════════════
#                      CALLBACK HANDLER
# ════════════════════════════════════════════════════════════

@check_callback_access
async def button(update: Update, context: CallbackContext) -> None:
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    data = query.data
    user_id = str(update.effective_user.id)

    # ── Ветки с кастомным callback-ответом ──

    if data == "current_page":
        await query.answer("Вы на этой странице")
        return

    if data.startswith("toggle_favorite_"):
        book_id = data[len("toggle_favorite_"):]
        await toggle_favorite(book_id, update, context)
        return

    if data.startswith("get_book_by_format_"):
        try:
            data_part = data[len("get_book_by_format_"):]
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
        except Exception as e:
            logger.error(f"Error decoding format: {e}", exc_info=e)
            await query.answer("Ошибка при обработке формата", show_alert=True)
        return

    if data.startswith("send_kindle_"):
        book_id = data[len("send_kindle_"):]
        await send_book_to_kindle(book_id, update, context)
        return

    if data.startswith("qd_"):
        book_id = data[3:]
        await quick_download(book_id, update, context)
        return

    if data.startswith("set_per_page_"):
        try:
            count = int(data.split("_")[3])
            if count in [5, 10, 20]:
                db.set_user_preference(user_id, 'books_per_page', count)
                await query.answer(f"✅ Установлено {count} книг на странице", show_alert=False)
                await show_user_settings(update, context)
        except (ValueError, IndexError):
            await query.answer("Ошибка при установке настройки", show_alert=True)
        return

    if data.startswith("set_format_"):
        try:
            format_type = data.split("_")[2].lower()
            if format_type in config.ALL_FORMATS:
                db.set_user_preference(user_id, 'default_format', format_type)
                await query.answer(f"✅ Формат: {format_type.upper()}", show_alert=False)
                await show_user_settings(update, context)
        except (ValueError, IndexError):
            await query.answer("Ошибка при установке формата", show_alert=True)
        return

    if data.startswith("set_tag_"):
        # set_tag_{book_id}_{tag}
        parts = data.split("_", 3)
        if len(parts) >= 4:
            book_id = parts[2]
            tag = parts[3]
            if tag == "none":
                tag = ""
            db.update_favorite_tags(user_id, book_id, tag)
            label = _shelf_label(tag) if tag else "без полки"
            await query.answer(f"✅ Полка: {label}", show_alert=False)
            await show_book_details_with_favorite(book_id, update, context)
        return

    if data.startswith("pick_shelf_"):
        book_id = data[len("pick_shelf_"):]
        await query.answer()
        await show_tag_picker(book_id, update, context)
        return

    if data.startswith("full_ann_"):
        book_id = data[len("full_ann_"):]
        book = _book_from_cache(book_id)
        if book and book.annotation:
            ann_text = f"📝 *Аннотация*\n\n📖 _{_escape_md(book.title)}_\n\n{_escape_md(book.annotation)}"
            if len(ann_text) > 4096:
                ann_text = ann_text[:4092] + "…"
            kb = [[InlineKeyboardButton("◀️ К книге", callback_data=f"book_{book_id}")]]
            await query.answer()
            await _safe_edit_or_send(query, context, ann_text, InlineKeyboardMarkup(kb))
        else:
            await query.answer("Аннотация недоступна", show_alert=True)
        return

    if data.startswith("author_books_"):
        book_id = data[len("author_books_"):]
        await query.answer("🔍 Ищу книги автора...")
        await show_other_books_by_author(book_id, update, context)
        return

    # ── Сортировка ──
    if data in ("sort_title", "sort_author", "sort_default"):
        books = context.user_data.get('search_results', [])
        if not books:
            await query.answer("Нет результатов")
            return
        if data == "sort_title":
            books.sort(key=lambda b: b.title.lower() if b.title else '')
            await query.answer("🔤 Отсортировано по названию")
        elif data == "sort_author":
            books.sort(key=lambda b: b.author.lower() if b.author else '')
            await query.answer("👤 Отсортировано по автору")
        else:
            original = context.user_data.get('search_results_original', [])
            if original:
                context.user_data['search_results'] = list(original)
                books = context.user_data['search_results']
            await query.answer("↩️ Исходный порядок")
        context.user_data['current_results_page'] = 1
        await show_books_page(books, update, context, None, page=1)
        return

    # ── Избранное: поиск ──
    if data == "search_favs":
        context.user_data['awaiting'] = 'fav_search'
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔍 Введите запрос для поиска в избранном (название или автор):"
        )
        return

    # ── Избранное: экспорт ──
    if data == "export_favs":
        await query.answer("📤 Готовлю файл...")
        await export_favorites(update, context)
        return

    # ── Полки ──
    if data.startswith("shelf_"):
        parts = data.split("_")
        if len(parts) >= 3:
            tag = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 1
            if tag == "all":
                context.user_data['fav_tag_filter'] = None
            else:
                context.user_data['fav_tag_filter'] = tag
            # Обновляем callback_data чтобы show_favorites получил правильную страницу
            query.data = f"show_favorites_{page}"
            await query.answer()
            await show_favorites(update, context)
        return

    # ── Повтор последнего поиска ──
    if data == "repeat_search":
        last = db.get_last_search(user_id)
        if not last:
            await query.answer("Нет предыдущих поисков", show_alert=True)
            return
        await query.answer(f"🔄 Повторяю поиск...")
        cmd = last['command']
        q = last['query']

        cache_key = f"{cmd}:{q}"
        books = _cache_get(cache_key)
        if books is None:
            if cmd == "author":
                raw = flib.scrape_books_by_author(q)
                if raw:
                    all_b = []
                    for group in raw:
                        all_b.extend(group)
                    unique = {}
                    for b in all_b:
                        unique.setdefault(b.id, b)
                    books = list(unique.values())
                else:
                    books = None
            elif cmd == "exact" and '|' in q:
                t, a = q.split('|', 1)
                books = flib.scrape_books_mbl(t.strip(), a.strip())
            else:
                books = flib.scrape_books_by_title(q)
            _cache_set(cache_key, books)

        if not books:
            try:
                await query.edit_message_text(f"😔 По запросу «{q}» ничего не найдено.")
            except Exception:
                pass
            return

        context.user_data['search_results'] = books
        context.user_data['search_results_original'] = list(books)
        context.user_data['search_type'] = cmd
        context.user_data['search_query'] = q
        context.user_data['current_results_page'] = 1
        await show_books_page(books, update, context, None, page=1)
        return

    # ── Дефолтный ответ для остальных навигационных веток ──
    await query.answer()

    if data.startswith("page_"):
        try:
            page = int(data.split("_")[1])
            books = context.user_data.get('search_results', [])
            if books:
                await show_books_page(books, update, context, None, page)
        except (ValueError, IndexError):
            pass
        return

    if data.startswith("book_"):
        book_id = data.split("_")[1]
        current_page = context.user_data.get('current_results_page', 1)
        _push_nav(context, {"type": "results", "page": current_page})
        await show_book_details_with_favorite(book_id, update, context)
        return

    if data.startswith("show_favorites_"):
        _push_nav(context, {"type": "main_menu"})
        await show_favorites(update, context)
        return

    if data.startswith("fav_book_"):
        book_id = data.split("_")[2]
        fav_page = context.user_data.get('current_favorites_page', 1)
        _push_nav(context, {"type": "favorites", "page": fav_page})
        await show_book_details_with_favorite(book_id, update, context)
        return

    if data == "main_menu":
        await show_main_menu(update, context)
        return

    if data == "menu_search":
        _push_nav(context, {"type": "main_menu"})
        await show_search_menu(update, context)
        return

    if data == "show_history":
        _push_nav(context, {"type": "main_menu"})
        await show_user_history(update, context)
        return

    if data == "show_my_stats":
        _push_nav(context, {"type": "main_menu"})
        await show_user_statistics(update, context)
        return

    if data == "show_settings":
        _push_nav(context, {"type": "main_menu"})
        await show_user_settings(update, context)
        return

    if data in ("back_to_results", "nav_back"):
        prev = _pop_nav(context)
        if prev:
            await _render_nav_entry(prev, update, context)
        else:
            await show_main_menu(update, context)
        return

    # Обработка старых callback'ов для обратной совместимости
    if " " in data:
        command, arg = data.split(" ", maxsplit=1)
        if command == "find_book_by_id":
            await show_book_details_with_favorite(arg, update, context)
        elif command == "get_book_by_format":
            if "+" in arg:
                book_id, book_format = arg.split("+", maxsplit=1)
                await get_book_by_format(book_id, book_format, update, context)


# ════════════════════════════════════════════════════════════
#                      MENU SCREENS
# ════════════════════════════════════════════════════════════

async def show_main_menu(update: Update, context: CallbackContext):
    """Показать главное меню (callback version)"""
    user_name = update.effective_user.first_name or "Книголюб"
    user_id = str(update.effective_user.id)
    context.user_data[_NAV_STACK_KEY] = []
    
    user_stats = db.get_user_stats(user_id)
    favorites_count = user_stats.get('favorites_count', 0)
    search_count = user_stats.get('user_info', {}).get('search_count', 0)
    download_count = user_stats.get('user_info', {}).get('download_count', 0)
    level = _get_user_level(search_count, download_count)
    
    text = f"""🏠 *Главное меню*

Привет, {_escape_md(user_name)}!  {level}

📊 Статистика:
• Поисков: {search_count}
• Скачиваний: {download_count}
• В избранном: {favorites_count}

{_next_level_info(search_count, download_count)}
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
        ],
    ]

    last = db.get_last_search(user_id)
    if last:
        q_short = last['query'][:20] + '…' if len(last['query']) > 20 else last['query']
        keyboard.append([
            InlineKeyboardButton(f"🔄 Повторить: «{q_short}»", callback_data="repeat_search")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await _safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_search_menu(update: Update, context: CallbackContext):
    """Показать меню поиска"""
    text = """
🔍 *Меню поиска*

Выберите способ поиска:

📖 По названию — найти книги по названию
👤 По автору — все книги автора
🎯 Точный поиск — название + автор
🆔 По ID — если знаете номер книги

Используйте команды:
• `/title название`
• `/author фамилия`
• `/exact название | автор`
• `/id номер`

💡 Или просто отправьте название книги текстом!
    """
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await _safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_history(update: Update, context: CallbackContext):
    """Показать историю поиска пользователя"""
    user_id = str(update.effective_user.id)
    history = db.get_user_search_history(user_id, limit=10)
    
    if not history:
        text = "📜 *История поиска*\n\nИстория пуста"
    else:
        text = "📜 *История поиска*\n\n"
        for item in history:
            timestamp = item['timestamp'][:16]
            command = item['command']
            q = item['query'][:30] + "…" if len(item['query']) > 30 else item['query']
            results = item['results_count']
            
            text += f"🕐 {timestamp}\n"
            text += f"   /{command}: «{_escape_md(q)}» ({results} рез.)\n\n"
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await _safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_statistics(update: Update, context: CallbackContext):
    """Показать статистику пользователя с уровнем достижений"""
    user_id = str(update.effective_user.id)
    stats = db.get_user_stats(user_id)
    
    user_info = stats.get('user_info', {})
    favorites_count = stats.get('favorites_count', 0)
    favorite_authors = stats.get('favorite_authors', [])
    search_count = user_info.get('search_count', 0)
    download_count = user_info.get('download_count', 0)
    level = _get_user_level(search_count, download_count)
    next_info = _next_level_info(search_count, download_count)
    
    text = f"""📊 *Ваша статистика*

🏆 Уровень: *{level}*
_{next_info}_

📅 Регистрация: {user_info.get('first_seen', 'Неизвестно')[:10]}
📅 Активность: {user_info.get('last_seen', 'Неизвестно')[:16]}

📈 *Активность:*
• Поисков: {search_count}
• Скачиваний: {download_count}
• В избранном: {favorites_count}

👤 *Любимые авторы:*
"""
    
    if favorite_authors:
        for i, author in enumerate(favorite_authors[:5], 1):
            text += f"{i}. {_escape_md(author['author'])} ({author['count']} книг)\n"
    else:
        text += "Пока нет данных\n"

    # Список всех уровней
    text += "\n🏆 *Уровни:*\n"
    for lvl in config.ACHIEVEMENT_LEVELS:
        marker = "▸" if lvl["name"] == level else "▹"
        text += f"{marker} {lvl['name']} — {lvl['searches']}+ поисков, {lvl['downloads']}+ скачиваний\n"
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await _safe_edit_or_send(update.callback_query, context, text, reply_markup)


async def show_user_settings(update: Update, context: CallbackContext):
    """Показать настройки пользователя"""
    user_id = str(update.effective_user.id)
    
    books_per_page = db.get_user_preference(user_id, 'books_per_page', config.BOOKS_PER_PAGE_DEFAULT)
    default_format = db.get_user_preference(user_id, 'default_format', 'fb2')
    kindle_email = db.get_user_preference(user_id, 'kindle_email', 'не задано')
    
    text = f"""⚙️ *Настройки*

📄 Книг на странице: {books_per_page}
📁 Формат по умолчанию: {default_format}
📧 Kindle email: {kindle_email}

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
            InlineKeyboardButton("MOBI", callback_data="set_format_mobi"),
            InlineKeyboardButton("PDF", callback_data="set_format_pdf"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="nav_back"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await _safe_edit_or_send(update.callback_query, context, text, reply_markup)


# ════════════════════════════════════════════════════════════
#                      TEXT COMMANDS
# ════════════════════════════════════════════════════════════

@check_access
async def favorites_command(update: Update, context: CallbackContext):
    """Команда для показа избранного"""
    context.user_data['fav_tag_filter'] = None
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
            q = item['query'][:30] + "…" if len(item['query']) > 30 else item['query']
            results = item['results_count']
            
            text += f"🕐 {timestamp}\n"
            text += f"   `/{command}`: «{_escape_md(q)}» ({results} рез.)\n\n"
    
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
            title = item['title'][:30] + "…" if len(item['title']) > 30 else item['title']
            author = item['author'][:20] + "…" if len(item['author']) > 20 else item['author']
            format_type = item['format']
            
            text += f"🕐 {timestamp}\n"
            text += f"   📖 {_escape_md(title)}\n"
            text += f"   ✍️ {_escape_md(author)}\n"
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
    search_count = user_info.get('search_count', 0)
    download_count = user_info.get('download_count', 0)
    level = _get_user_level(search_count, download_count)
    
    text = f"""📊 *Ваша статистика*

🏆 Уровень: *{level}*

👤 *Профиль:*
• ID: `{user_id}`
• Имя: {_escape_md(user_info.get('full_name', 'Неизвестно'))}

📅 *Даты:*
• Регистрация: {user_info.get('first_seen', 'Неизвестно')[:10]}
• Последняя активность: {user_info.get('last_seen', 'Неизвестно')[:16]}

📈 *Активность:*
• Поисков: {search_count}
• Скачиваний: {download_count}
• В избранном: {favorites_count}

👤 *Топ-5 любимых авторов:*
"""
    
    if favorite_authors:
        for i, author in enumerate(favorite_authors[:5], 1):
            text += f"{i}. {_escape_md(author['author'])} — {author['count']} книг\n"
    else:
        text += "Пока нет данных\n"
    
    text += "\n📚 *Последние скачивания:*\n"
    if recent_downloads:
        for download in recent_downloads[:3]:
            title = download['title'][:25] + "…" if len(download['title']) > 25 else download['title']
            text += f"• {_escape_md(title)}\n"
    else:
        text += "Пока нет скачиваний\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@check_access
async def settings_command(update: Update, context: CallbackContext):
    """Команда для показа настроек"""
    user_id = str(update.effective_user.id)
    
    books_per_page = db.get_user_preference(user_id, 'books_per_page', config.BOOKS_PER_PAGE_DEFAULT)
    default_format = db.get_user_preference(user_id, 'default_format', 'fb2')
    kindle_email = db.get_user_preference(user_id, 'kindle_email', 'не задано')
    
    text = f"""⚙️ *Настройки*

*Текущие параметры:*
📄 Книг на странице: `{books_per_page}`
📁 Формат по умолчанию: `{default_format}`
📧 Kindle email: `{kindle_email}`

*Команды для изменения:*
• `/setpage [5|10|20]` — книг на странице
• `/setformat [fb2|epub|mobi|pdf]` — формат по умолчанию
• `/setkindle email@kindle.com` — email Kindle
• `/clearkindle` — удалить email Kindle

*Примеры:*
`/setpage 20`
`/setformat epub`
`/setkindle name@kindle.com`
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
    if format_type not in config.ALL_FORMATS:
        await update.message.reply_text("❌ Некорректный формат. Используйте: fb2, epub, mobi, pdf, djvu")
        return
    
    db.set_user_preference(user_id, 'default_format', format_type)
    await update.message.reply_text(f"✅ Формат по умолчанию: {format_type.upper()}")


@check_access
async def setkindle_command(update: Update, context: CallbackContext):
    """Установить email для отправки на Kindle"""
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите email Kindle\n"
            "Пример: `/setkindle name@kindle.com`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    email = context.args[0].strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        await update.message.reply_text("❌ Некорректный email")
        return
    db.set_user_preference(user_id, 'kindle_email', email)
    await update.message.reply_text(f"✅ Kindle email установлен: {email}")


@check_access
async def clearkindle_command(update: Update, context: CallbackContext):
    """Удалить email Kindle"""
    user_id = str(update.effective_user.id)
    db.set_user_preference(user_id, 'kindle_email', '')
    await update.message.reply_text("✅ Kindle email удалён")


# ════════════════════════════════════════════════════════════
#                      ADMIN
# ════════════════════════════════════════════════════════════

@check_access
async def show_stats(update: Update, _: CallbackContext) -> None:
    """Показать общую статистику (только для админа)"""
    user_id = str(update.effective_user.id)
    
    if ALLOWED_USERS and user_id == ALLOWED_USERS[0]:
        stats = db.get_global_stats()
        
        stats_text = f"""📊 *Общая статистика бота*

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
            title = book['title'][:30] + "…" if len(book['title']) > 30 else book['title']
            stats_text += f"{i}. {_escape_md(title)} ({book['count']} скач.)\n"
        
        stats_text += "\n✍️ *Топ авторов:*\n"
        for i, author in enumerate(stats['top_authors'][:5], 1):
            name = author['author'][:25] + "…" if len(author['author']) > 25 else author['author']
            stats_text += f"{i}. {_escape_md(name)} ({author['count']} скач.)\n"
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ У вас нет прав для просмотра статистики")


@check_access
async def list_allowed_users(update: Update, _: CallbackContext) -> None:
    """Список разрешенных пользователей (только для админов)"""
    user_id = str(update.effective_user.id)
    
    if ALLOWED_USERS and user_id == ALLOWED_USERS[0]:
        if ALLOWED_USERS:
            users_info = []
            for uid in ALLOWED_USERS:
                user_data = db.get_user(uid)
                if user_data:
                    users_info.append(f"• {uid} — {_escape_md(user_data.get('full_name', 'Неизвестно'))}")
                else:
                    users_info.append(f"• {uid} — (не в БД)")
            
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


# ════════════════════════════════════════════════════════════
#                      JOBS & ERROR HANDLER
# ════════════════════════════════════════════════════════════

async def cleanup_job(context: CallbackContext):
    """Задача для очистки старых данных"""
    db.cleanup_old_data(days=30)
    flib.cleanup_old_files(days=30)
    logger.info("Database cleanup completed")


async def app_error_handler(update: object, context: CallbackContext) -> None:
    """Глобальный обработчик ошибок для PTB."""
    if context.error:
        _inc_error_stat(context, context.error)
    logger.error("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Произошла ошибка. Попробуйте позже."
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
#                      INLINE QUERY
# ════════════════════════════════════════════════════════════

async def inline_query(update: Update, context: CallbackContext) -> None:
    """Inline mode: быстрый поиск по названию."""
    # Проверка доступа для inline (нет update.message — нельзя ответить текстом)
    if ALLOWED_USERS:
        uid = str(update.effective_user.id)
        if uid not in ALLOWED_USERS:
            return

    query = update.inline_query.query.strip()
    if not query or len(query) < 3:
        return

    cache_key = f"inline:{query}"
    books = _cache_get(cache_key)
    if books is None:
        books = flib.scrape_books_by_title(query) or []
        _cache_set(cache_key, books)

    bot_username = context.bot.username or "bot"

    results = []
    for book in books[:10]:
        deep_link = f"https://t.me/{bot_username}?start=book_{book.id}"
        results.append(
            InlineQueryResultArticle(
                id=str(book.id),
                title=f"{book.title} — {book.author}",
                description=f"ID: {book.id}  •  {book.link}",
                input_message_content=InputTextMessageContent(
                    f"📖 *{_escape_md(book.title)}*\n"
                    f"✍️ _{_escape_md(book.author)}_\n\n"
                    f"🔗 [Открыть в боте]({deep_link})",
                    parse_mode=ParseMode.MARKDOWN,
                ),
            )
        )
    await update.inline_query.answer(results, cache_time=10)
