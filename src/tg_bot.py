import os
import traceback
from urllib.error import HTTPError
from functools import wraps
from enum import Enum
import re
from datetime import datetime
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode

from src import flib
from src.custom_logging import get_logger

logger = get_logger(__name__)

# Получаем список разрешенных пользователей из переменной окружения
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')
ALLOWED_USERS = [user_id.strip() for user_id in ALLOWED_USERS if user_id.strip()]

# Статистика использования
usage_stats = defaultdict(int)
search_history = defaultdict(list)

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


async def quick_search_menu(update: Update, context: CallbackContext):
    """Меню быстрого поиска с популярными запросами"""
    quick_text = """
⚡ *Быстрый поиск*

Выберите популярную категорию или используйте команды поиска:
    """
    
    keyboard = [
        [
            InlineKeyboardButton("📚 Классика", callback_data="quick_classic"),
            InlineKeyboardButton("🔮 Фантастика", callback_data="quick_fantasy")
        ],
        [
            InlineKeyboardButton("🕵️ Детективы", callback_data="quick_detective"),
            InlineKeyboardButton("💕 Романы", callback_data="quick_romance")
        ],
        [
            InlineKeyboardButton("🧪 Научпоп", callback_data="quick_science"),
            InlineKeyboardButton("📜 История", callback_data="quick_history")
        ],
        [
            InlineKeyboardButton("◀️ Главное меню", callback_data="back_to_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        quick_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


@check_access
async def start_callback(update: Update, context: CallbackContext):
    """Главное меню с командами"""
    user_name = update.effective_user.first_name or "Книголюб"
    
    # Проверяем, передан ли аргумент (например, /start quick_search)
    if context.args and context.args[0] == "quick_search":
        await quick_search_menu(update, context)
        return
    
    help_text = f"""
👋 *Привет, {user_name}!*

📚 *Добро пожаловать в библиотеку Flibusta!*

━━━━━━━━━━━━━━━━━━━━━
*🔍 КОМАНДЫ ПОИСКА*
━━━━━━━━━━━━━━━━━━━━━

📖 /title `название` - поиск книги по названию
👤 /author `фамилия` - поиск всех книг автора
🎯 /exact `название | автор` - точный поиск книги
🆔 /id `номер` - получить книгу по ID
🔍 /search - универсальный поиск (старый интерфейс)

━━━━━━━━━━━━━━━━━━━━━
*📝 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ*
━━━━━━━━━━━━━━━━━━━━━

• `/title 1984` - найдет все книги с "1984" в названии
• `/author Оруэлл` - покажет все книги Джорджа Оруэлла
• `/exact 1984 | Оруэлл` - найдет именно "1984" Оруэлла
• `/id 123456` - получит книгу с ID 123456

━━━━━━━━━━━━━━━━━━━━━
*💡 ПОЛЕЗНЫЕ СОВЕТЫ*
━━━━━━━━━━━━━━━━━━━━━

✅ Используйте `/author` для просмотра всех книг автора
✅ Используйте `/exact` когда знаете и название, и автора
✅ Можно вводить только фамилию автора
✅ Поиск работает на русском и английском языках

━━━━━━━━━━━━━━━━━━━━━
*ℹ️ ДОПОЛНИТЕЛЬНО*
━━━━━━━━━━━━━━━━━━━━━

📋 /help - показать это меню снова
👥 /users - список пользователей (только для админа)

_Выберите нужную команду и начните поиск!_
    """
    
    # Добавляем интерактивные кнопки для быстрого доступа
    keyboard = [
        [
            InlineKeyboardButton("📖 Поиск по названию", callback_data="help_title"),
            InlineKeyboardButton("👤 Поиск по автору", callback_data="help_author")
        ],
        [
            InlineKeyboardButton("🎯 Точный поиск", callback_data="help_exact"),
            InlineKeyboardButton("🆔 Поиск по ID", callback_data="help_id")
        ],
        [
            InlineKeyboardButton("🔍 Универсальный поиск", callback_data="help_search")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


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
    
    # Сбор статистики
    user_id = str(update.effective_user.id)
    usage_stats['search_by_title'] += 1
    search_history[user_id].append({
        'type': 'title',
        'query': title,
        'timestamp': datetime.now()
    })
    
    logger.info(
        msg="search by title",
        extra={
            "command": "search_by_title",
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.name,
            "title": title,
        }
    )
    
    mes = await update.message.reply_text("🔍 Ищу книги по названию...")
    
    try:
        books = flib.scrape_books_by_title(title)
        
        if not books:
            await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 По запросу «{title}» ничего не найдено.\n"
                "Попробуйте изменить запрос или использовать другую команду."
            )
            return
        
        await show_books_list(books, update, context, mes, f"📚 Найдено книг по названию «{title}»: {len(books)}")
        
    except Exception as e:
        await handle_error(e, update, context, mes)


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
    
    logger.info(
        msg="search by author",
        extra={
            "command": "search_by_author", 
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.name,
            "author": author,
        }
    )
    
    mes = await update.message.reply_text("🔍 Ищу книги автора...")
    
    try:
        # Сначала пробуем точный поиск по автору
        authors_books = flib.scrape_books_by_author(author)
        
        if not authors_books:
            await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 Автор «{author}» не найден.\n"
                "Попробуйте:\n"
                "• Проверить правописание\n"
                "• Использовать только фамилию\n"
                "• Попробовать команду /search для более широкого поиска"
            )
            return
        
        # Объединяем все книги от всех найденных авторов
        all_books = []
        for author_books in authors_books:
            all_books.extend(author_books)
        
        # Убираем дубликаты по ID
        unique_books = {}
        for book in all_books:
            if book.id not in unique_books:
                unique_books[book.id] = book
        
        books_list = list(unique_books.values())
        
        # Сортируем по названию
        books_list.sort(key=lambda x: x.title)
        
        await show_books_list(
            books_list, 
            update, 
            context, 
            mes, 
            f"👤 Найдено книг автора «{author}»: {len(books_list)}"
        )
        
    except Exception as e:
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
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.name,
            "title": title,
            "author": author,
        }
    )
    
    mes = await update.message.reply_text("🔍 Выполняю точный поиск...")
    
    try:
        # Используем точный поиск по названию и автору
        books = flib.scrape_books_mbl(title, author)
        
        if not books:
            await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(
                f"😔 Книга «{title}» автора «{author}» не найдена.\n"
                "Попробуйте команды /title или /author для более широкого поиска."
            )
            return
        
        await show_books_list(
            books, 
            update, 
            context, 
            mes,
            f"🎯 Точный поиск: «{title}» - {author}\nНайдено: {len(books)}"
        )
        
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
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.name,
            "book_id": book_id,
        }
    )
    
    mes = await update.message.reply_text("🔍 Получаю информацию о книге...")
    
    try:
        book = flib.get_book_by_id(book_id)
        
        if not book:
            await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
            await update.message.reply_text(f"😔 Книга с ID {book_id} не найдена.")
            return
        
        await show_book_details(book, update, context, mes)
        
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


