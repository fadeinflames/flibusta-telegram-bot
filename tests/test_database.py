"""Tests for src/database.py."""

from src import database as db


class TestUsers:
    def test_add_and_get_user(self, tmp_db):
        db.add_or_update_user("1", username="alice", full_name="Alice A")
        user = db.get_user("1")
        assert user is not None
        assert user["username"] == "alice"
        assert user["full_name"] == "Alice A"
        assert user["search_count"] == 0

    def test_update_existing_user(self, tmp_db):
        db.add_or_update_user("1", username="alice")
        db.add_or_update_user("1", username="alice2", full_name="Alice")
        user = db.get_user("1")
        assert user["username"] == "alice2"
        assert user["full_name"] == "Alice"

    def test_get_nonexistent_user(self, tmp_db):
        assert db.get_user("999") is None

    def test_update_user_stats(self, tmp_db):
        db.add_or_update_user("1")
        db.update_user_stats("1", search=True)
        db.update_user_stats("1", download=True)
        user = db.get_user("1")
        assert user["search_count"] == 1
        assert user["download_count"] == 1


class TestPreferences:
    def test_set_and_get_preference(self, tmp_db):
        db.add_or_update_user("1")
        db.set_user_preference("1", "books_per_page", 20)
        assert db.get_user_preference("1", "books_per_page") == 20

    def test_get_preference_default(self, tmp_db):
        db.add_or_update_user("1")
        assert db.get_user_preference("1", "missing_key", "default") == "default"

    def test_get_preference_no_user(self, tmp_db):
        assert db.get_user_preference("999", "key", "fallback") == "fallback"


class TestSearchHistory:
    def test_add_and_get_history(self, tmp_db):
        db.add_or_update_user("1")
        db.add_search_history("1", "title", "test query", 5)
        history = db.get_user_search_history("1", limit=10)
        assert len(history) == 1
        assert history[0]["command"] == "title"
        assert history[0]["query"] == "test query"
        assert history[0]["results_count"] == 5

    def test_add_search_history_increments_counter(self, tmp_db):
        db.add_or_update_user("1")
        db.add_search_history("1", "title", "q1", 1)
        db.add_search_history("1", "author", "q2", 2)
        user = db.get_user("1")
        assert user["search_count"] == 2

    def test_get_last_search(self, tmp_db):
        db.add_or_update_user("1")
        db.add_search_history("1", "title", "first", 1)
        db.add_search_history("1", "author", "second", 2)
        last = db.get_last_search("1")
        assert last["command"] == "author"
        assert last["query"] == "second"

    def test_get_last_search_empty(self, tmp_db):
        db.add_or_update_user("1")
        assert db.get_last_search("1") is None

    def test_history_ordering(self, tmp_db):
        db.add_or_update_user("1")
        for i in range(5):
            db.add_search_history("1", "title", f"q{i}", i)
        history = db.get_user_search_history("1", limit=3)
        assert len(history) == 3
        assert history[0]["query"] == "q4"


