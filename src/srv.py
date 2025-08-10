import os
import asyncio
from datetime import time

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
    show_stats,
    favorites_command,
    history_command,
    downloads_command,
    mystats_command,
    settings_command,
    setpage_command,
    setformat_command,
    cleanup_job
)

from src import database as db


def main():
    load_dotenv(".env")
    
    # Инициализация базы данных
    db.init_database()
    print("✅ База данных инициализирована")

    app = ApplicationBuilder().token(os.getenv("TOKEN")).build()
    
    # ===== ОСНОВНЫЕ КОМАНДЫ =====
    app.add_handler(CommandHandler("start", start_callback))
    app.add_handler(CommandHandler("help", help_command))
    
    # ===== КОМАНДЫ ПОИСКА =====
    app.add_handler(CommandHandler("title", search_by_title))
    app.add_handler(CommandHandler("author", search_by_author))
    app.add_handler(CommandHandler("exact", search_exact))
    app.add_handler(CommandHandler("id", search_by_id))
    app.add_handler(CommandHandler("search", universal_search))
    
    # ===== ЛИЧНЫЙ КАБИНЕТ =====
    app.add_handler(CommandHandler("favorites", favorites_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("downloads", downloads_command))
    app.add_handler(CommandHandler("mystats", mystats_command))
    app.add_handler(CommandHandler("settings", settings_command))
    
    # ===== НАСТРОЙКИ =====
    app.add_handler(CommandHandler("setpage", setpage_command))
    app.add_handler(CommandHandler("setformat", setformat_command))
    
    # ===== АДМИНИСТРАТИВНЫЕ КОМАНДЫ =====
    app.add_handler(CommandHandler("users", list_allowed_users))
    app.add_handler(CommandHandler("stats", show_stats))
    
    # ===== ОБРАБОТЧИКИ =====
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(TEXT, find_the_book))
    
    # ===== ЗАДАЧИ =====
    # Ежедневная очистка старых данных в 3:00
    job_queue = app.job_queue
    job_queue.run_daily(
        cleanup_job,
        time=time(hour=3, minute=0),
        name='cleanup_job'
    )
    
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("=" * 50)
    print()
    print("📚 КОМАНДЫ ПОИСКА:")
    print("  /title <название>    - поиск по названию")  
    print("  /author <фамилия>    - поиск по автору")
    print("  /exact <назв | автор> - точный поиск")
    print("  /id <номер>          - поиск по ID")
    print("  /search              - универсальный поиск")
    print()
    print("⭐ ЛИЧНЫЙ КАБИНЕТ:")
    print("  /favorites           - избранные книги")
    print("  /history             - история поиска")
    print("  /downloads           - история скачиваний")
    print("  /mystats             - личная статистика")
    print("  /settings            - настройки")
    print()
    print("⚙️ НАСТРОЙКИ:")
    print("  /setpage <5|10|20>   - книг на странице")
    print("  /setformat <формат>  - формат по умолчанию")
    print()
    print("👨‍💼 АДМИН:")
    print("  /users               - список пользователей")
    print("  /stats               - общая статистика")
    print()
    print("💡 Подсказка: начните с команды /start")
    print("=" * 50)
    
    app.run_polling()


if __name__ == "__main__":
    main()
