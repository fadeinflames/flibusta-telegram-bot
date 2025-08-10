import requests
from bs4 import BeautifulSoup
import urllib.request
import urllib.parse
import os
import re
from typing import List, Optional, Dict
from dataclasses import dataclass, field
import time
from functools import lru_cache

ALL_FORMATS = ['fb2', 'epub', 'mobi', 'pdf', 'djvu']
SITE = 'http://flibusta.is'

# Добавляем таймаут и повторные попытки
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 1


@dataclass
class Book:
    """Класс для представления книги"""
    id: str
    title: str = ''
    author: str = ''
    link: str = ''
    formats: Dict[str, str] = field(default_factory=dict)
    cover: str = ''
    size: str = ''
    series: str = ''  # Добавляем серию
    year: str = ''    # Добавляем год
    
    def __str__(self):
        return f'{self.title} - {self.author} ({self.id})'
    
    def __eq__(self, other):
        if isinstance(other, Book):
            return self.id == other.id
        return False
    
    def __hash__(self):
        return hash(self.id)


def get_page(url: str, retries: int = MAX_RETRIES) -> Optional[BeautifulSoup]:
    """Получение страницы с повторными попытками"""
    for attempt in range(retries):
        try:
            r = urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT)
            html_bytes = r.read()
            html = html_bytes.decode("utf-8")
            return BeautifulSoup(html, "html.parser")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            else:
                raise e
    return None


def normalize_author_name(author: str) -> str:
    """Нормализация имени автора для поиска"""
    # Убираем лишние пробелы
    author = ' '.join(author.split())
    # Убираем специальные символы
    author = re.sub(r'[^\w\s-]', '', author, flags=re.UNICODE)
    return author.strip()


def scrape_books_by_title(text: str) -> Optional[List[Book]]:
    """Поиск книг только по названию"""
    query_text = urllib.parse.quote(text)
    url = f"{SITE}/booksearch?ask={query_text}&chb=on"
    
    try:
        sp = get_page(url)
        if not sp:
            return None
            
        target_div = sp.find('div', attrs={'class': 'clear-block', 'id': 'main'})
        if not target_div:
            return None
            
        target_ul_list = target_div.findChildren('ul', attrs={'class': ''})
        
        if len(target_ul_list) == 0:
            return None
        
        target_ul = target_ul_list[0]
        li_list = target_ul.find_all("li")
        
        result = []
        for li in li_list:
            # Получаем ID книги
            book_link = li.find('a')
            if not book_link:
                continue
                
            book_id = str(book_link.get('href')).replace('/b/', '')
            book = Book(book_id)
            
            # Название
            book.title = book_link.text
            
            # Ссылка
            book.link = SITE + book_link.get('href') + '/'
            
            # Автор(ы)
            author_links = li.find_all('a')[1:]  # Все ссылки кроме первой - авторы
            if author_links:
                authors = [a.text for a in author_links if '/a/' in a.get('href', '')]
                book.author = ', '.join(authors) if authors else '[автор не указан]'
            else:
                book.author = '[автор не указан]'
            
            # Дополнительная информация (размер, год и т.д.)
            text_content = li.get_text()
            # Пытаемся извлечь размер
            size_match = re.search(r'(\d+[KMГ])', text_content)
            if size_match:
                book.size = size_match.group(1)
            
            result.append(book)
        
        return result
        
    except Exception as e:
        print(f"Error in scrape_books_by_title: {e}")
        return None


def scrape_books_by_author(text: str) -> Optional[List[List[Book]]]:
    """Поиск всех книг конкретного автора"""
    # Нормализуем имя автора
    author_normalized = normalize_author_name(text)
    query_text = urllib.parse.quote(author_normalized)
    url = f"{SITE}/booksearch?ask={query_text}&cha=on"
    
    try:
        sp = get_page(url)
        if not sp:
            return None
            
        target_div = sp.find('div', attrs={'class': 'clear-block', 'id': 'main'})
        if not target_div:
            return None
            
        target_ul_list = target_div.findChildren('ul', attrs={'class': ''})
        
        if len(target_ul_list) == 0:
            return None
        
        target_ul = target_ul_list[0]
        li_list = target_ul.find_all("li")
        
        # Получаем ссылки на страницы авторов
        authors_links = []
        for li in li_list:
            author_link = li.find('a')
            if author_link:
                # Проверяем, что это действительно автор, а не что-то другое
                href = author_link.get('href', '')
                if '/a/' in href:
                    authors_links.append(SITE + href + '/')
        
        if not authors_links:
            return None
        
        final_res = []
        for author_link in authors_links:
            books = scrape_author_page(author_link)
            if books:
                final_res.append(books)
        
        return final_res
        
    except Exception as e:
        print(f"Error in scrape_books_by_author: {e}")
        return None


