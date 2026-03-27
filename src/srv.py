import os
from datetime import time

from dotenv import load_dotenv

# Загружаем переменные окружения ДО импорта модулей,
# которые используют os.getenv() на уровне модуля (config, tg_bot и др.)
load_dotenv(".env")

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
)
from telegram.ext.filters import TEXT
from telegram.request import HTTPXRequest

from src import database as db
from src.rutracker_downloader import downloader as rt_downloader
from src.tg_bot import (
    app_error_handler,
    button,
    cancel_command,
    cleanup_job,
    downloads_command,
    favorites_command,
    find_the_book,
    help_command,
    history_command,
    inline_query,
    list_allowed_users,
    mystats_command,
    rt_admin_delete,
    rt_admin_delete_all,
    rt_admin_queue,
    rt_admin_stop,
    search_by_author,
    search_by_id,
    search_by_title,
    search_exact,
    setformat_command,
    setpage_command,
    settings_command,
    show_stats,
    start_callback,
    universal_search,
)
from src.tg_bot_rutracker import audiobook_search_command, listening_command, now_reading_command


def main():
    # Инициализация базы данных
    db.init_database()
    print("[ OK ] База данных инициализирована")

    # Reset downloads stuck in 'downloading' state from previous run
    stuck = db.rt_reset_stuck_downloads()
    if stuck:
        print(f"[ OK ] Сброшено {stuck} зависших загрузок RuTracker")

    # Получаем токен
    token = os.getenv("TOKEN")
    if not token:
        print("[ERROR] ОШИБКА: Токен не найден в .env файле!")
        print("[INFO ] Добавьте строку: TOKEN=your_bot_token_here")
        return

    print("[KEY ] Токен загружен из окружения")

    # Настройка HTTPXRequest с увеличенными таймаутами
    proxy_url = os.getenv("TELEGRAM_PROXY")

    request_kwargs = {
        "connection_pool_size": 8,
        "connect_timeout": 20.0,
        "read_timeout": 20.0,
        "write_timeout": 20.0,
        "pool_timeout": 20.0,
    }

    if proxy_url:
        print(f"[NET ] Используется прокси: {proxy_url}")
        request_kwargs["proxy"] = proxy_url
    else:
        print("[NET ] Прямое подключение (без прокси)")

    request = HTTPXRequest(**request_kwargs)

    # Создаем приложение с настроенным request
    app = ApplicationBuilder().token(token).request(request).build()

    # Фоновый загрузчик RuTracker
    rt_downloader.start(app)
    print("[ OK ] RuTracker downloader запущен")

    # ===== ОСНОВНЫЕ КОМАНДЫ =====
    app.add_handler(CommandHandler("start", start_callback))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # ===== КОМАНДЫ ПОИСКА =====
    app.add_handler(CommandHandler("title", search_by_title))
    app.add_handler(CommandHandler("author", search_by_author))
    app.add_handler(CommandHandler("exact", search_exact))
    app.add_handler(CommandHandler("id", search_by_id))
    app.add_handler(CommandHandler("search", universal_search))

    # ===== АУДИОКНИГИ =====
    app.add_handler(CommandHandler("audiobook", audiobook_search_command))
    app.add_handler(CommandHandler("listening", listening_command))
    app.add_handler(CommandHandler("now", now_reading_command))

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
    app.add_handler(CommandHandler("rtqueue", rt_admin_queue))
    app.add_handler(CommandHandler("rtstop", rt_admin_stop))
    app.add_handler(CommandHandler("rtdel", rt_admin_delete))
    app.add_handler(CommandHandler("rtdelall", rt_admin_delete_all))

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
        name="cleanup_job",
    )

    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("=" * 50)
    print()
    print("АУДИОКНИГИ (RuTracker):")
    print("  /audiobook <запрос>  - поиск аудиокниг на RuTracker")
    print("  /listening, /now     - что читаю / слушаю (прогресс + очередь)")
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
    print("  /rtqueue [N]         - очередь RuTracker")
    print("  /rtstop <id>         - отменить задачу RuTracker")
    print("  /rtdel <id>          - удалить задачу и файлы на диске")
    print("  /rtdelall            - очистить всю очередь RuTracker")
    print()
    print("Подсказка: начните с команды /start")
    print("=" * 50)
    print()

    # Запуск бота
    try:
        print("[CONN] Подключаемся к Telegram API...")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "inline_query"],
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
