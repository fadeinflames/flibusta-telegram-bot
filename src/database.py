import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
import os

# Путь к базе данных
DB_PATH = os.path.join(os.getcwd(), 'flibusta_bot.db')


@contextmanager
def get_db():
    """Контекстный менеджер для работы с БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Для получения результатов как словарей
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Инициализация базы данных"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                search_count INTEGER DEFAULT 0,
                download_count INTEGER DEFAULT 0,
                is_admin BOOLEAN DEFAULT 0,
                preferences TEXT DEFAULT '{}',
                is_banned BOOLEAN DEFAULT 0
            )
        ''')
        
        # Таблица истории поиска
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                command TEXT,
                query TEXT,
                results_count INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица избранных книг
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                book_id TEXT,
                title TEXT,
                author TEXT,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                tags TEXT,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                UNIQUE(user_id, book_id)
            )
        ''')
        
        # Таблица скачанных книг
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                book_id TEXT,
                title TEXT,
                author TEXT,
                format TEXT,
                download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица кэша книг
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books_cache (
                book_id TEXT PRIMARY KEY,
                title TEXT,
                author TEXT,
                link TEXT,
                formats TEXT,
                cover TEXT,
                size TEXT,
                series TEXT,
                year TEXT,
                cached_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
        ''')
        
        # Таблица статистики
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE DEFAULT CURRENT_DATE,
                total_searches INTEGER DEFAULT 0,
                total_downloads INTEGER DEFAULT 0,
                unique_users INTEGER DEFAULT 0,
                popular_queries TEXT DEFAULT '[]',
                popular_books TEXT DEFAULT '[]'
            )
        ''')
        
        # Создаем индексы для оптимизации
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_history_timestamp ON search_history(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_downloads_book ON downloads(book_id)')
        
        conn.commit()


# Функции для работы с пользователями
def add_or_update_user(user_id: str, username: str = None, full_name: str = None, is_admin: bool = False):
    """Добавить или обновить пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, is_admin)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(?, username),
                full_name = COALESCE(?, full_name),
                last_seen = CURRENT_TIMESTAMP
        ''', (user_id, username, full_name, is_admin, username, full_name))
        conn.commit()


def get_user(user_id: str) -> Optional[Dict]:
    """Получить информацию о пользователе"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_user_stats(user_id: str, search: bool = False, download: bool = False):
    """Обновить статистику пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        if search:
            cursor.execute('''
                UPDATE users SET search_count = search_count + 1, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
        if download:
            cursor.execute('''
                UPDATE users SET download_count = download_count + 1, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
        conn.commit()


def set_user_preference(user_id: str, key: str, value: any):
    """Установить настройку пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT preferences FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            prefs = json.loads(row['preferences'] or '{}')
            prefs[key] = value
            cursor.execute('UPDATE users SET preferences = ? WHERE user_id = ?', 
                         (json.dumps(prefs), user_id))
            conn.commit()


def get_user_preference(user_id: str, key: str, default=None):
    """Получить настройку пользователя"""
    user = get_user(user_id)
    if user:
        prefs = json.loads(user['preferences'] or '{}')
        return prefs.get(key, default)
    return default


# Функции для работы с историей поиска
def add_search_history(user_id: str, command: str, query: str, results_count: int = 0):
    """Добавить запись в историю поиска"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO search_history (user_id, command, query, results_count)
            VALUES (?, ?, ?, ?)
        ''', (user_id, command, query, results_count))
        conn.commit()
        update_user_stats(user_id, search=True)


def get_user_search_history(user_id: str, limit: int = 10) -> List[Dict]:
    """Получить историю поиска пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM search_history 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]


# Функции для работы с избранным
def add_to_favorites(user_id: str, book_id: str, title: str, author: str, tags: str = None, notes: str = None):
    """Добавить книгу в избранное"""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO favorites (user_id, book_id, title, author, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, book_id, title, author, tags, notes))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Книга уже в избранном


def remove_from_favorites(user_id: str, book_id: str):
    """Удалить книгу из избранного"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM favorites WHERE user_id = ? AND book_id = ?', (user_id, book_id))
        conn.commit()
        return cursor.rowcount > 0


def get_user_favorites(user_id: str, offset: int = 0, limit: int = 10) -> Tuple[List[Dict], int]:
    """Получить избранное пользователя с пагинацией"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем общее количество
        cursor.execute('SELECT COUNT(*) as total FROM favorites WHERE user_id = ?', (user_id,))
        total = cursor.fetchone()['total']
        
        # Получаем страницу
        cursor.execute('''
            SELECT * FROM favorites 
            WHERE user_id = ? 
            ORDER BY added_date DESC 
            LIMIT ? OFFSET ?
        ''', (user_id, limit, offset))
        
        favorites = [dict(row) for row in cursor.fetchall()]
        return favorites, total


def is_favorite(user_id: str, book_id: str) -> bool:
    """Проверить, есть ли книга в избранном"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM favorites WHERE user_id = ? AND book_id = ?', (user_id, book_id))
        return cursor.fetchone() is not None


