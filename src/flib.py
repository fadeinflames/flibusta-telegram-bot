import requests
from bs4 import BeautifulSoup
import urllib.request
import urllib.parse
import os
import re

ALL_FORMATS = ['fb2', 'epub', 'mobi', 'pdf', 'djvu']
SITE = 'http://flibusta.is'


class Book:
    def __init__(self, book_id):
        self.id = book_id
        self.title = ''
        self.author = ''
        self.link = ''
        self.formats = {}
        self.cover = ''
        self.size = ''
        self.series = ''  # Добавлено
        self.year = ''    # Добавлено

    def __str__(self):
        return f'{self.title} - {self.author} ({self.id})'

def get_page(url):
    """Получение страницы"""
    try:
        # Используем requests для единообразия и лучшей обработки ошибок
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return soup
    except (requests.exceptions.RequestException, Exception) as e:
        return None


def scrape_books_by_title(text: str) -> list[Book] | None:
    """Поиск книг по названию"""
    query_text = urllib.parse.quote(text)
    url = f"http://flibusta.is/booksearch?ask={query_text}&chb=on"

    sp = get_page(url)
    if not sp:
        return None

    target_div = sp.find('div', attrs={'class': 'clear-block', 'id': 'main'})
    if not target_div:
        target_div = sp.find('div', id='main')
        if not target_div:
            return None

    # Ищем все ul списки
    target_ul_list = target_div.find_all('ul')
    
    if len(target_ul_list) == 0:
        return None

    result = []
    
    # Проходим по всем спискам
    for target_ul in target_ul_list:
        # Пропускаем списки с классами (обычно это навигация)
        if target_ul.get('class'):
            continue
            
        li_list = target_ul.find_all("li")
        
        for li in li_list:
            # Получаем все ссылки в элементе
            all_links = li.find_all('a')
            if not all_links:
                continue
            
            # Первая ссылка должна быть на книгу
            first_link = all_links[0]
            href = first_link.get('href', '')
            
            # Проверяем, что это ссылка на книгу
            if not href.startswith('/b/'):
                continue
            
            book_id = href.replace('/b/', '')
            book = Book(book_id)
            book.title = first_link.text.strip()
            book.link = SITE + href + '/'
            
            # Собираем авторов (остальные ссылки)
            authors = []
            for link in all_links[1:]:
                link_href = link.get('href', '')
                if link_href.startswith('/a/'):
                    authors.append(link.text.strip())
            
            book.author = ', '.join(authors) if authors else '[автор не указан]'
            result.append(book)
    
    return result if result else None


def scrape_books_by_author(text: str) -> list[list[Book]] | None:
    """Поиск книг по автору"""
    query_text = urllib.parse.quote(text)
    url = f"http://flibusta.is/booksearch?ask={query_text}&cha=on"

    sp = get_page(url)
    if not sp:
        return None

    target_div = sp.find('div', attrs={'class': 'clear-block', 'id': 'main'})
    if not target_div:
        target_div = sp.find('div', id='main')
        if not target_div:
            return None

    # Ищем списки авторов
    target_ul_list = target_div.find_all('ul')
    
    if len(target_ul_list) == 0:
        return None

    # Находим список с авторами
    authors_links = []
    for target_ul in target_ul_list:
        if target_ul.get('class'):
            continue
            
        li_list = target_ul.find_all("li")
        for li in li_list:
            author_link = li.find('a')
            if author_link:
                href = author_link.get('href', '')
                if href.startswith('/a/'):
                    authors_links.append(SITE + href + '/')

    if not authors_links:
        return None

    final_res = []
    
    # Для каждого автора получаем его книги
    for author_link in authors_links:
        sp_author = get_page(author_link)
        if not sp_author:
            continue

        # Получаем имя автора
        author_h1 = sp_author.find("h1", attrs={"class": "title"})
        if not author_h1:
            continue
        author = author_h1.text.strip()

        # Находим форму с книгами
        target_form = sp_author.find('form', attrs={'method': 'POST'})
        if not target_form:
            continue

        # Исключаем переводы
        target_p_translates = target_form.find("h3", string='Переводы')
        if target_p_translates:
            sibling = target_p_translates.next_sibling
            while sibling:
                next_sibling = sibling.next_sibling
                sibling.extract()
                sibling = next_sibling

        # Ищем книги
        result = []
        
        # Способ 1: через SVG (новая разметка)
        svg_elements = target_form.find_all('svg')
        for svg in svg_elements:
            book_link = svg.find_next_sibling("a")
            if book_link:
                href = book_link.get('href', '')
                if href.startswith('/b/'):
                    book_id = href.replace('/b/', '')
                    book = Book(book_id)
                    book.title = book_link.text.strip()
                    book.author = author
                    book.link = SITE + href + '/'
                    result.append(book)
        
        # Способ 2: через checkbox (старая разметка)
        if not result:
            checkboxes = target_form.find_all('input', attrs={'type': 'checkbox'})
            for cb in checkboxes:
                book_link = cb.find_next_sibling('a')
                if book_link:
                    href = book_link.get('href', '')
                    if href.startswith('/b/'):
                        book_id = href.replace('/b/', '')
                        book = Book(book_id)
                        book.title = book_link.text.strip()
                        book.author = author
                        book.link = SITE + href + '/'
                        result.append(book)
        
        # Способ 3: все ссылки на книги в форме
        if not result:
            book_links = target_form.find_all('a', href=re.compile(r'^/b/\d+$'))
            for book_link in book_links:
                href = book_link.get('href', '')
                book_id = href.replace('/b/', '')
                book = Book(book_id)
                book.title = book_link.text.strip()
                book.author = author
                book.link = SITE + href + '/'
                result.append(book)
        
        if result:
            final_res.append(result)

    return final_res if final_res else None


