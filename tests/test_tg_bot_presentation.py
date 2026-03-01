import unittest

from src import config
from src.tg_bot_presentation import escape_md, get_user_level, next_level_info, shelf_label


class TestTgBotPresentation(unittest.TestCase):
    def test_escape_md_escapes_markdown_v1_chars(self):
        self.assertEqual(escape_md("_*`["), "\\_\\*\\`\\[")

    def test_escape_md_handles_empty(self):
        self.assertEqual(escape_md(""), "")
        self.assertEqual(escape_md(None), "")

    def test_get_user_level_returns_last_reached_level(self):
        top = config.ACHIEVEMENT_LEVELS[-1]
        self.assertEqual(get_user_level(10_000, 10_000), top["name"])

    def test_next_level_info_returns_max_for_top_level(self):
        top = config.ACHIEVEMENT_LEVELS[-1]
        self.assertEqual(
            next_level_info(top["searches"], top["downloads"]),
            "Максимальный уровень достигнут! 🎉",
        )

    def test_shelf_label_known_and_unknown(self):
        self.assertEqual(shelf_label("want"), config.FAVORITE_SHELVES["want"])
        self.assertEqual(shelf_label("custom"), "custom")
        self.assertEqual(shelf_label(""), "Все")


if __name__ == "__main__":
    unittest.main()
