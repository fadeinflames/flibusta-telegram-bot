import os

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler
from telegram.ext.filters import TEXT

from src.tg_bot import (
    start_callback, 
    button, 
    help_command, 
    find_the_book,
    search_by_title,
    search_by_author,
    search_exact,
    search_by_id,
    universal_search,
    list_allowed_users,
    show_stats  # Добавляем импорт новой функции
)


def main():
    load_dotenv(".env")

    app = ApplicationBuilder().token(os.getenv("TOKEN")).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start_callback))
    app.add_handler(CommandHandler("help", help_command))
    
    # Новые команды поиска
    app.add_handler(CommandHandler("title", search_by_title))
    app.add_handler(CommandHandler("author", search_by_author))
    app.add_handler(CommandHandler("exact", search_exact))
    app.add_handler(CommandHandler("id", search_by_id))
    app.add_handler(CommandHandler("search", universal_search))
    
    # Административные команды
    app.add_handler(CommandHandler("users", list_allowed_users))
    app.add_handler(CommandHandler("stats", show_stats))  # Добавляем команду статистики
    
    # Обработчики callback кнопок
    app.add_handler(CallbackQueryHandler(button))
    
    # Обработчик текстовых сообщений (для обратной совместимости)
    app.add_handler(MessageHandler(TEXT, find_the_book))

    print("🤖 Бот запущен и готов к работе!")
    print("📚 Доступные команды:")
    print("  /start - главное меню")
    print("  /title - поиск по названию")  
    print("  /author - поиск по автору")
    print("  /exact - точный поиск")
    print("  /id - поиск по ID")
    print("  /search - универсальный поиск")
    print("  /users - список пользователей (админ)")
    print("  /stats - статистика использования (админ)")
    
    app.run_polling()


if __name__ == "__main__":
    main()
