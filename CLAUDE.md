# CLAUDE.md — Архитектура и важные факты о проекте

## Обзор

Telegram-бот для поиска и скачивания книг с сайта Flibusta. Написан на Python 3.12, использует библиотеку `python-telegram-bot` v21+ (async). Запускается в Docker-контейнере.

## Структура проекта

```
src/
├── srv.py          — Точка входа. Загружает .env, инициализирует БД, регистрирует хэндлеры, запускает polling.
├── config.py       — Все константы и настройки (сайт, таймауты, пагинация, уровни достижений, полки).
├── flib.py         — Скрапинг Flibusta: поиск книг, получение деталей, скачивание файлов/обложек.
├── database.py     — SQLite через sqlite3 (синхронный). Пользователи, история, избранное, скачивания, кэш книг.
├── tg_bot.py       — Логика бота: команды, callback-обработчик, UI, пагинация, навигация.
├── tg_bot_presentation.py — Вспомогательные функции форматирования (Markdown, уровни, полки).
├── tg_bot_ui.py    — UI-хелперы экранов (breadcrumbs, screen, truncate).
├── tg_bot_nav.py   — Управление навигационным стеком.
└── custom_logging.py — JSON-логирование с RotatingFileHandler (10 МБ × 5 файлов).
```

## Ключевые архитектурные решения

### Точка входа (`src/srv.py`)

- `load_dotenv(".env")` вызывается **до** любых импортов модулей, использующих `os.getenv()` на уровне модуля (config, tg_bot).
- `db.init_database()` вызывается синхронно в `main()` до запуска бота.
- `HTTPXRequest` настраивается с пулом соединений (8) и таймаутами 20 сек.
- Поддержка прокси через переменную окружения `TELEGRAM_PROXY`.
- Ежедневная задача `cleanup_job` запускается в 03:00 через `job_queue.run_daily()`.

### База данных (`src/database.py`)

- **Синхронный** `sqlite3` (не aiosqlite). Все функции — обычные (не `async`).
- `get_db()` — контекстный менеджер, каждый вызов открывает/закрывает соединение.
- WAL-режим включается при инициализации (`PRAGMA journal_mode=WAL`).
- Миграции встроены в `init_database()`: добавление новых колонок через `ALTER TABLE` с `try/except sqlite3.OperationalError`.
- Пользовательские настройки хранятся как JSON-строка в колонке `preferences` таблицы `users`.
- Теги (полки) в `favorites.tags` — это **простая строка** (ключ из `config.FAVORITE_SHELVES`), **не JSON-массив**.

#### Таблицы

| Таблица | Назначение |
|---|---|
| `users` | Пользователи, статистика, настройки (preferences JSON) |
| `search_history` | История поисковых запросов |
| `favorites` | Избранные книги (UNIQUE на user_id + book_id) |
| `downloads` | История скачиваний |
| `books_cache` | Кэш информации о книгах (аннотация, жанры, форматы и т.д.) |
| `statistics` | Агрегированная статистика (не используется активно) |

### Скрапинг (`src/flib.py`)

- Глобальный `requests.Session` с retry-стратегией (3 попытки, backoff 1.0 сек, статусы 429/5xx).
- In-memory LRU-кэш страниц (`_PAGE_CACHE`, OrderedDict, TTL 300 сек, макс. 128 записей).
- `Book` — dataclass с полями: `id`, `title`, `author`, `link`, `formats` (dict), `cover`, `size`, `series`, `year`, `annotation`, `genres` (list), `rating`, `author_link`.
- `formats` — dict, где ключ = текстовое представление формата (например `"(fb2)"`), значение = URL для скачивания.
- Скачивание: запрос идёт на `{SITE}/b/{id}/epub` (или другой формат). Для epub/mobi и др. Flibusta может делать **редирект на `https://static.flibusta.is`** (конвертер). Ошибки соединения часто возникают именно при обращении к static.flibusta.is; при сбое в лог пишется `resolved_url` — финальный URL после редиректа.

#### Методы поиска

| Функция | URL Flibusta | Что ищет |
|---|---|---|
| `scrape_books_by_title(text)` | `/booksearch?ask=...&chb=on` | Книги по названию |
| `scrape_books_by_author(text)` | `/booksearch?ask=...&cha=on` | Авторов → их книги |
| `scrape_books_mbl(title, author)` | `/makebooklist?ab=ab1&t=...&ln=...&sort=sd2` | Точный поиск |
| `get_book_by_id(book_id)` | `/b/{book_id}/` | Детали книги |
| `get_other_books_by_author(url)` | Страница автора | Другие книги автора |

- `scrape_books_by_author` возвращает `list[list[Book]]` (список авторов → список книг каждого).
- `get_book_by_id` парсит аннотацию тремя способами (заголовок "Аннотация", div.content, все `<p>`), жанры через `/g/`, серию через `/sequence/`.

### Бот (`src/tg_bot.py`)

#### Контроль доступа

- `ALLOWED_USERS` загружается из env `ALLOWED_USERS` (через запятую). Если пустой — доступ открыт для всех.
- Первый пользователь в списке считается **администратором** (доступ к `/stats`, `/users`).
- Три декоратора:
  - `@check_access` — для команд (через `update.message`).
  - `@check_callback_access` — для callback queries.
  - `@rate_limit(sec)` — rate-limiting по `context.user_data`.

#### Markdown