def update_favorite_notes(user_id: str, book_id: str, notes: str):
    """Обновить заметки к книге в избранном"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE favorites SET notes = ? 
            WHERE user_id = ? AND book_id = ?
        ''', (notes, user_id, book_id))
        conn.commit()


# Функции для работы со скачиваниями
def add_download(user_id: str, book_id: str, title: str, author: str, format: str):
    """Добавить запись о скачивании"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO downloads (user_id, book_id, title, author, format)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, book_id, title, author, format))
        conn.commit()
        update_user_stats(user_id, download=True)


def get_user_downloads(user_id: str, limit: int = 10) -> List[Dict]:
    """Получить историю скачиваний пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM downloads 
            WHERE user_id = ? 
            ORDER BY download_date DESC 
            LIMIT ?
        ''', (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]


# Функции для работы с кэшем книг
def cache_book(book):
    """Закэшировать информацию о книге"""
    with get_db() as conn:
        cursor = conn.cursor()
        formats_json = json.dumps(book.formats)
        cursor.execute('''
            INSERT OR REPLACE INTO books_cache 
            (book_id, title, author, link, formats, cover, size, series, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (book.id, book.title, book.author, book.link, formats_json, 
              book.cover, book.size, book.series, book.year))
        conn.commit()


def get_cached_book(book_id: str) -> Optional[Dict]:
    """Получить книгу из кэша"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE books_cache 
            SET access_count = access_count + 1 
            WHERE book_id = ?
        ''', (book_id,))
        cursor.execute('SELECT * FROM books_cache WHERE book_id = ?', (book_id,))
        row = cursor.fetchone()
        if row:
            book_dict = dict(row)
            book_dict['formats'] = json.loads(book_dict['formats'])
            return book_dict
        return None


# Функции для статистики
def get_global_stats() -> Dict:
    """Получить глобальную статистику"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Общее количество пользователей
        cursor.execute('SELECT COUNT(*) as total_users FROM users')
        total_users = cursor.fetchone()['total_users']
        
        # Активные пользователи за последние 7 дней
        cursor.execute('''
            SELECT COUNT(*) as active_users FROM users 
            WHERE last_seen > datetime('now', '-7 days')
        ''')
        active_users = cursor.fetchone()['active_users']
        
        # Общее количество поисков
        cursor.execute('SELECT COUNT(*) as total_searches FROM search_history')
        total_searches = cursor.fetchone()['total_searches']
        
        # Общее количество скачиваний
        cursor.execute('SELECT COUNT(*) as total_downloads FROM downloads')
        total_downloads = cursor.fetchone()['total_downloads']
        
        # Общее количество книг в избранном
        cursor.execute('SELECT COUNT(*) as total_favorites FROM favorites')
        total_favorites = cursor.fetchone()['total_favorites']
        
        # Топ команд
        cursor.execute('''
            SELECT command, COUNT(*) as count 
            FROM search_history 
            GROUP BY command 
            ORDER BY count DESC 
            LIMIT 5
        ''')
        top_commands = [dict(row) for row in cursor.fetchall()]
        
        # Топ книг
        cursor.execute('''
            SELECT book_id, title, author, COUNT(*) as count 
            FROM downloads 
            GROUP BY book_id 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_books = [dict(row) for row in cursor.fetchall()]
        
        # Топ авторов
        cursor.execute('''
            SELECT author, COUNT(*) as count 
            FROM downloads 
            GROUP BY author 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_authors = [dict(row) for row in cursor.fetchall()]
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'total_searches': total_searches,
            'total_downloads': total_downloads,
            'total_favorites': total_favorites,
            'top_commands': top_commands,
            'top_books': top_books,
            'top_authors': top_authors
        }


def get_user_stats(user_id: str) -> Dict:
    """Получить статистику пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        user = get_user(user_id)
        if not user:
            return {}
        
        # Количество книг в избранном
        cursor.execute('SELECT COUNT(*) as favorites_count FROM favorites WHERE user_id = ?', (user_id,))
        favorites_count = cursor.fetchone()['favorites_count']
        
        # Последние поиски
        recent_searches = get_user_search_history(user_id, limit=5)
        
        # Последние скачивания
        recent_downloads = get_user_downloads(user_id, limit=5)
        
        # Любимые авторы
        cursor.execute('''
            SELECT author, COUNT(*) as count 
            FROM downloads 
            WHERE user_id = ? 
            GROUP BY author 
            ORDER BY count DESC 
            LIMIT 5
        ''', (user_id,))  # Исправлено: добавлен параметр user_id
        favorite_authors = [dict(row) for row in cursor.fetchall()]
        
        return {
            'user_info': user,
            'favorites_count': favorites_count,
            'recent_searches': recent_searches,
            'recent_downloads': recent_downloads,
            'favorite_authors': favorite_authors
        }


# Функции очистки старых данных
def cleanup_old_data(days: int = 30):
    """Очистить старые данные"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Удаляем старую историю поиска
        cursor.execute('''
            DELETE FROM search_history 
            WHERE timestamp < datetime('now', '-' || ? || ' days')
        ''', (days,))
        
        # Удаляем старый кэш книг, которые не использовались
        cursor.execute('''
            DELETE FROM books_cache 
            WHERE cached_date < datetime('now', '-' || ? || ' days')
            AND access_count < 2
        ''', (days,))
        
        conn.commit()


# Инициализация при импорте модуля
if __name__ != "__main__":
    init_database()
