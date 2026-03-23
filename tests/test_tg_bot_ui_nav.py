import unittest

from src.tg_bot_nav import NAV_STACK_KEY, pop_nav, push_nav, reset_nav
from src.tg_bot_ui import breadcrumbs, screen, truncate


class _DummyContext:
    def __init__(self):
        self.user_data = {}


class TestUiHelpers(unittest.TestCase):
    def test_truncate(self):
        self.assertEqual(truncate("abcdef", 4), "abc…")
        self.assertEqual(truncate("abc", 4), "abc")

    def test_breadcrumbs(self):
        self.assertEqual(breadcrumbs("🏠 Меню", "📚 Результаты"), "🏠 Меню > 📚 Результаты")

    def test_screen(self):
        text = screen("📚 <b>Title</b>", "Body", "🏠 Меню")
        self.assertIn("📚 <b>Title</b>", text)
        self.assertIn("<i>🏠 Меню</i>", text)
        self.assertIn("Body", text)


class TestNavHelpers(unittest.TestCase):
    def test_push_pop_and_reset(self):
        ctx = _DummyContext()
        push_nav(ctx, {"type": "main_menu"})
        push_nav(ctx, {"type": "main_menu"})  # duplicate should be ignored
        push_nav(ctx, {"type": "search_menu"})
        self.assertEqual(len(ctx.user_data[NAV_STACK_KEY]), 2)
        self.assertEqual(pop_nav(ctx), {"type": "search_menu"})
        reset_nav(ctx)
        self.assertEqual(ctx.user_data[NAV_STACK_KEY], [])


if __name__ == "__main__":
    unittest.main()
