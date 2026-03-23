"""Tests for src/flib.py — HTML parsing logic."""

from bs4 import BeautifulSoup

from src.flib import (
    Book,
    _find_main_div,
    _fix_redirect_location,
    download_book,
    get_book_by_id,
    scrape_books_by_title,
    scrape_books_mbl,
)

# ────────────────────── Unit tests (no network) ──────────────────────


class TestRedirectFix:
    def test_fixes_http_443_to_https(self):
        result = _fix_redirect_location("http://static.flibusta.is:443/some/path")
        assert result == "https://static.flibusta.is/some/path"

    def test_ignores_normal_https(self):
        assert _fix_redirect_location("https://example.com/path") is None

    def test_ignores_non_443(self):
        assert _fix_redirect_location("http://example.com:8080/path") is None

    def test_ignores_empty(self):
        assert _fix_redirect_location("") is None
        assert _fix_redirect_location(None) is None


class TestBookDataclass:
    def test_str_representation(self):
        b = Book("123", title="Test", author="Author")
        assert str(b) == "Test - Author (123)"

    def test_defaults(self):
        b = Book("1")
        assert b.title == ""
        assert b.formats == {}
        assert b.genres == []

    def test_to_dict(self):
        b = Book("42", title="T", author="A", formats={"(fb2)": "url"}, genres=["fiction"])
        d = b.to_dict()
        assert d["book_id"] == "42"
        assert d["title"] == "T"
        assert '"(fb2)"' in d["formats"]  # JSON string
        assert '"fiction"' in d["genres"]

    def test_from_dict_roundtrip(self):
        original = Book(
            "42",
            title="Test Book",
            author="Author",
            link="http://example.com",
            formats={"(fb2)": "http://example.com/fb2"},
            genres=["fiction", "novel"],
            annotation="A test",
            series="Series 1",
            year="2020",
            rating="5",
            author_link="http://example.com/a/1/",
        )
        d = original.to_dict()
        restored = Book.from_dict(d)
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.formats == original.formats
        assert restored.genres == original.genres
        assert restored.annotation == original.annotation

    def test_from_dict_handles_raw_types(self):
        """from_dict should handle both JSON strings and raw dicts/lists."""
        d = {
            "book_id": "1",
            "title": "T",
            "formats": {"(fb2)": "url"},  # already a dict
            "genres": ["a", "b"],  # already a list
        }
        b = Book.from_dict(d)
        assert b.formats == {"(fb2)": "url"}
        assert b.genres == ["a", "b"]


class TestFindMainDiv:
    def test_finds_clear_block(self):
        html = '<div class="clear-block" id="main"><p>Content</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        div = _find_main_div(soup)
        assert div is not None
        assert div.find("p").text == "Content"

    def test_falls_back_to_id_only(self):
        html = '<div id="main"><p>Content</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        div = _find_main_div(soup)
        assert div is not None

    def test_returns_none_when_missing(self):
        html = "<div><p>No main</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        assert _find_main_div(soup) is None


# ────────────────────── Parsing tests with HTML fixtures ──────────────────────

TITLE_SEARCH_HTML = """
<html><body>
<div class="clear-block" id="main">
<ul>
  <li><a href="/b/123">Мастер и Маргарита</a> - <a href="/a/456">Булгаков Михаил</a></li>
  <li><a href="/b/789">Белая гвардия</a> - <a href="/a/456">Булгаков Михаил</a></li>
</ul>
</div>
</body></html>
"""

MBL_SEARCH_HTML = """
<html><body>
<form name="bk">
  <div><a href="/b/100">Война и мир</a> - <a href="/a/200">Толстой Лев</a></div>
  <div><a href="/b/101">Анна Каренина</a> - <a href="/a/200">Толстой Лев</a></div>
</form>
</body></html>
"""

BOOK_PAGE_HTML = """
<html><body>
<div class="clear-block" id="main">
  <h1 class="title">Мастер и Маргарита</h1>
  <a href="/a/456">Булгаков Михаил</a>
  <a href="/g/1">Роман</a>
  <a href="/g/2">Фантастика</a>
  <a href="/sequence/10">Серия книг</a>
  <a>(fb2)</a>
  <a>(epub)</a>
  <span>2 МБ</span>
  <img alt="Cover image" src="/img/cover.jpg" />
</div>
</body></html>
"""


class TestParseBooksByTitle:
    def test_parse_title_search_results(self, monkeypatch):
        monkeypatch.setattr("src.flib.get_page", lambda url: BeautifulSoup(TITLE_SEARCH_HTML, "html.parser"))
        books = scrape_books_by_title("Булгаков")
        assert books is not None
        assert len(books) == 2
        assert books[0].id == "123"
        assert books[0].title == "Мастер и Маргарита"
        assert books[0].author == "Булгаков Михаил"
        assert books[1].id == "789"

    def test_parse_returns_none_on_empty(self, monkeypatch):
        monkeypatch.setattr("src.flib.get_page", lambda url: None)
        assert scrape_books_by_title("nothing") is None


class TestParseMbl:
    def test_parse_mbl_results(self, monkeypatch):
        monkeypatch.setattr("src.flib.get_page", lambda url: BeautifulSoup(MBL_SEARCH_HTML, "html.parser"))
        books = scrape_books_mbl("Война", "Толстой")
        assert books is not None
        assert len(books) == 2
        assert books[0].id == "100"
        assert books[0].title == "Война и мир"


class TestParseBookById:
    def test_parse_book_page(self, monkeypatch):
        monkeypatch.setattr("src.flib.get_page", lambda url: BeautifulSoup(BOOK_PAGE_HTML, "html.parser"))
        book = get_book_by_id("123")
        assert book is not None
        assert book.title == "Мастер и Маргарита"
        assert book.author == "Булгаков Михаил"
        assert "Роман" in book.genres
        assert "Фантастика" in book.genres
        assert book.series == "Серия книг"

    def test_parse_returns_none_for_missing(self, monkeypatch):
        monkeypatch.setattr("src.flib.get_page", lambda url: None)
        assert get_book_by_id("999") is None


class TestDownloadBook:
    def test_download_returns_none_for_missing_format(self):
        book = Book("1", formats={"(fb2)": "http://example.com/fb2"})
        result, filename = download_book(book, "(epub)")
        assert result is None
        assert filename is None

    def test_download_returns_none_for_none_book(self):
        result, filename = download_book(None, "(fb2)")
        assert result is None
        assert filename is None
