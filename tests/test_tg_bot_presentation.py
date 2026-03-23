import unittest

from src import config
from src.tg_bot_presentation import escape_html, escape_md, get_user_level, next_level_info, shelf_label


class TestTgBotPresentation(unittest.TestCase):
    def test_escape_html_escapes_special_chars(self):
        self.assertEqual(escape_html("<b>bold&</b>"), "&lt;b&gt;bold&amp;&lt;/b&gt;")

    def test_escape_html_handles_empty(self):
        self.assertEqual(escape_html(""), "")
        self.assertEqual(escape_html(None), "")

    def test_escape_md_is_alias_for_escape_html(self):
        self.assertIs(escape_md, escape_html)

    def test_escape_html_passes_through_safe_text(self):
        self.assertEqual(escape_html("hello world"), "hello world")

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