- Используется **`ParseMode.MARKDOWN`** (v1), **не** MarkdownV2.
- `_escape_md()` экранирует только `_`, `*`, `` ` ``, `[` (символы Markdown v1).

#### Навигация

- Навигационный стек в `context.user_data["nav_stack"]` (макс. 10 записей).
- `_push_nav` / `_pop_nav` / `_render_nav_entry` — управление "назад".
- Типы записей: `results`, `favorites`, `history`, `stats`, `settings`, `search_menu`, `main_menu`.

#### In-memory кэш поиска

- `_SEARCH_CACHE` — dict с TTL (`config.SEARCH_CACHE_TTL_SEC` = 120 сек, макс. 256 записей).
- Ключи: `title:запрос`, `author:запрос`, `exact:title|author`, `inline:запрос`.

#### Callback data протокол

| Паттерн | Действие |
|---|---|
| `book_{id}` | Открыть карточку книги |
| `page_{n}` | Страница результатов |
| `toggle_favorite_{id}` | Добавить/удалить из избранного |
| `get_book_by_format_{id}\|{url_encoded_format}` | Скачать в формате |
| `qd_{id}` | Быстрое скачивание (формат по умолчанию) |
| `pick_shelf_{id}` | Выбор полки |
| `set_tag_{id}_{tag}` | Установить полку |
| `book_meta_{id}` | Показать подробные метаданные книги |
| `full_ann_{id}` | Показать полную аннотацию |
| `author_books_{id}` | Другие книги автора |
| `sort_title` / `sort_author` / `sort_default` | Сортировка результатов |
| `show_favorites_{page}` | Страница избранного |
| `fav_book_{id}` | Книга из избранного |
| `shelf_{tag}_{page}` | Полка в избранном |
| `search_favs` | Поиск в избранном (ожидает текстовый ввод) |
| `export_favs` | Экспорт избранного в .txt |
| `set_per_page_{n}` | Настройка пагинации |
| `set_format_{fmt}` | Формат по умолчанию |
| `repeat_search` | Повтор последнего поиска |
| `main_menu` / `menu_search` / `show_history` / `show_my_stats` / `show_settings` | Навигация |
| `nav_back` / `back_to_results` | Назад по стеку |

#### Deep Linking

- `/start book_{id}` — открывает карточку книги (для шаринга через URL `t.me/bot?start=book_123`).

#### Пользовательские настройки

- `books_per_page` — 5, 10 или 20 (дефолт 10).
- `default_format` — формат скачивания по умолчанию (дефолт `fb2`).

#### Уровни достижений

Определяются по количеству поисков и скачиваний (`config.ACHIEVEMENT_LEVELS`):
📖 Новичок → 📚 Читатель → 📕 Библиофил → 🏛 Книгочей → 🎓 Эрудит → 👑 Мастер.

#### Полки для избранного

Предустановленные полки (`config.FAVORITE_SHELVES`):
- `want` — 📕 Хочу прочитать
- `reading` — 📗 Читаю
- `done` — 📘 Прочитано
- `recommend` — 📙 Рекомендую

## Переменные окружения

| Переменная | Описание | Обязательна |
|---|---|---|
| `TOKEN` | Токен Telegram бота | ✅ |
| `ALLOWED_USERS` | ID пользователей через запятую | ❌ (без неё доступ для всех) |
| `FLIBUSTA_SITE` | URL сайта Flibusta | ❌ (по умолчанию `http://flibusta.is`) |
| `TELEGRAM_PROXY` | URL прокси для Telegram API | ❌ |
| `DATA_DIR` | Директория для БД | ❌ (по умолчанию `./data`) |
| `BOOKS_DIR` | Директория для обложек | ❌ (по умолчанию `./books`) |
| `LOGS_DIR` | Директория для логов | ❌ (по умолчанию `./logs`) |

## Docker

- Образ на базе `python:3.12-slim`.
- `PYTHONPATH=/srv`, рабочая директория `/srv`.
- Три volume: `/srv/books`, `/srv/logs`, `/srv/data`.
- Entrypoint: `python src/srv.py`.
- `docker-compose.yml` монтирует `./books`, `./logs`, `./data` в контейнер.

## Важные особенности

1. **Все функции БД и парсера — синхронные.** В async-хэндлерах они вызываются через `asyncio.to_thread`, чтобы не блокировать event loop.
2. **`_book_from_cache` — async-обёртка** над синхронным кэшем/парсером; при промахе кэша может вызвать HTTP-запрос к Flibusta.
3. **Callback data ограничена 64 байтами** (лимит Telegram). Формат книги URL-кодируется и передаётся через `|` разделитель.
4. **Ошибки при редактировании сообщений** (например, если предыдущее сообщение было фото) обрабатываются через `_safe_edit_or_send` — удаляет старое и шлёт новое.
5. **Обложки** скачиваются в `{BOOKS_DIR}/{book_id}/cover.jpg` и удаляются по cron-задаче через 30 дней.
6. **Inline mode** поддерживает быстрый поиск по названию (минимум 3 символа), результаты кэшируются 10 секунд на стороне Telegram.

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Приветствие + deep linking |
| `/help` | Справка |
| `/title <название>` | Поиск по названию |
| `/author <фамилия>` | Поиск по автору |
| `/exact <назв \| автор>` | Точный поиск |
| `/id <номер>` | Книга по ID |
| `/search` | Подсказка по поиску |
| `/favorites` | Избранное |
| `/history` | История поиска |
| `/downloads` | История скачиваний |
| `/mystats` | Личная статистика |
| `/settings` | Настройки |
| `/setpage <5\|10\|20>` | Книг на странице |
| `/setformat <формат>` | Формат по умолчанию |
| `/users` | Список пользователей (админ) |
| `/stats` | Общая статистика (админ) |

## Зависимости

- `python-telegram-bot[job-queue]` ^21.9 — Telegram Bot API
- `python-dotenv` — загрузка .env
- `requests` — HTTP-клиент для Flibusta
- `beautifulsoup4` + `lxml` — парсинг HTML
- `json-log-formatter` — JSON-логирование
