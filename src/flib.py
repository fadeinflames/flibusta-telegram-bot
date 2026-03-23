import io
import json
import os
import re
import shutil
import threading
import time
import urllib.parse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src import config
from src.custom_logging import get_logger

logger = get_logger(__name__)


# ────────────────────── Thread-safe session ──────────────────────

_thread_local = threading.local()


def _fix_redirect_location(location: str) -> str | None:
    """Исправляет редирект http://host:443 -> https://host (Flibusta отдаёт такой Location)."""
    if not location or not location.startswith("http://") or ":443" not in location:
        return None
    parsed = urllib.parse.urlparse(location)
    if not parsed.netloc.endswith(":443"):
        return None
    new_netloc = parsed.netloc.replace(":443", "")
    return urllib.parse.urlunparse(
        ("https", new_netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment)
    )


class RedirectFixAdapter(HTTPAdapter):
    """Исправляет Location с http://host:443 на https://host перед следованием редиректу."""

    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        if 300 <= response.status_code < 400:
            loc = response.headers.get("Location")
            if loc:
                fixed = _fix_redirect_location(loc)
                if fixed:
                    response.headers["Location"] = fixed
        return response


def _get_session() -> requests.Session:
    """Возвращает per-thread сессию с retry-стратегией."""
    session = getattr(_thread_local, "session", None)
    if session is not None:
        return session

    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})

    retry_strategy = Retry(
        total=config.REQUEST_MAX_RETRIES,
        backoff_factor=config.REQUEST_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = RedirectFixAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    _thread_local.session = session
    return session


# ────────────────────── Page cache ──────────────────────

_page_cache_lock = threading.Lock()
_PAGE_CACHE: "OrderedDict[str, tuple[float, BeautifulSoup]]" = OrderedDict()


# ────────────────────── Book dataclass ──────────────────────


@dataclass
class Book:
    id: str
    title: str = ""
    author: str = ""
    link: str = ""
    formats: dict = field(default_factory=dict)
    cover: str = ""
    size: str = ""
    series: str = ""
    year: str = ""
    annotation: str = ""
    genres: list = field(default_factory=list)
    rating: str = ""
    author_link: str = ""

    def __str__(self):
        return f"{self.title} - {self.author} ({self.id})"

    def to_dict(self) -> dict:
        """Serialize Book to a plain dict (for DB cache)."""
        return {
            "book_id": self.id,
            "title": self.title,
            "author": self.author,
            "link": self.link,
            "formats": json.dumps(self.formats),
            "cover": self.cover,
            "size": self.size,
            "series": self.series,
            "year": self.year,
            "annotation": self.annotation,
            "genres": json.dumps(self.genres),
            "rating": self.rating,
            "author_link": self.author_link,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        """Restore Book from a DB-cache dict (with JSON-encoded fields)."""
        formats = data.get("formats", "{}")
        if isinstance(formats, str):
            formats = json.loads(formats)
        genres = data.get("genres", "[]")
        if isinstance(genres, str):
            try:
                genres = json.loads(genres or "[]")
            except (json.JSONDecodeError, TypeError):
                genres = []

        return cls(
            id=data.get("book_id", data.get("id", "")),
            title=data.get("title", ""),
            author=data.get("author", ""),
            link=data.get("link", ""),
            formats=formats,
            cover=data.get("cover", ""),
            size=data.get("size", ""),
            series=data.get("series", ""),
            year=data.get("year", ""),
            annotation=data.get("annotation", ""),
            genres=genres,
            rating=data.get("rating", ""),
            author_link=data.get("author_link", ""),
        )


# ────────────────────── Helpers ──────────────────────


def _find_main_div(soup: BeautifulSoup):
    """Find the main content div on a Flibusta page."""
    div = soup.find("div", attrs={"class": "clear-block", "id": "main"})
    if not div:
        div = soup.find("div", id="main")
    return div


def get_page(url):
    """Получение и кэширование страницы."""
    try:
        now = time.time()

        with _page_cache_lock:
            if url in _PAGE_CACHE:
                cached_time, cached_soup = _PAGE_CACHE[url]
                if now - cached_time < config.PAGE_CACHE_TTL_SEC:
                    _PAGE_CACHE.move_to_end(url)
                    return cached_soup
                _PAGE_CACHE.pop(url, None)

        session = _get_session()
        response = session.get(url, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        with _page_cache_lock:
            _PAGE_CACHE[url] = (now, soup)
            _PAGE_CACHE.move_to_end(url)
            if len(_PAGE_CACHE) > config.PAGE_CACHE_MAX_SIZE:
                _PAGE_CACHE.popitem(last=False)

        return soup
    except requests.exceptions.RequestException:
        return None
    except Exception:
        logger.warning("Unexpected parser error in get_page", extra={"url": url}, exc_info=True)
        return None


def scrape_books_by_title(text: str) -> list[Book] | None:
    """Поиск книг по названию."""
    query_text = urllib.parse.quote(text)
    url = f"{config.SITE}/booksearch?ask={query_text}&chb=on"

    sp = get_page(url)
    if not sp:
        return None

    target_div = _find_main_div(sp)
    if not target_div:
        return None

    target_ul_list = target_div.find_all("ul")
    if len(target_ul_list) == 0:
        return None

    result = []

    for target_ul in target_ul_list:
        if target_ul.get("class"):
            continue

        li_list = target_ul.find_all("li")

        for li in li_list:
            all_links = li.find_all("a")
            if not all_links:
                continue

            first_link = all_links[0]
            href = first_link.get("href", "")

            if not href.startswith("/b/"):
                continue

            book_id = href.replace("/b/", "")
            book = Book(book_id)
            book.title = first_link.text.strip()
            book.link = config.SITE + href + "/"

            authors = []
            for link in all_links[1:]:
                link_href = link.get("href", "")
                if link_href.startswith("/a/"):
                    authors.append(link.text.strip())
                    if not book.author_link:
                        book.author_link = config.SITE + link_href + "/"

            book.author = ", ".join(authors) if authors else "[автор не указан]"
            result.append(book)

    return result if result else None


def _parse_author_page(author_link: str) -> list[Book]:
    """Parse a single author page and return list of books."""
    sp_author = get_page(author_link)
    if not sp_author:
        return []

    author_h1 = sp_author.find("h1", attrs={"class": "title"})
    if not author_h1:
        return []
    author = author_h1.text.strip()

    target_form = sp_author.find("form", attrs={"method": "POST"})
    if not target_form:
        return []

    target_p_translates = target_form.find("h3", string="Переводы")
    if target_p_translates:
        sibling = target_p_translates.next_sibling
        while sibling:
            next_sibling = sibling.next_sibling
            sibling.extract()
            sibling = next_sibling

    result = []

    svg_elements = target_form.find_all("svg")
    for svg in svg_elements:
        book_link = svg.find_next_sibling("a")
        if book_link:
            href = book_link.get("href", "")
            if href.startswith("/b/"):
                book_id = href.replace("/b/", "")
                book = Book(book_id)
                book.title = book_link.text.strip()
                book.author = author
                book.author_link = author_link
                book.link = config.SITE + href + "/"
                result.append(book)

    if not result:
        checkboxes = target_form.find_all("input", attrs={"type": "checkbox"})
        for cb in checkboxes:
            book_link = cb.find_next_sibling("a")
            if book_link:
                href = book_link.get("href", "")
                if href.startswith("/b/"):
                    book_id = href.replace("/b/", "")
                    book = Book(book_id)
                    book.title = book_link.text.strip()
                    book.author = author
                    book.author_link = author_link
                    book.link = config.SITE + href + "/"
                    result.append(book)

    if not result:
        book_links = target_form.find_all("a", href=re.compile(r"^/b/\d+$"))
        for book_link in book_links:
            href = book_link.get("href", "")
            book_id = href.replace("/b/", "")
            book = Book(book_id)
            book.title = book_link.text.strip()
            book.author = author
            book.author_link = author_link
            book.link = config.SITE + href + "/"
            result.append(book)

    return result


def scrape_books_by_author(text: str) -> list[list[Book]] | None:
    """Поиск книг по автору (параллельная загрузка страниц авторов)."""
    query_text = urllib.parse.quote(text)
    url = f"{config.SITE}/booksearch?ask={query_text}&cha=on"

    sp = get_page(url)
    if not sp:
        return None

    target_div = _find_main_div(sp)
    if not target_div:
        return None

    target_ul_list = target_div.find_all("ul")
    if len(target_ul_list) == 0:
        return None

    authors_links = []
    for target_ul in target_ul_list:
        if target_ul.get("class"):
            continue

        li_list = target_ul.find_all("li")
        for li in li_list:
            author_link = li.find("a")
            if author_link:
                href = author_link.get("href", "")
                if href.startswith("/a/"):
                    authors_links.append(config.SITE + href + "/")

    if not authors_links:
        return None

    # Parallel fetch of author pages
    final_res = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = pool.map(_parse_author_page, authors_links)
        for books in results:
            if books:
                final_res.append(books)

    return final_res if final_res else None


def scrape_books_mbl(title: str, author: str) -> list[Book] | None:
    """Точный поиск по названию и автору."""
    title_q = urllib.parse.quote(title)
    author_q = urllib.parse.quote(author)
    url = f"{config.SITE}/makebooklist?ab=ab1&t={title_q}&ln={author_q}&sort=sd2"

    sp = get_page(url)
    if not sp:
        return None

    target_form = sp.find("form", attrs={"name": "bk"})
    if target_form is None:
        return None

    div_list = target_form.find_all("div")

    result = []
    for d in div_list:
        book_link = d.find("a", href=re.compile(r"^/b/\d+$"))
        if not book_link:
            continue

        b_href = book_link.get("href")
        book_id = b_href.replace("/b/", "")

        book = Book(book_id)
        book.title = book_link.text.strip()
        book.link = config.SITE + b_href + "/"

        author_links = d.find_all("a", href=re.compile(r"^/a/\d+$"))
        if author_links:
            authors = [a.text.strip() for a in author_links]
            book.author = ", ".join(authors[::-1])
            book.author_link = config.SITE + author_links[0].get("href", "") + "/"
        else:
            book.author = author or "[автор не указан]"

        result.append(book)

    return result if result else None


def get_book_by_id(book_id):
    """Получение книги по ID с аннотацией, жанрами и рейтингом."""
    book = Book(book_id)
    book.link = f"{config.SITE}/b/{book_id}/"

    sp = get_page(book.link)
    if not sp:
        return None

    target_div = _find_main_div(sp)
    if not target_div:
        return None

    target_h1 = target_div.find("h1", attrs={"class": "title"})
    if not target_h1:
        return None

    book.title = target_h1.text.strip()
    if book.title == "Книги":
        return None

    size_span = target_div.find("span", string=re.compile(r"\d+.*[МК]Б"))
    if not size_span:
        size_elements = target_div.find_all(string=re.compile(r"Размер.*?\d+.*?[МК]Б"))
        if size_elements:
            book.size = size_elements[0].strip()
    else:
        book.size = size_span.text.strip()

    target_img = target_div.find("img", attrs={"alt": "Cover image"})
    if target_img:
        img_src = target_img.get("src")
        if img_src:
            book.cover = config.SITE + img_src if not img_src.startswith("http") else img_src

    format_links = target_div.find_all("a", string=re.compile(r"\(.*(?:fb2|epub|mobi|pdf|djvu)\)"))
    for a in format_links:
        b_format = a.text.strip()
        link = a.get("href")
        if link:
            book.formats[b_format] = config.SITE + link if not link.startswith("http") else link

    author_link = target_h1.find_next("a")
    if author_link and "/a/" in author_link.get("href", ""):
        book.author = author_link.text.strip()
        book.author_link = config.SITE + author_link.get("href", "") + "/"
    else:
        book.author = "[автор не указан]"

    try:
        genre_links = target_div.find_all("a", href=re.compile(r"^/g/\d+"))
        if genre_links:
            book.genres = list(dict.fromkeys(g.text.strip() for g in genre_links if g.text.strip()))
    except Exception:
        logger.debug("Failed to parse genres", extra={"book_id": book_id}, exc_info=True)

    try:
        annotation_parts = []

        ann_header = target_div.find(["h2", "h3"], string=re.compile(r"аннотация|описание", re.IGNORECASE))
        if ann_header:
            sibling = ann_header.find_next_sibling()
            while sibling and sibling.name in ("p", "div", None):
                txt = sibling.get_text(strip=True)
                if txt:
                    annotation_parts.append(txt)
                sibling = sibling.find_next_sibling()
                if sibling and sibling.name in ("h2", "h3", "form"):
                    break

        if not annotation_parts:
            content_div = target_div.find(
                "div", class_=re.compile(r"content|body|description|field-item", re.IGNORECASE)
            )
            if content_div:
                paragraphs = content_div.find_all("p")
                for p in paragraphs:
                    txt = p.get_text(strip=True)
                    if txt and len(txt) > 20:
                        annotation_parts.append(txt)

        if not annotation_parts:
            for p in target_div.find_all("p"):
                txt = p.get_text(strip=True)
                if txt and len(txt) > 30 and not re.match(r"^(Скачать|Размер|Формат)", txt):
                    annotation_parts.append(txt)

        if annotation_parts:
            book.annotation = "\n".join(annotation_parts[:5])
            if len(book.annotation) > 1500:
                book.annotation = book.annotation[:1497] + "..."
    except Exception:
        logger.debug("Failed to parse annotation", extra={"book_id": book_id}, exc_info=True)

    try:
        series_link = target_div.find("a", href=re.compile(r"^/sequence/\d+"))
        if series_link:
            book.series = series_link.text.strip()
    except Exception:
        logger.debug("Failed to parse series", extra={"book_id": book_id}, exc_info=True)

    try:
        if not book.year:
            year_match = target_div.find(string=re.compile(r"Год\s*издания.*?(\d{4})"))
            if year_match:
                m = re.search(r"(\d{4})", str(year_match))
                if m:
                    book.year = m.group(1)
    except Exception:
        logger.debug("Failed to parse year", extra={"book_id": book_id}, exc_info=True)

    return book


def get_other_books_by_author(author_url: str, exclude_book_id: str = None, limit: int = 10) -> list[Book]:
    """Получить другие книги автора по ссылке на страницу автора."""
    if not author_url:
        return []
    try:
        sp = get_page(author_url)
        if not sp:
            return []

        author_h1 = sp.find("h1", attrs={"class": "title"})
        author_name = author_h1.text.strip() if author_h1 else ""

        target_form = sp.find("form", attrs={"method": "POST"})
        if not target_form:
            return []

        result = []
        book_links = target_form.find_all("a", href=re.compile(r"^/b/\d+$"))
        for bl in book_links:
            href = bl.get("href", "")
            bid = href.replace("/b/", "")
            if bid == exclude_book_id:
                continue
            b = Book(bid)
            b.title = bl.text.strip()
            b.author = author_name
            b.author_link = author_url
            b.link = config.SITE + href + "/"
            result.append(b)
            if len(result) >= limit:
                break
        return result
    except Exception:
        logger.warning("Failed to fetch author's books", extra={"author_url": author_url}, exc_info=True)
        return []


def download_book_cover(book: Book):
    """Скачивание обложки книги."""
    if not book or not book.cover:
        return

    try:
        session = _get_session()
        c_response = session.get(book.cover, timeout=config.DOWNLOAD_TIMEOUT)
        c_response.raise_for_status()

        cover_dir = os.path.join(config.BOOKS_DIR, book.id)
        os.makedirs(cover_dir, exist_ok=True)

        c_full_path = os.path.join(cover_dir, "cover.jpg")
        with open(c_full_path, "wb") as f:
            f.write(c_response.content)
    except (OSError, requests.exceptions.RequestException):
        logger.debug(
            "Cover download failed",
            extra={"book_id": getattr(book, "id", None), "cover_url": getattr(book, "cover", None)},
            exc_info=True,
        )


class DownloadTooLargeError(Exception):
    """Raised when a download exceeds MAX_DOWNLOAD_SIZE."""


def download_book(book: Book, b_format: str) -> tuple[io.BytesIO | None, str | None]:
    """Скачивание книги в указанном формате (стриминг в буфер с лимитом размера)."""
    if not book or b_format not in book.formats:
        return None, None

    book_url = book.formats[b_format]

    try:
        session = _get_session()

        with session.get(book_url, timeout=config.DOWNLOAD_TIMEOUT, stream=True) as b_response:
            b_response.raise_for_status()

            # Check Content-Length if available
            content_length = b_response.headers.get("content-length")
            if content_length and int(content_length) > config.MAX_DOWNLOAD_SIZE:
                raise DownloadTooLargeError(f"File size {int(content_length)} exceeds limit {config.MAX_DOWNLOAD_SIZE}")

            # Получаем имя файла из заголовков
            content_disposition = b_response.headers.get("content-disposition", "")
            if "filename=" in content_disposition:
                n_index = content_disposition.index("filename=")
                b_filename = content_disposition[n_index + 9 :].replace('"', "").replace("'", "")
                if b_filename.startswith("UTF-8''"):
                    b_filename = urllib.parse.unquote(b_filename[7:])
                if b_filename.endswith(".fb2.zip"):
                    b_filename = b_filename.replace(".zip", "")
            else:
                ext = b_format.split("(")[1].split(")")[0] if "(" in b_format else "txt"
                ext = re.sub(r"[^a-zA-Z0-9]", "", ext.lower())
                b_filename = f"{book.title} - {book.author}.{ext}"
                b_filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", b_filename)
                if len(b_filename) > 200:
                    name_part = b_filename[:190]
                    ext_part = b_filename[-10:]
                    b_filename = name_part + ext_part

            buf = io.BytesIO()
            total = 0
            for chunk in b_response.iter_content(chunk_size=8192):
                total += len(chunk)
                if total > config.MAX_DOWNLOAD_SIZE:
                    raise DownloadTooLargeError(f"Download exceeded limit {config.MAX_DOWNLOAD_SIZE} during streaming")
                buf.write(chunk)
            buf.seek(0)
            buf.name = b_filename

        return buf, b_filename

    except DownloadTooLargeError:
        logger.warning(
            "Download too large",
            extra={"book_id": book.id, "format": b_format, "url": book_url},
        )
        return None, None
    except requests.exceptions.Timeout:
        logger.warning(
            "Download timeout",
            extra={"book_id": book.id, "format": b_format, "url": book_url},
            exc_info=True,
        )
        return None, None
    except requests.exceptions.RequestException as e:
        extra = {"book_id": book.id, "format": b_format, "url": book_url}
        req = getattr(e, "request", None)
        if req and getattr(req, "url", None) and req.url != book_url:
            extra["resolved_url"] = req.url
        logger.warning("Download request failed", extra=extra, exc_info=True)
        return None, None
    except Exception:
        logger.warning(
            "Download error",
            extra={"book_id": book.id, "format": b_format, "url": book_url},
            exc_info=True,
        )
        return None, None


def cleanup_old_files(days: int = 30):
    """Очистка старых файлов книг и обложек."""
    if days <= 0:
        return

    cutoff = time.time() - (days * 24 * 60 * 60)
    if not os.path.exists(config.BOOKS_DIR):
        return

    for book_dir in os.listdir(config.BOOKS_DIR):
        full_path = os.path.join(config.BOOKS_DIR, book_dir)
        try:
            if os.path.isdir(full_path) and os.path.getmtime(full_path) < cutoff:
                shutil.rmtree(full_path, ignore_errors=True)
        except OSError:
            continue