class TestFavorites:
    def test_add_and_check_favorite(self, tmp_db):
        db.add_or_update_user("1")
        assert db.add_to_favorites("1", "100", "Book", "Author") is True
        assert db.is_favorite("1", "100") is True
        assert db.is_favorite("1", "999") is False

    def test_add_duplicate_favorite(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "100", "Book", "Author")
        assert db.add_to_favorites("1", "100", "Book", "Author") is False

    def test_remove_favorite(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "100", "Book", "Author")
        assert db.remove_from_favorites("1", "100") is True
        assert db.is_favorite("1", "100") is False
        assert db.remove_from_favorites("1", "100") is False

    def test_are_favorites_batch(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "10", "A", "X")
        db.add_to_favorites("1", "20", "B", "Y")
        result = db.are_favorites("1", ["10", "20", "30"])
        assert result == {"10", "20"}

    def test_are_favorites_empty_list(self, tmp_db):
        assert db.are_favorites("1", []) == set()

    def test_get_favorites_with_pagination(self, tmp_db):
        db.add_or_update_user("1")
        for i in range(15):
            db.add_to_favorites("1", str(i), f"Book {i}", "Author")
        page1, total = db.get_user_favorites("1", offset=0, limit=10)
        assert total == 15
        assert len(page1) == 10
        page2, _ = db.get_user_favorites("1", offset=10, limit=10)
        assert len(page2) == 5

    def test_favorites_with_tag_filter(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "1", "Book1", "Auth", tags="want")
        db.add_to_favorites("1", "2", "Book2", "Auth", tags="done")
        db.add_to_favorites("1", "3", "Book3", "Auth", tags="want")
        favs, total = db.get_user_favorites("1", tag="want")
        assert total == 2
        assert all(f["tags"] == "want" for f in favs)

    def test_update_tags(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "1", "Book", "Auth")
        db.update_favorite_tags("1", "1", "reading")
        favs, _ = db.get_user_favorites("1", tag="reading")
        assert len(favs) == 1

    def test_search_favorites(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "1", "Мастер и Маргарита", "Булгаков")
        db.add_to_favorites("1", "2", "Война и мир", "Толстой")
        results = db.search_favorites("1", "Маргарита")
        assert len(results) == 1
        assert results[0]["book_id"] == "1"

    def test_favorites_count_by_tag(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "1", "A", "X", tags="want")
        db.add_to_favorites("1", "2", "B", "Y", tags="want")
        db.add_to_favorites("1", "3", "C", "Z", tags="done")
        counts = db.get_favorites_count_by_tag("1")
        assert counts["want"] == 2
        assert counts["done"] == 1

    def test_export_favorites(self, tmp_db):
        db.add_or_update_user("1")
        db.add_to_favorites("1", "1", "Book", "Author", tags="want", notes="Good book")
        exported = db.get_all_favorites_for_export("1")
        assert len(exported) == 1
        assert exported[0]["notes"] == "Good book"


class TestDownloads:
    def test_add_and_get_downloads(self, tmp_db):
        db.add_or_update_user("1")
        db.add_download("1", "100", "Book", "Author", "(fb2)")
        downloads = db.get_user_downloads("1", limit=10)
        assert len(downloads) == 1
        assert downloads[0]["book_id"] == "100"
        assert downloads[0]["format"] == "(fb2)"

    def test_add_download_increments_counter(self, tmp_db):
        db.add_or_update_user("1")
        db.add_download("1", "100", "Book", "Author", "(fb2)")
        user = db.get_user("1")
        assert user["download_count"] == 1


class TestBookCache:
    def _make_book(self):
        from src.flib import Book

        b = Book("42")
        b.title = "Test Book"
        b.author = "Test Author"
        b.link = "http://example.com/b/42/"
        b.formats = {"(fb2)": "http://example.com/b/42/fb2"}
        b.cover = ""
        b.size = "1 МБ"
        b.genres = ["fiction"]
        b.annotation = "A test book"
        return b

    def test_cache_and_retrieve_book(self, tmp_db):
        book = self._make_book()
        db.cache_book(book)
        cached = db.get_cached_book("42")
        assert cached is not None
        assert cached["title"] == "Test Book"
        assert cached["formats"] == {"(fb2)": "http://example.com/b/42/fb2"}
        assert cached["genres"] == ["fiction"]

    def test_cache_miss(self, tmp_db):
        assert db.get_cached_book("999") is None


class TestStats:
    def test_global_stats(self, tmp_db):
        db.add_or_update_user("1")
        db.add_search_history("1", "title", "test", 5)
        db.add_download("1", "1", "Book", "Author", "fb2")
        stats = db.get_global_stats()
        assert stats["total_users"] == 1
        assert stats["total_searches"] == 1
        assert stats["total_downloads"] == 1

    def test_user_stats(self, tmp_db):
        db.add_or_update_user("1", username="alice", full_name="Alice")
        db.add_to_favorites("1", "1", "Book", "Author")
        stats = db.get_user_stats("1")
        assert stats["favorites_count"] == 1
        assert stats["user_info"]["username"] == "alice"

    def test_user_stats_nonexistent(self, tmp_db):
        assert db.get_user_stats("999") == {}


class TestCleanup:
    def test_cleanup_old_data(self, tmp_db):
        db.add_or_update_user("1")
        db.add_search_history("1", "title", "old query", 1)
        # Manually backdate the record so cleanup can find it
        with db.get_db() as conn:
            conn.execute("UPDATE search_history SET timestamp = datetime('now', '-60 days')")
            conn.commit()
        db.cleanup_old_data(days=30)
        history = db.get_user_search_history("1")
        assert len(history) == 0
