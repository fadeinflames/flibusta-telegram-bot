import unittest

from src.tg_bot_cache import TTLCache


class _Now:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class TestTTLCache(unittest.TestCase):
    def test_get_miss_returns_none(self):
        cache = TTLCache(ttl_sec=10, max_size=10)
        self.assertIsNone(cache.get("missing"))

    def test_expired_item_removed(self):
        now = _Now()
        cache = TTLCache(ttl_sec=10, max_size=10, now=now)
        cache.set("k", "v")
        self.assertEqual(cache.get("k"), "v")
        now.value = 11.0
        self.assertIsNone(cache.get("k"))

    def test_lru_eviction(self):
        now = _Now()
        cache = TTLCache(ttl_sec=100, max_size=2, now=now)
        cache.set("a", 1)
        now.value += 1
        cache.set("b", 2)
        self.assertEqual(cache.get("a"), 1)  # touch a, b becomes oldest
        now.value += 1
        cache.set("c", 3)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.get("c"), 3)


if __name__ == "__main__":
    unittest.main()
