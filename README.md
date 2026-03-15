# Flibusta Telegram Bot

Telegram-бот для поиска книг на Flibusta и скачивания выбранного формата прямо в чат.

## Возможности

- Поиск по названию, автору, точный поиск и поиск по ID книги.
- Пагинация результатов и сортировка.
- Избранное с полками (`want`, `reading`, `done`, `recommend`).
- История поиска и история скачиваний.
- Inline mode для быстрого поиска из любого чата.

## Технологии

- Python 3.12
- `python-telegram-bot` 21.x (async)
- `requests` + `beautifulsoup4` + `lxml` для парсинга Flibusta
- SQLite (`sqlite3`)
- Docker / docker-compose

## Структура проекта

- `src/srv.py` — точка входа, регистрация хендлеров, запуск polling.
- `src/tg_bot.py` — callback-роутер, текстовые команды, admin, inline, jobs.
- `src/tg_bot_helpers.py` — общие утилиты, декораторы, async-обёртки.
- `src/tg_bot_views.py` — функции отображения экранов.
- `src/tg_bot_search.py` — поисковые команды.
- `src/tg_bot_favorites.py` — управление избранным.
- `src/tg_bot_download.py` — скачивание книг.
- `src/flib.py` — парсинг сайта и скачивание файлов.
- `src/database.py` — доступ к SQLite и SQL-операции.
- `src/config.py` — конфигурация и константы.
- `src/custom_logging.py` — JSON-логирование.
- `src/tg_bot_presentation.py` — форматирование текста/уровней.
- `src/tg_bot_ui.py` — UI-хелперы (breadcrumbs, screen, truncate).
- `src/tg_bot_nav.py` — навигационный стек.
- `src/tg_bot_cache.py` — in-memory TTL/LRU-кэш поиска.

## Быстрый старт (локально)

1. Установите Python 3.12+
2. Установите зависимости:

```bash
pip install -r requirements.txt
```

1. Создайте `.env`:

```env
TOKEN=your_bot_token_here
# Опционально:
# ALLOWED_USERS=12345,67890
# FLIBUSTA_SITE=http://flibusta.is
# TELEGRAM_PROXY=http://proxy:port
# DATA_DIR=./data
# BOOKS_DIR=./books
# LOGS_DIR=./logs
```

1. Запустите бота:

```bash
python src/srv.py
```

## Запуск в Docker

```bash
make build
make up
make logs
```

Остановка:

```bash
make down
```

## Основные команды

- `/start` — стартовое меню.
- `/help` — справка.
- `/title <название>` — поиск по названию.
- `/author <фамилия>` — поиск по автору.
- `/exact <название | автор>` — точный поиск.
- `/id <номер>` — карточка книги по ID.
- `/favorites` — избранное.
- `/history` — история поисков.
- `/downloads` — история скачиваний.
- `/mystats` — персональная статистика.
- `/settings` — настройки пользователя.
- `/setpage <5|10|20>` — книг на странице.
- `/setformat <fb2|epub|mobi|pdf|djvu>` — формат по умолчанию.

## Админ-команды

Если задан `ALLOWED_USERS`, первый ID в списке считается администратором:

- `/users`
- `/stats`

## Надежность и ограничения

- В проекте используется синхронный `sqlite3`, но вызовы БД/парсера из async-хендлеров выполняются через thread pool (`asyncio.to_thread`) для снижения блокировок event loop.
- Callback data в Telegram ограничена 64 байтами.
- Flibusta может отдавать нестабильные/медленные ответы, поэтому предусмотрены retry и таймауты.

## Development checklist

- Проверить поиск: `/title`, `/author`, `/exact`, `/id`.
- Проверить скачивание книги в нескольких форматах.
- Проверить добавление/удаление из избранного и полки.
- Проверить команды `/history`, `/downloads`, `/settings`.
- Проверить inline mode (минимум 3 символа).
- Проверить экран "ℹ️ Подробнее о книге" и возврат к карточке.
