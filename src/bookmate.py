"""
Bookmate / Яндекс Книги integration.

API flow:
  1. search_audiobooks(query)  →  list of {uuid, title, authors, duration_sec, cover_url}
  2. get_book_tracks(uuid)     →  list of {number, duration_sec, offset_sec,
                                           m4a_url, size_bytes, availability}
  3. download_track(m4a_url, book_uuid) → bytes  (no auth needed — JWT is in URL)

Authentication:
  search + playlists  →  Yandex session cookies (BOOKMATE_SESSION_ID etc.)
  audio CDN           →  only Origin/Referer headers
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import requests

from . import config

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) "
    "Gecko/20100101 Firefox/120.0"
)


def _auth_cookies() -> dict[str, str]:
    """Build cookie dict from env vars. Returns empty dict if not configured."""
    cookies: dict[str, str] = {}
    if config.BOOKMATE_SESSION_ID:
        cookies["Session_id"] = config.BOOKMATE_SESSION_ID
    if config.BOOKMATE_L_COOKIE:
        cookies["L"] = config.BOOKMATE_L_COOKIE
    if config.BOOKMATE_SESSAR:
        cookies["sessar"] = config.BOOKMATE_SESSAR
    if config.BOOKMATE_YANDEX_LOGIN:
        cookies["yandex_login"] = config.BOOKMATE_YANDEX_LOGIN
    return cookies


def is_configured() -> bool:
    return bool(config.BOOKMATE_SESSION_ID)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BookmateBook:
    uuid: str
    title: str
    authors: list[str]
    narrators: list[str]
    duration_sec: int
    cover_url: str

    @property
    def duration_fmt(self) -> str:
        h, m = divmod(self.duration_sec // 60, 60)
        if h:
            return f"{h} ч {m} мин"
        return f"{m} мин"


@dataclass
class BookmateTrack:
    number: int
    duration_sec: int
    offset_sec: int
    m4a_url: str          # high quality
    m4a_url_min: str      # low quality (smaller, safer for Telegram)
    size_max_bytes: int
    size_min_bytes: int
    availability: str

    @property
    def is_available(self) -> bool:
        return self.availability == "available"

    @property
    def safe_m4a_url(self) -> str:
        """Return low-bitrate URL if max exceeds Telegram 50 MB limit."""
        if self.size_max_bytes > 48 * 1024 * 1024:
            return self.m4a_url_min
        return self.m4a_url

    @property
    def safe_size_bytes(self) -> int:
        if self.size_max_bytes > 48 * 1024 * 1024:
            return self.size_min_bytes
        return self.size_max_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def search_audiobooks(query: str, limit: int = 10) -> list[BookmateBook]:
    """Search Bookmate for audiobooks. Returns up to *limit* results."""
    cookies = _auth_cookies()
    if not cookies:
        logger.warning("Bookmate: no auth cookies configured")
        return []

    try:
        resp = requests.get(
            config.BOOKMATE_SEARCH_URL,
            params={"query": query, "type": "audiobook"},
            cookies=cookies,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
                "Referer": "https://books.yandex.ru/",
            },
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Bookmate search failed: %s", exc)
        return []

    try:
        data = resp.json()
        objects = data["search"]["audiobooks"]["objects"]
    except (KeyError, ValueError) as exc:
        logger.error("Bookmate search: unexpected response: %s", exc)
        return []

    results: list[BookmateBook] = []
    for item in objects[:limit]:
        dur_raw = item.get("duration", 0)
        dur_sec = dur_raw if isinstance(dur_raw, int) else dur_raw.get("seconds", 0)
        results.append(BookmateBook(
            uuid=item.get("uuid", ""),
            title=item.get("title", ""),
            authors=[a.get("name", "") for a in item.get("authors", [])],
            narrators=[n.get("name", "") for n in item.get("narrators", [])],
            duration_sec=dur_sec,
            cover_url=(item.get("cover") or {}).get("small", ""),
        ))
    return results


def get_book_tracks(book_uuid: str) -> list[BookmateTrack]:
    """Fetch track list for an audiobook. Returns tracks in order."""
    cookies = _auth_cookies()
    if not cookies:
        logger.warning("Bookmate: no auth cookies configured")
        return []

    url = config.BOOKMATE_PLAYLISTS_URL.format(uuid=book_uuid)
    try:
        resp = requests.get(
            url,
            params={"lang": "ru"},
            cookies=cookies,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
                "Referer": f"https://books.yandex.ru/audiobooks/{book_uuid}",
            },
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Bookmate playlists failed for %s: %s", book_uuid, exc)
        return []

    try:
        data = resp.json()
        raw_tracks = data.get("tracks", [])
    except (ValueError, KeyError) as exc:
        logger.error("Bookmate playlists: unexpected response: %s", exc)
        return []

    tracks: list[BookmateTrack] = []
    for t in raw_tracks:
        offline = t.get("offline", {})
        max_br = offline.get("max_bit_rate", {})
        min_br = offline.get("min_bit_rate", {})

        m3u8_url = t.get("url", {}).get("m3u8", "")
        max_m3u8 = max_br.get("url", m3u8_url)
        min_m3u8 = min_br.get("url", m3u8_url)

        tracks.append(BookmateTrack(
            number=t.get("number", 0),
            duration_sec=t.get("duration", {}).get("seconds", 0),
            offset_sec=t.get("duration", {}).get("offset", 0),
            m4a_url=max_m3u8.replace("/play.m3u8", "/play.m4a"),
            m4a_url_min=min_m3u8.replace("/play.m3u8", "/play.m4a"),
            size_max_bytes=max_br.get("bytes_size", 0),
            size_min_bytes=min_br.get("bytes_size", 0),
            availability=t.get("availability", "unavailable"),
        ))
    return tracks


def download_track(m4a_url: str, book_uuid: str) -> bytes:
    """Download an audio track. No auth cookies required — JWT is in the URL."""
    try:
        resp = requests.get(
            m4a_url,
            headers={
                "User-Agent": _USER_AGENT,
                "Origin": config.BOOKMATE_AUDIO_ORIGIN,
                "Referer": f"{config.BOOKMATE_AUDIO_ORIGIN}/audiobooks/{book_uuid}",
            },
            timeout=config.DOWNLOAD_TIMEOUT,
            stream=True,
        )
        resp.raise_for_status()

        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            buf.write(chunk)
            if buf.tell() > config.AUDIO_MAX_SIZE:
                raise ValueError(
                    f"Track too large (>{config.AUDIO_MAX_SIZE // 1024 // 1024} MB)"
                )
        return buf.getvalue()
    except Exception as exc:
        logger.error("Bookmate download failed (%s): %s", m4a_url[:80], exc)
        raise
