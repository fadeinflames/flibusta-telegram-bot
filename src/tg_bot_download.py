"""Book download handlers."""

from telegram import Update
from telegram.ext import CallbackContext

from src import database as db
from src import flib
from src.custom_logging import get_logger
from src.tg_bot_helpers import book_from_cache, db_call, flib_call

logger = get_logger(__name__)


async def get_book_by_format(book_id: str, book_format: str, update: Update, context: CallbackContext):
    """Download a book in a specific format."""
    user_id = str(update.effective_user.id)

    logger.info(
        msg="get book by format",
        extra={
            "command": "get_book_by_format",
            "user_id": user_id,
            "user_name": update.effective_user.name,
            "book_id": book_id,
            "format": book_format,
        },
    )

    if update.callback_query:
        await update.callback_query.answer("⏳ Начинаю скачивание...")

    mes = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Подождите, скачиваю книгу...",
    )

    try:
        book = await book_from_cache(book_id)
        if not book:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Книга не найдена.",
            )
            return

        b_content, b_filename = await flib_call(flib.download_book, book, book_format)

        if b_content and b_filename:
            await db_call(db.add_download, user_id, book_id, book.title, book.author, book_format)

            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=b_content,
                filename=b_filename,
                caption=f"✅ Книга загружена!\n📖 {book.title}\n✍️ {book.author}",
            )
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        else:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Ошибка при скачивании книги.\nПопробуйте другой формат.",
            )
    except Exception as e:
        try:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        except Exception:
            pass
        logger.error(
            "Error downloading book",
            exc_info=e,
            extra={"user_id": user_id, "book_id": book_id, "format": book_format},
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка при скачивании книги.\nПопробуйте позже.",
        )


async def quick_download(book_id: str, update: Update, context: CallbackContext):
    """Quick download using the user's default format."""
    user_id = str(update.effective_user.id)
    default_fmt = await db_call(db.get_user_preference, user_id, "default_format", "fb2")

    if update.callback_query:
        await update.callback_query.answer(f"⏳ Скачиваю ({default_fmt})...")

    mes = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"⏳ Быстрое скачивание ({default_fmt})...",
    )

    try:
        book = await book_from_cache(book_id)
        if not book or not book.formats:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Книга не найдена или нет форматов.",
            )
            return

        selected = None
        for fmt_key in book.formats:
            if default_fmt in fmt_key.lower():
                selected = fmt_key
                break
        format_substituted = False
        if not selected:
            selected = next(iter(book.formats))
            format_substituted = True

        b_content, b_filename = await flib_call(flib.download_book, book, selected)
        if b_content and b_filename:
            await db_call(db.add_download, user_id, book_id, book.title, book.author, selected)
            caption = f"✅ {book.title}\n✍️ {book.author}"
            if format_substituted:
                actual_fmt = selected.strip("() ").upper()
                caption += f"\n\nℹ️ Формат {default_fmt.upper()} недоступен, скачан {actual_fmt}"
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=b_content,
                filename=b_filename,
                caption=caption,
            )
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        else:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Ошибка скачивания. Откройте карточку книги для выбора формата.",
            )
    except Exception as e:
        try:
            await context.bot.delete_message(chat_id=mes.chat_id, message_id=mes.message_id)
        except Exception:
            pass
        logger.error("Quick download error", exc_info=e)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка скачивания.",
        )