def scrape_books_mbl(title: str, author: str) -> list[Book] | None:
    """Точный поиск по названию и автору"""
    title_q = urllib.parse.quote(title)
    author_q = urllib.parse.quote(author)
    url = f"http://flibusta.is/makebooklist?ab=ab1&t={title_q}&ln={author_q}&sort=sd2"

    sp = get_page(url)
    if not sp:
        return None
        
    target_form = sp.find('form', attrs={'name': 'bk'})
    
    if target_form is None:
        return None

    div_list = target_form.find_all('div')
    
    result = []
    for d in div_list:
        # Ищем ссылку на книгу
        book_link = d.find('a', href=re.compile(r'^/b/\d+$'))
        if not book_link:
            continue
            
        b_href = book_link.get('href')
        book_id = b_href.replace('/b/', '')
        
        book = Book(book_id)
        book.title = book_link.text.strip()
        book.link = SITE + b_href + '/'
        
        # Ищем авторов
        author_links = d.find_all('a', href=re.compile(r'^/a/\d+$'))
        if author_links:
            authors = [a.text.strip() for a in author_links]
            # Реверсируем порядок для правильного отображения
            book.author = ', '.join(authors[::-1])
        else:
            book.author = author or '[автор не указан]'
        
        result.append(book)

    return result if result else None


def get_book_by_id(book_id):
    """Получение книги по ID"""
    book = Book(book_id)
    book.link = SITE + '/b/' + book_id + '/'

    sp = get_page(book.link)
    if not sp:
        return None
        
    target_div = sp.find('div', attrs={'class': 'clear-block', 'id': 'main'})
    if not target_div:
        target_div = sp.find('div', id='main')
        if not target_div:
            return None

    target_h1 = target_div.find('h1', attrs={'class': 'title'})
    if not target_h1:
        return None
        
    book.title = target_h1.text.strip()
    if book.title == "Книги":
        return None
    
    # Размер книги - ищем в разных местах
    # Ищем span с размером
    size_span = target_div.find('span', string=re.compile(r'\d+.*[МК]Б'))
    if not size_span:
        # Пробуем найти в тексте страницы
        size_elements = target_div.find_all(string=re.compile(r'Размер.*?\d+.*?[МК]Б'))
        if size_elements:
            book.size = size_elements[0].strip()
    else:
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
        b_format = a.text.strip()
        link = a.get('href')
        if link:
            book.formats[b_format] = SITE + link if not link.startswith('http') else link

    # Автор
    author_link = target_h1.find_next('a')
    if author_link and '/a/' in author_link.get('href', ''):
        book.author = author_link.text.strip()
    else:
        book.author = '[автор не указан]'

    return book


def download_book_cover(book: Book):
    """Скачивание обложки книги"""
    if not book or not hasattr(book, 'cover') or not book.cover:
        return
        
    try:
        c_response = requests.get(
            book.cover, 
            timeout=10,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        c_response.raise_for_status()
        
        books_dir = os.path.join(os.getcwd(), "books")
        cover_dir = os.path.join(books_dir, book.id)
        os.makedirs(cover_dir, exist_ok=True)
        
        c_full_path = os.path.join(cover_dir, 'cover.jpg')
        with open(c_full_path, "wb") as f:
            f.write(c_response.content)
    except Exception:
        pass  # Игнорируем ошибки при скачивании обложки


def download_book(book: Book, b_format: str):
    """Скачивание книги в указанном формате"""
    if not book or not hasattr(book, 'formats') or b_format not in book.formats:
        return None, None
        
    book_url = book.formats[b_format]

    try:
        b_response = requests.get(
            book_url, 
            timeout=30,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        
        b_response.raise_for_status()

        # Получаем имя файла из заголовков
        content_disposition = b_response.headers.get('content-disposition', '')
        if 'filename=' in content_disposition:
            n_index = content_disposition.index('filename=')
            b_filename = content_disposition[n_index + 9:].replace('"', '').replace("'", '')
            # Обрабатываем кодировку в filename (RFC 5987)
            if b_filename.startswith("UTF-8''"):
                b_filename = urllib.parse.unquote(b_filename[7:])
            if b_filename.endswith('.fb2.zip'):
                b_filename = b_filename.replace('.zip', '')
        else:
            # Генерируем имя файла
            ext = b_format.split('(')[1].split(')')[0] if '(' in b_format else 'txt'
            # Очищаем расширение от лишних символов
            ext = re.sub(r'[^a-zA-Z0-9]', '', ext.lower())
            b_filename = f"{book.title} - {book.author}.{ext}"
            # Убираем недопустимые символы для Windows/Linux
            b_filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', b_filename)
            # Ограничиваем длину имени файла
            if len(b_filename) > 200:
                name_part = b_filename[:190]
                ext_part = b_filename[-10:]
                b_filename = name_part + ext_part

        return b_response.content, b_filename
        
    except requests.exceptions.Timeout:
        return None, None
    except requests.exceptions.RequestException as e:
        return None, None
    except Exception:
        return None, None
