import os
from datetime import time

from dotenv import load_dotenv

# Загружаем переменные окружения ДО импорта модулей,
# которые используют os.getenv() на уровне модуля (config, tg_bot и др.)
load_dotenv(".env")

from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, InlineQueryHandler,
)
from telegram.ext.filters import TEXT
from telegram.request import HTTPXRequest

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
    setkindle_command,
    clearkindle_command,
    cleanup_job,
    app_error_handler,
    inline_query,
)

from src import database as db


def main():
    # Инициализация базы данных
    db.init_database()
    print("[ OK ] База данных инициализирована")

    # Получаем токен
    token = os.getenv("TOKEN")
    if not token:
        print("[ERROR] ОШИБКА: Токен не найден в .env файле!")
        print("[INFO ] Добавьте строку: TOKEN=your_bot_token_here")
        return

    print(f"[KEY ] Токен: {token[:10]}...{token[-5:]}")

    # Настройка HTTPXRequest с увеличенными таймаутами
    proxy_url = os.getenv("TELEGRAM_PROXY")

    request_kwargs = {
        'connection_pool_size': 8,
        'connect_timeout': 20.0,
        'read_timeout': 20.0,
        'write_timeout': 20.0,
        'pool_timeout': 20.0,
    }

    if proxy_url:
        print(f"[NET ] Используется прокси: {proxy_url}")
        request_kwargs['proxy'] = proxy_url
    else:
        print("[NET ] Прямое подключение (без прокси)")

    request = HTTPXRequest(**request_kwargs)

    # Создаем приложение с настроенным request
    app = ApplicationBuilder() \
        .token(token) \
        .request(request) \
        .build()

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
    app.add_handler(CommandHandler("setkindle", setkindle_command))
    app.add_handler(CommandHandler("clearkindle", clearkindle_command))

    # ===== АДМИНИСТРАТИВНЫЕ КОМАНДЫ =====
    app.add_handler(CommandHandler("users", list_allowed_users))
    app.add_handler(CommandHandler("stats", show_stats))

    # ===== ОБРАБОТЧИКИ =====
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(TEXT, find_the_book))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_error_handler(app_error_handler)

    # ===== ЗАДАЧИ =====
    # Ежедневная очистка старых данных в 3:00
    job_queue = app.job_queue
    job_queue.run_daily(
        cleanup_job,
        time=time(hour=3, minute=0),
        name='cleanup_job',
    )

    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("=" * 50)
    print()
    print("КОМАНДЫ ПОИСКА:")
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
    print("АДМИН:")
    print("  /users               - список пользователей")
    print("  /stats               - общая статистика")
    print()
    print("Подсказка: начните с команды /start")
    print("=" * 50)
    print()

    # Запуск бота
    try:
        print("[CONN] Подключаемся к Telegram API...")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=['message', 'callback_query', 'inline_query'],
        )
    except KeyboardInterrupt:
        print("\n[STOP] Получен сигнал остановки (Ctrl+C)")
        print("[ OK ] Бот остановлен")
    except Exception as e:
        error_type = type(e).__name__
        print(f"\n[ERROR] ОШИБКА: {error_type}")
        print(f"        Детали: {str(e)}\n")

        if "TimedOut" in error_type or "ConnectTimeout" in error_type or "Timeout" in str(e):
            print("ВОЗМОЖНЫЕ РЕШЕНИЯ:")
            print("   1. Проверьте подключение к интернету")
            print("   2. Попробуйте увеличить таймауты")
            print("   3. Проверьте, не блокирует ли файрвол подключение")
            print("   4. Убедитесь, что api.telegram.org доступен:")
            print("      curl -I https://api.telegram.org")
        elif "Unauthorized" in error_type or "Unauthorized" in str(e):
            print("РЕШЕНИЕ:")
            print("   - Проверьте правильность токена бота в .env файле")
            print("   - Получите новый токен у @BotFather в Telegram")
        else:
            print("Для диагностики:")
            print("   - Проверьте логи выше")
            print("   - Убедитесь что TOKEN указан в .env")
            print("   - Проверьте права доступа к базе данных")

        print("\n" + "=" * 50)
        raise


if __name__ == "__main__":
    main()
