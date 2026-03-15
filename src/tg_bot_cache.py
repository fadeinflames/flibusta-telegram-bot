import time
from collections import OrderedDict
from collections.abc import Callable


class TTLCache:
    """Simple in-memory TTL cache with LRU eviction."""

    def __init__(self, ttl_sec: int, max_size: int, now: Callable[[], float] | None = None):
        self._ttl_sec = ttl_sec
        self._max_size = max_size
        self._now = now or time.time
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str):
        item = self._data.get(key)
        if not item:
            return None
        ts, value = item
        if self._now() - ts > self._ttl_sec:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value):
        self._data[key] = (self._now(), value)
        self._data.move_to_end(key)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)