def scrape_author_page(author_url: str) -> Optional[List[Book]]:
    """Получение всех книг со страницы автора"""
    try:
        sp = get_page(author_url)
        if not sp:
            return None
        
        # Получаем имя автора
        author_h1 = sp.find("h1", attrs={"class": "title"})
        if not author_h1:
            return None
        author = author_h1.text.strip()
        
        # Находим форму с книгами
        target_form = sp.find('form', attrs={'method': 'POST'})
        if not target_form:
            return None
        
        # Исключаем переводы
        target_p_translates = target_form.find("h3", string='Переводы')
        if target_p_translates:
            sibling = target_p_translates.next_sibling
            while sibling:
                next_sibling = sibling.next_sibling
                sibling.extract()
                sibling = next_sibling
        
        # Находим все книги
        books_elements = target_form.find_all('svg')  # Или другой селектор
        if not books_elements:
            # Альтернативный способ поиска
            books_elements = target_form.find_all('input', attrs={'type': 'checkbox'})
        
        result = []
        for element in books_elements:
            # Находим ссылку на книгу
            book_link = element.find_next_sibling("a")
            if not book_link or '/b/' not in book_link.get('href', ''):
                continue
            
            book_id = str(book_link.get('href')).replace('/b/', '')
            book = Book(book_id)
            book.title = book_link.text.strip()
            book.author = author
            book.link = SITE + book_link.get('href') + '/'
            
            # Пытаемся получить дополнительную информацию
            parent = element.parent
            if parent:
                text = parent.get_text()
                # Размер
                size_match = re.search(r'(\d+[KMГ])', text)
                if size_match:
                    book.size = size_match.group(1)
                # Год
                year_match = re.search(r'\((\d{4})\)', text)
                if year_match:
                    book.year = year_match.group(1)
            
            result.append(book)
        
        return result
        
    except Exception as e:
        print(f"Error in scrape_author_page: {e}")
        return None


def scrape_books_mbl(title: str, author: str) -> Optional[List[Book]]:
    """Точный поиск по названию и автору"""
    title_q = urllib.parse.quote(title)
    author_q = urllib.parse.quote(normalize_author_name(author))
    url = f"{SITE}/makebooklist?ab=ab1&t={title_q}&ln={author_q}&sort=sd2"
    
    try:
        sp = get_page(url)
        if not sp:
            return None
            
        target_form = sp.find('form', attrs={'name': 'bk'})
        
        if target_form is None:
            return None
        
        div_list = target_form.find_all('div')
        
        result = []
        for d in div_list:
            # Находим ссылку на книгу
            book_link = d.find('a', attrs={'href': re.compile('/b/')})
            if not book_link:
                continue
            
            book_href = book_link.get('href')
            book_id = book_href.replace('/b/', '')
            
            book = Book(book_id)
            book.title = book_link.text.strip()
            book.link = SITE + book_href + '/'
            
            # Находим авторов
            author_links = d.find_all('a', attrs={'href': re.compile('/a/')})
            if author_links:
                authors = [a.text.strip() for a in author_links]
                book.author = ', '.join(authors[::-1])  # Реверсируем порядок
            else:
                book.author = '[автор не указан]'
            
            # Дополнительная информация
            text = d.get_text()
            size_match = re.search(r'(\d+[KMГ])', text)
            if size_match:
                book.size = size_match.group(1)
            
            result.append(book)
        
        return result
        
    except Exception as e:
        print(f"Error in scrape_books_mbl: {e}")
        return None


