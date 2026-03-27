"""Tests for reading_progress table and helpers."""

import json

from src import database as db


class TestReadingProgress:
    def test_upsert_and_list(self, tmp_db):
        db.add_or_update_user("42")
        db.reading_progress_upsert_audio(
            42,
            "12345",
            "Test Book",
            "Author",
            None,
            [1, 2, 3, 4],
            2,
        )
        rows = db.reading_progress_list(42)
        assert len(rows) == 1
        assert rows[0]["rutracker_topic_id"] == "12345"
        assert rows[0]["current_chapter"] == 2
        assert rows[0]["total_chapters"] == 4
        assert json.loads(rows[0]["file_indices_json"]) == [1, 2, 3, 4]

    def test_by_topic_and_update_chapter(self, tmp_db):
        db.add_or_update_user("7")
        db.reading_progress_upsert_audio(
            7,
            "999",
            "T",
            "",
            None,
            [10, 20],
            0,
        )
        row = db.reading_progress_by_topic(7, "999")
        assert row is not None
        assert row["current_chapter"] == 0
        db.reading_progress_update_chapter(7, "999", 1)
        row2 = db.reading_progress_by_topic(7, "999")
        assert row2["current_chapter"] == 1

    def test_delete(self, tmp_db):
        db.add_or_update_user("1")
        db.reading_progress_upsert_audio(1, "55", "X", "", None, [1], 0)
        rid = db.reading_progress_list(1)[0]["id"]
        assert db.reading_progress_delete(1, rid) is True
        assert db.reading_progress_list(1) == []