async def show_books_list(books, update: Update, context: CallbackContext, mes, header_text):
    """Отображение списка найденных книг"""
    if len(books) > 100:
        books = books[:100]
        header_text += "\n⚠️ Показаны первые 100 результатов"
    
    kbs = []
    kb = []
    
    for i, book in enumerate(books):
        # Сокращаем длинные названия
        title = book.title[:40] + "..." if len(book.title) > 40 else book.title
        author = book.author[:20] + "..." if len(book.author) > 20 else book.author
        
        text = f"{title} - {author}"
        callback_data = f"find_book_by_id {book.id}"
        kb.append([InlineKeyboardButton(text, callback_data=callback_data)])
        
        if len(kb) == 49:
            kbs.append(kb.copy())
            kb = []
    
    if kb:
        kbs.append(kb)
    
    await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
    
    # Отправляем заголовок
    await update.message.reply_text(header_text)
    
    # Отправляем кнопки
    for kb in kbs:
        reply_markup = InlineKeyboardMarkup(kb)
        await update.message.reply_text("Выберите книгу:", reply_markup=reply_markup)


async def show_book_details(book, update: Update, context: CallbackContext, mes):
    """Отображение деталей книги"""
    capt = (
        f"📖 *{book.title}*\n"
        f"✍️ _{book.author}_\n"
        f"📊 Размер: {book.size}\n"
        f"🔗 [Ссылка на сайт]({book.link})"
    )
    
    kb = []
    for b_format in book.formats:
        text = f"📥 Скачать {b_format}"
        callback_data = f"get_book_by_format {book.id}+{b_format}"
        kb.append([InlineKeyboardButton(text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(kb)
    
    if book.cover:
        try:
            flib.download_book_cover(book)
            c_full_path = os.path.join(os.getcwd(), "books", book.id, "cover.jpg")
            with open(c_full_path, "rb") as cover:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=cover,
                    caption=capt,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="[обложка недоступна]\n\n" + capt,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="[обложки нет]\n\n" + capt,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)


async def handle_error(error, update: Update, context: CallbackContext, mes):
    """Обработка ошибок"""
    await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
    await update.message.reply_text(
        "❌ Произошла ошибка при выполнении запроса.\n"
        "Попробуйте позже или используйте другую команду."
    )
    logger.error(f"Error occurred: {error}", extra={"exc": error})
    print("Traceback full:")
    print(traceback.format_exc())


@check_access
async def find_the_book(update: Update, context: CallbackContext) -> None:
    """Обработка текстовых сообщений (старый интерфейс)"""
    # Проверяем, не является ли это командой
    if update.message.text.startswith('/'):
        return
    
    if len(update.message.text.split('\n')) == 2:
        log_author = update.message.text.split('\n')[1]
    else:
        log_author = None
        
    logger.info(
        msg="find the book",
        extra={
            "command": "find_the_book",
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.name,
            "user_full_name": update.effective_user.full_name,
            "book_name": update.message.text.split('\n')[0],
            "author": log_author,
        }
    )

    search_string = update.message.text
    mes = await update.message.reply_text("🔍 Подождите, идёт поиск...")

    err_author = False
    try:
        libr = []
        if "\n" in search_string:
            title, author = search_string.split("\n", maxsplit=1)
            if len(author.split(" ")) > 1:
                err_author = True
            scr_lib = flib.scrape_books_mbl(title, author)
            if scr_lib:
                libr += scr_lib
        else:
            libr_t = flib.scrape_books_by_title(search_string)
            libr_a = flib.scrape_books_by_author(search_string)
            if libr_t:
                libr += libr_t
            if libr_a:
                libr += [book for nested_list in libr_a for book in nested_list]
        
        if search_string.isdigit():
            book_by_id = flib.get_book_by_id(search_string)
            if book_by_id:
                libr.append(book_by_id)

    except (AttributeError, HTTPError) as e:
        await handle_error(e, update, context, mes)
        return

    if not libr:
        await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
        await update.message.reply_text("😔 К сожалению, ничего не найдено")
        if err_author:
            await update.message.reply_text(
                "⚠️ Вероятно вместо фамилии автора на второй строке было указано что-то ещё"
            )
    else:
        await show_books_list(libr, update, context, mes, f"📚 Найдено результатов: {len(libr)}")


@check_callback_access
async def button(update: Update, context: CallbackContext) -> None:
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    # Обработка команд помощи
    if query.data.startswith("help_"):
        await handle_help_buttons(query, update, context)
        return

    # Обработка основных команд
    command, arg = query.data.split(" ", maxsplit=1)
    if command == "find_book_by_id":
        await find_book_by_id(book_id=arg, update=update, context=context)
    if command == "get_book_by_format":
        await get_book_by_format(data=arg, update=update, context=context)


async def handle_help_buttons(query, update: Update, context: CallbackContext):
    """Обработка кнопок помощи"""
    # Обработка кнопки "Назад к меню"
    if query.data == "back_to_menu":
        help_text = """
📚 *Добро пожаловать в библиотеку Flibusta!*

━━━━━━━━━━━━━━━━━━━━━
*🔍 КОМАНДЫ ПОИСКА*
━━━━━━━━━━━━━━━━━━━━━

📖 /title `название` - поиск книги по названию
👤 /author `фамилия` - поиск всех книг автора
🎯 /exact `название | автор` - точный поиск книги
🆔 /id `номер` - получить книгу по ID
🔍 /search - универсальный поиск (старый интерфейс)

━━━━━━━━━━━━━━━━━━━━━
*📝 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ*
━━━━━━━━━━━━━━━━━━━━━

• `/title 1984` - найдет все книги с "1984" в названии
• `/author Оруэлл` - покажет все книги Джорджа Оруэлла
• `/exact 1984 | Оруэлл` - найдет именно "1984" Оруэлла
• `/id 123456` - получит книгу с ID 123456

━━━━━━━━━━━━━━━━━━━━━
*💡 ПОЛЕЗНЫЕ СОВЕТЫ*
━━━━━━━━━━━━━━━━━━━━━

✅ Используйте `/author` для просмотра всех книг автора
✅ Используйте `/exact` когда знаете и название, и автора
✅ Можно вводить только фамилию автора
✅ Поиск работает на русском и английском языках

━━━━━━━━━━━━━━━━━━━━━
*ℹ️ ДОПОЛНИТЕЛЬНО*
━━━━━━━━━━━━━━━━━━━━━

📋 /help - показать это меню снова
👥 /users - список пользователей (только для админа)

_Выберите нужную команду и начните поиск!_
        """
        
        keyboard = [
            [
                InlineKeyboardButton("📖 Поиск по названию", callback_data="help_title"),
                InlineKeyboardButton("👤 Поиск по автору", callback_data="help_author")
            ],
            [
                InlineKeyboardButton("🎯 Точный поиск", callback_data="help_exact"),
                InlineKeyboardButton("🆔 Поиск по ID", callback_data="help_id")
            ],
            [
                InlineKeyboardButton("🔍 Универсальный поиск", callback_data="help_search")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return
    
    help_type = query.data.replace("help_", "")
    
    help_messages = {
        "title": (
            "📖 *Поиск по названию книги*\n\n"
            "*Формат:* `/title название книги`\n\n"
            "*Примеры:*\n"
            "• `/title Война и мир`\n"
            "• `/title 1984`\n"
            "• `/title Гарри Поттер`\n\n"
            "Эта команда найдет все книги, в названии которых есть указанный текст.\n\n"
            "_Совет: Можно вводить часть названия для более широкого поиска._"
        ),
        "author": (
            "👤 *Поиск по автору*\n\n"
            "*Формат:* `/author фамилия автора`\n\n"
            "*Примеры:*\n"
            "• `/author Толстой`\n"
            "• `/author Пушкин`\n"
            "• `/author Кинг`\n\n"
            "Эта команда покажет все книги указанного автора.\n\n"
            "_Совет: Достаточно ввести только фамилию автора._"
        ),
        "exact": (
            "🎯 *Точный поиск книги*\n\n"
            "*Формат:* `/exact название | автор`\n\n"
            "*Примеры:*\n"
            "• `/exact Война и мир | Толстой`\n"
            "• `/exact 1984 | Оруэлл`\n"
            "• `/exact Оно | Кинг`\n\n"
            "Эта команда выполнит точный поиск конкретной книги конкретного автора.\n\n"
            "_Важно: Используйте символ | для разделения названия и автора._"
        ),
        "id": (
            "🆔 *Поиск по ID*\n\n"
            "*Формат:* `/id номер`\n\n"
            "*Примеры:*\n"
            "• `/id 123456`\n"
            "• `/id 789012`\n\n"
            "Эта команда получит книгу по её уникальному идентификатору на сайте.\n\n"
            "_Совет: ID книги можно узнать из URL на сайте Flibusta._"
        ),
        "search": (
            "🔍 *Универсальный поиск*\n\n"
            "*Команда:* `/search`\n\n"
            "После ввода команды отправьте:\n"
            "• Только название книги\n"
            "• Или название на первой строке и автора на второй\n\n"
            "*Пример:*\n"
            "```\n"
            "1984\n"
            "Оруэлл\n"
            "```\n\n"
            "_Это старый способ поиска, рекомендуем использовать новые команды._"
        )
    }
    
    message = help_messages.get(help_type, "Неизвестная команда")
    
    # Добавляем кнопку "Назад к меню"
    keyboard = [[InlineKeyboardButton("◀️ Назад к меню", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def find_book_by_id(book_id, update: Update, context: CallbackContext):
    """Получение информации о книге по ID"""
    logger.info(
        msg="find book by id",
        extra={
            "command": "find_book_by_id",
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.name,
            "book_id": book_id,
        }
    )

    mes = await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="⏳ Подождите, загружаю информацию о книге..."
    )
    
    try:
        book = flib.get_book_by_id(book_id)
        
        if not book:
            await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Книга не найдена"
            )
            return
        
        await show_book_details(book, update, context, mes)
        
    except Exception as e:
        await handle_error(e, update, context, mes)


async def get_book_by_format(data: str, update: Update, context: CallbackContext):
    """Скачивание книги в выбранном формате"""
    logger.info(
        msg="get book by format",
        extra={
            "command": "get_book_by_format",
            "user_id": update.effective_user.id,
            "user_name": update.effective_user.name,
            "data": data,
        }
    )

    mes = await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="⏳ Подождите, скачиваю книгу..."
    )

    book_id, book_format = data.split("+")
    book = flib.get_book_by_id(book_id)

    b_content, b_filename = flib.download_book(book, book_format)

    if b_filename:
        await context.bot.send_document(
            chat_id=update.effective_chat.id, 
            document=b_content, 
            filename=b_filename,
            caption=f"✅ Книга успешно загружена!\n📖 {book.title}\n✍️ {book.author}"
        )
        await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
    else:
        logger.error(
            msg="download error",
            extra={
                "command": "get_book_by_format",
                "user_id": update.effective_user.id,
                "user_name": update.effective_user.name,
                "data": data,
            }
        )
        await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Произошла ошибка при скачивании книги.\nПопробуйте другой формат или повторите позже."
        )


@check_access
async def help_command(update: Update, context: CallbackContext) -> None:
    """Команда помощи"""
    await start_callback(update, context)


@check_access
async def show_stats(update: Update, _: CallbackContext) -> None:
    """Показать статистику использования бота (только для админа)"""
    user_id = str(update.effective_user.id)
    
    # Проверяем, является ли пользователь админом
    if ALLOWED_USERS and user_id == ALLOWED_USERS[0]:
        if not usage_stats:
            await update.message.reply_text("📊 Статистика пока пуста")
            return
        
        stats_text = "📊 *Статистика использования бота*\n\n"
        
        # Сортируем по популярности
        sorted_stats = sorted(usage_stats.items(), key=lambda x: x[1], reverse=True)
        
        stats_text += "*Топ команд:*\n"
        for i, (command, count) in enumerate(sorted_stats[:10], 1):
            stats_text += f"{i}. `{command}`: {count} раз\n"
        
        # Общая статистика
        total_searches = sum(usage_stats.values())
        unique_users = len(search_history)
        
        stats_text += f"\n*Общая информация:*\n"
        stats_text += f"• Всего поисков: {total_searches}\n"
        stats_text += f"• Уникальных пользователей: {unique_users}\n"
        stats_text += f"• Разрешенных пользователей: {len(ALLOWED_USERS)}\n"
        
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
            users_list = "\n".join([f"• {user}" for user in ALLOWED_USERS])
            await update.message.reply_text(
                f"📋 *Список разрешенных пользователей:*\n\n{users_list}\n\n"
                f"_Всего: {len(ALLOWED_USERS)} пользователей_",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("⚠️ Список разрешенных пользователей пуст. Доступ открыт для всех.")
    else:
        await update.message.reply_text("❌ У вас нет прав для просмотра этой информации.")
