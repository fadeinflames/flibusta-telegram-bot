import os
import traceback
from urllib.error import HTTPError
from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from src import flib
from src.custom_logging import get_logger

logger = get_logger(__name__)

# Получаем список разрешенных пользователей из переменной окружения
# Формат в .env: ALLOWED_USERS=123456789,987654321,555666777
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')
ALLOWED_USERS = [user_id.strip() for user_id in ALLOWED_USERS if user_id.strip()]


def check_access(func):
    """Декоратор для проверки доступа пользователя"""
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)
        
        # Если список пустой, разрешаем всем (обратная совместимость)
        if not ALLOWED_USERS:
            return await func(update, context)
        
        # Проверяем, есть ли пользователь в списке разрешенных
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
        
        # Если список пустой, разрешаем всем (обратная совместимость)
        if not ALLOWED_USERS:
            return await func(update, context)
        
        # Проверяем, есть ли пользователь в списке разрешенных
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


@check_access
async def start_callback(update: Update, _: CallbackContext):
    await update.message.reply_text(
            "Введите название книги (без автора) ИЛИ добавьте фамилию автора на новой строке. \n"
            "\n"
            "Пример:\n"
            "\n"
            "1984\n"
            "Оруэлл"
    )


@check_access
async def find_the_book(update: Update, context: CallbackContext) -> None:
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
    mes = await update.message.reply_text("Подождите, идёт поиск...")

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
        await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
        await update.message.reply_text("Произошла ошибка на сервере.")
        print("Traceback full:")
        print(traceback.format_exc())
        logger.error(f"Access error {e}", extra={"exc": e})
        return

    if not libr:
        await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
        await update.message.reply_text("К сожалению, ничего не найдено =(")
        if err_author:
            await update.message.reply_text("Вероятно вместо фамилии автора на второй строке было указано что-то ещё")
    else:
        kbs = []
        kb = []
        for i in range(len(libr)):
            book = libr[i]
            text = f"{book.title} - {book.author}"
            callback_data = "find_book_by_id " + book.id
            kb.append([InlineKeyboardButton(text, callback_data=callback_data)])
            if len(kb) == 49:
                kbs.append(kb.copy())
                kb = []
        if kb:
            kbs.append(kb)

        await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
        for kb in kbs:
            reply_markup = InlineKeyboardMarkup(kb)
            await update.message.reply_text("Выберите книгу:", reply_markup=reply_markup)


@check_callback_access
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    command, arg = query.data.split(" ", maxsplit=1)
    if command == "find_book_by_id":
        await find_book_by_id(book_id=arg, update=update, context=context)
    if command == "get_book_by_format":
        await get_book_by_format(data=arg, update=update, context=context)


async def find_book_by_id(book_id, update: Update, context: CallbackContext):
    log_command = "find_book_by_id"
    log_user_id = update.effective_user.id
    log_user_name = update.effective_user.name
    log_user_full_name = update.effective_user.full_name
    log_search_string = book_id
    logger.info(
            msg="find the book",
            extra={
                "command": log_command,
                "user_id": log_user_id,
                "user_name": log_user_name,
                "user_full_name": log_user_full_name,
                "search_string": log_search_string,
            })

    mes = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Подождите, идёт загрузка..."
    )
    book = flib.get_book_by_id(book_id)
    capt = "\U0001F4D6 {title}\n\U0001F5E3 {author}\n\U0001FAB6 {size}\n\U0001F310 {url}".format(
            author=book.author, title=book.title, url=book.link, size=book.size,
    )

    kb = []
    for b_format in book.formats:
        text = b_format
        callback_data = f"get_book_by_format {book.id}+{b_format}"
        kb.append([InlineKeyboardButton(text, callback_data=callback_data)])
    reply_markup = InlineKeyboardMarkup(kb)

    if book.cover:
        flib.download_book_cover(book)
        c_full_path = os.path.join(os.getcwd(), "books", book_id, "cover.jpg")
        cover = open(os.path.join(c_full_path), "rb")
        await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=cover,
                caption=capt,
                reply_markup=reply_markup,
        )
    else:
        await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="[обложки нет]\n\n" + capt,
                reply_markup=reply_markup,
        )
    await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)


async def get_book_by_format(data: str, update: Update, context: CallbackContext):
    log_command = "get_book_by_format"
    log_user_id = update.effective_user.id
    log_user_name = update.effective_user.name
    log_user_full_name = update.effective_user.full_name
    logger.info(
            msg="get book by format",
            extra={
                "command": log_command,
                "user_id": log_user_id,
                "user_name": log_user_name,
                "user_full_name": log_user_full_name,
                "data": data,
            })

    mes = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Подождите, идёт скачивание..."
    )

    book_id, book_format = data.split("+")
    book = flib.get_book_by_id(book_id)

    b_content, b_filename = flib.download_book(book, book_format)

    if b_filename:
        await context.bot.send_document(chat_id=update.effective_chat.id, document=b_content, filename=b_filename)
        await context.bot.deleteMessage(chat_id=mes.chat_id, message_id=mes.message_id)
    else:
        logger.error(
                msg="download error",
                extra={
                    "command": log_command,
                    "user_id": log_user_id,
                    "user_name": log_user_name,
                    "user_full_name": log_user_full_name,
                    "data": data,
                })
        await context.bot.deleteMessage(
                chat_id=mes.chat_id, message_id=mes.message_id)
        await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла ошибка на сервере."
        )


@check_access
async def help_command(update: Update, _: CallbackContext) -> None:
    await update.message.reply_text("Нажмите /start чтобы начать")


# Команда для администратора для проверки списка разрешенных пользователей
@check_access
async def list_allowed_users(update: Update, _: CallbackContext) -> None:
    """Команда для отображения списка разрешенных пользователей (только для админов)"""
    user_id = str(update.effective_user.id)
    
    # Проверяем, является ли пользователь первым в списке (админом)
    if ALLOWED_USERS and user_id == ALLOWED_USERS[0]:
        if ALLOWED_USERS:
            users_list = "\n".join([f"• {user}" for user in ALLOWED_USERS])
            await update.message.reply_text(
                f"📋 Список разрешенных пользователей:\n\n{users_list}\n\n"
                f"Всего: {len(ALLOWED_USERS)} пользователей"
            )
        else:
            await update.message.reply_text("⚠️ Список разрешенных пользователей пуст. Доступ открыт для всех.")
    else:
        await update.message.reply_text("У вас нет прав для просмотра этой информации.")