@lru_cache(maxsize=100)
def get_book_by_id(book_id: str) -> Optional[Book]:
    """Получение книги по ID с кешированием"""
    book = Book(book_id)
    book.link = f'{SITE}/b/{book_id}/'
    
    try:
        sp = get_page(book.link)
        if not sp:
            return None
            
        target_div = sp.find('div', attrs={'class': 'clear-block', 'id': 'main'})
        if not target_div:
            return None
        
        # Проверяем, что книга существует
        target_h1 = target_div.find('h1', attrs={'class': 'title'})
        if not target_h1:
            return None
            
        book.title = target_h1.text.strip()
        if book.title == "Книги":  # Страница не найдена
            return None
        
        # Размер
        size_span = sp.find('span', attrs={'style': 'size'})
        if size_span:
            book.size = size_span.text.strip()
        
        # Обложка
        target_img = target_div.find('img', attrs={'alt': 'Cover image'})
        if target_img:
            img_src = target_img.get('src')
            if img_src:
                book.cover = SITE + img_src if not img_src.startswith('http') else img_src
        
        # Форматы для скачивания
        format_links = target_div.find_all('a', string=re.compile(r'\(.*(?:fb2|epub|mobi|pdf|djvu)\)'))
        for a in format_links:
            format_text = a.text.strip()
            link = a.get('href')
            if link:
                full_link = SITE + link if not link.startswith('http') else link
                book.formats[format_text] = full_link
        
        # Автор
        author_link = target_h1.find_next('a')
        if author_link and '/a/' in author_link.get('href', ''):
            book.author = author_link.text.strip()
        else:
            book.author = '[автор не указан]'
        
        # Серия (если есть)
        series_link = sp.find('a', attrs={'href': re.compile('/sequence/')})
        if series_link:
            book.series = series_link.text.strip()
        
        return book
        
    except Exception as e:
        print(f"Error in get_book_by_id: {e}")
        return None


def download_book_cover(book: Book) -> bool:
    """Скачивание обложки книги"""
    if not book.cover:
        return False
    
    try:
        c_response = requests.get(book.cover, timeout=REQUEST_TIMEOUT)
        if not c_response.ok:
            return False
            
        c_full_path = os.path.join(os.getcwd(), "books", book.id, 'cover.jpg')
        os.makedirs(os.path.dirname(c_full_path), exist_ok=True)
        
        with open(c_full_path, "wb") as f:
            f.write(c_response.content)
        
        return True
        
    except Exception as e:
        print(f"Error downloading cover: {e}")
        return False


def download_book(book: Book, b_format: str) -> tuple[Optional[bytes], Optional[str]]:
    """Скачивание книги в указанном формате"""
    if b_format not in book.formats:
        return None, None
    
    book_url = book.formats[b_format]
    
    try:
        b_response = requests.get(book_url, timeout=30)  # Увеличиваем таймаут для больших файлов
        
        if not b_response.ok:
            return None, None
        
        # Получаем имя файла из заголовков
        content_disposition = b_response.headers.get('content-disposition', '')
        if content_disposition:
            # Извлекаем имя файла
            filename_match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition)
            if filename_match:
                b_filename = filename_match.group(1).replace('"', '').replace("'", '')
                # Убираем .zip если это fb2
                if b_filename.endswith('.fb2.zip'):
                    b_filename = b_filename.removesuffix('.zip')
            else:
                # Генерируем имя файла
                extension = b_format.replace('(', '').replace(')', '').split()[0]
                b_filename = f"{book.title} - {book.author}.{extension}"
        else:
            # Генерируем имя файла
            extension = b_format.replace('(', '').replace(')', '').split()[0]
            b_filename = f"{book.title} - {book.author}.{extension}"
        
        # Очищаем имя файла от недопустимых символов
        b_filename = re.sub(r'[<>:"/\\|?*]', '_', b_filename)
        
        return b_response.content, b_filename
        
    except requests.exceptions.Timeout:
        print(f"Timeout downloading book: {book_url}")
        return None, None
    except Exception as e:
        print(f"Error downloading book: {e}")
        return None, None


# Дополнительные утилиты для расширенного поиска
def search_books_advanced(
    title: Optional[str] = None,
    author: Optional[str] = None,
    year: Optional[str] = None,
    series: Optional[str] = None
) -> List[Book]:
    """
    Расширенный поиск книг с несколькими параметрами
    """
    results = []
    
    # Если указан только автор - ищем все его книги
    if author and not title:
        author_books = scrape_books_by_author(author)
        if author_books:
            for books_list in author_books:
                results.extend(books_list)
    
    # Если указано только название
    elif title and not author:
        title_books = scrape_books_by_title(title)
        if title_books:
            results.extend(title_books)
    
    # Если указаны и название, и автор
    elif title and author:
        exact_books = scrape_books_mbl(title, author)
        if exact_books:
            results.extend(exact_books)
    
    # Фильтрация по дополнительным параметрам
    if year and results:
        results = [book for book in results if year in book.year]
    
    if series and results:
        results = [book for book in results if series.lower() in book.series.lower()]
    
    # Убираем дубликаты
    unique_books = list({book.id: book for book in results}.values())
    
    return unique_books
