"""akniga.org client — scraping, AJAX, AES crypto, HLS/MP3 download.

Verified against live site 2026-03-27. Key findings:
- Search URL: /search/books?q=<query>
- Book items: div.content__main__articles--item[data-bid]
- AJAX flow: 2 steps — /ajax/player/token → /ajax/b/{bid} with token
- Audio: HLS playlist at hres (AES-encrypted), all chapters in one m3u8
- Chapter seeking: ffmpeg -ss <time_from_start> -t <duration>
- DDoSGuard: must visit homepage before POST to /ajax/b/
"""

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from src import config
from src.custom_logging import get_logger

logger = get_logger(__name__)

SITE = config.AKNIGA_SITE
AJAX_KEY = config.AKNIGA_AJAX_KEY

_SESSION: requests.Session | None = None
_SESSION_WARMED = False

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


# ────────────────────── Session ──────────────────────


def _get_session() -> requests.Session:
    """Return a shared requests.Session, warming it up with a homepage hit if needed."""
    global _SESSION, _SESSION_WARMED
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update(_BROWSER_HEADERS)
    if not _SESSION_WARMED:
        try:
            _SESSION.headers["Accept"] = (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            )
            _SESSION.get(SITE + "/", timeout=config.REQUEST_TIMEOUT)
            _SESSION_WARMED = True
        except Exception as e:  # noqa: BLE001
            logger.warning("akniga homepage warmup failed", exc_info=e)
    return _SESSION


def _reset_session() -> None:
    """Force a fresh session (call after persistent 403 errors)."""
    global _SESSION, _SESSION_WARMED
    _SESSION = None
    _SESSION_WARMED = False


# ────────────────────── Data models ──────────────────────


@dataclass
class AudiobookChapter:
    index: int
    title: str
    duration_sec: int = 0
    time_from_start: int = 0  # seconds from beginning of the full HLS stream


@dataclass
class Audiobook:
    book_id: str
    slug: str
    title: str
    author: str
    narrator: str = ""
    description: str = ""
    cover_url: str = ""
    chapters: list[AudiobookChapter] = field(default_factory=list)

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)

    @property
    def url(self) -> str:
        return f"{SITE}/{self.slug}"


# ────────────────────── CryptoJS AES (EVP_BytesToKey) ──────────────────────


def _evp_kdf(password: bytes, salt: bytes) -> tuple[bytes, bytes]:
    d = b""
    d_i = b""
    while len(d) < 48:
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:32], d[32:48]


def cryptojs_decrypt(ciphertext_json: str, passphrase: str = AJAX_KEY) -> str:
    """Decrypt CryptoJS AES JSON-encoded ciphertext (EVP_BytesToKey + AES-256-CBC)."""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    data = json.loads(ciphertext_json)
    salt = bytes.fromhex(data["s"])
    ct = base64.b64decode(data["ct"])
    iv = bytes.fromhex(data["iv"])
    key, _ = _evp_kdf(passphrase.encode(), salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ct), AES.block_size).decode()


# ────────────────────── Search ──────────────────────


def search_audiobooks(query: str, page: int = 1) -> list[dict]:
    """
    Search audiobooks on akniga.org.

    Returns list of dicts: {book_id, slug, title, author, narrator, cover_url, duration}.
    """
    session = _get_session()
    params: dict = {"q": query}
    if page > 1:
        params["page"] = page

    url = f"{SITE}/search/books"
    try:
        session.headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        )
        resp = session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("akniga search failed", exc_info=e, extra={"query": query})
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    for item in soup.select("div.content__main__articles--item"):
        try:
            bid = item.get("data-bid", "")
            if not bid:
                continue

            # Slug and title from cover block
            cover_a = item.select_one(".article--cover a")
            cover_img = item.select_one(".article--cover img")
            if not cover_a:
                continue

            href = cover_a.get("href", "")
            slug = href.rstrip("/").split("/")[-1] if href else ""
            if not slug:
                continue

            # Title: prefer img alt (clean), fall back to h2 text
            title = ""
            if cover_img:
                title = cover_img.get("alt", "").strip()
            if not title:
                h2 = item.select_one("h2.caption__article-main")
                if h2:
                    raw = h2.get_text(strip=True)
                    # Format: "Автор – Название", strip author part
                    if " – " in raw:
                        title = raw.split(" – ", 1)[1]
                    else:
                        title = raw

            author_a = item.select_one('a[href*="/author/"]')
            author = author_a.get_text(strip=True) if author_a else ""

            narrator_a = item.select_one('a[href*="/performer/"]')
            narrator = narrator_a.get_text(strip=True) if narrator_a else ""

            cover_url = ""
            if cover_img:
                src = cover_img.get("src", "")
                cover_url = src if src.startswith("http") else (SITE + src if src else "")

            # Duration from hours/minutes spans
            h_span = item.select_one("span.hours")
            m_span = item.select_one("span.minutes")
            duration = ""
            if h_span or m_span:
                parts = []
                if h_span:
                    parts.append(h_span.get_text(strip=True))
                if m_span:
                    parts.append(m_span.get_text(strip=True))
                duration = " ".join(parts)

            results.append({
                "book_id": bid,
                "slug": slug,
                "title": title,
                "author": author,
                "narrator": narrator,
                "cover_url": cover_url,
                "duration": duration,
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to parse search result item", exc_info=e)
            continue

    logger.info(
        "akniga search done",
        extra={"query": query, "page": page, "results": len(results)},
    )
    return results


# ────────────────────── Book page ──────────────────────


def get_book_page(slug: str) -> dict | None:
    """
    Fetch book page and extract book_id + security_ls_key + metadata.

    Returns dict: {book_id, slug, security_ls_key, title, author, narrator,
                   description, cover_url}.
    """
    session = _get_session()
    url = f"{SITE}/{slug}"

    try:
        session.headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        )
        resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("akniga get_book_page failed", exc_info=e, extra={"slug": slug})
        return None

    text = resp.text
    soup = BeautifulSoup(text, "lxml")

    # book_id from data-bid attribute (any element)
    bid_match = re.search(r'data-bid=["\'](\d+)["\']', text)
    if not bid_match:
        logger.warning("No data-bid found on book page", extra={"slug": slug})
        return None
    book_id = bid_match.group(1)

    # Security key from inline JS
    key_match = re.search(r"LIVESTREET_SECURITY_KEY\s*=\s*['\"]([^'\"]+)['\"]", text)
    security_ls_key = key_match.group(1) if key_match else ""

    # Title from cover img alt (most reliable) or h1/h2
    title = ""
    cover_img = soup.select_one(".article--cover img, img[src*='preview']")
    if cover_img:
        title = cover_img.get("alt", "").strip()
    if not title:
        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        h2 = soup.select_one("h2.caption__article-main")
        if h2:
            raw = h2.get_text(strip=True)
            title = raw.split(" – ", 1)[1] if " – " in raw else raw
    if not title:
        title = slug.replace("-", " ").title()

    author_a = soup.select_one('a[href*="/author/"]')
    author = author_a.get_text(strip=True) if author_a else ""

    narrator_a = soup.select_one('a[href*="/performer/"]')
    narrator = narrator_a.get_text(strip=True) if narrator_a else ""

    desc_tag = soup.select_one(".description__article-main, .b-book__description")
    description = desc_tag.get_text(" ", strip=True)[:500] if desc_tag else ""

    cover_url = ""
    if cover_img:
        src = cover_img.get("src", "")
        cover_url = src if src.startswith("http") else (SITE + src if src else "")

    return {
        "book_id": book_id,
        "slug": slug,
        "security_ls_key": security_ls_key,
        "title": title,
        "author": author,
        "narrator": narrator,
        "description": description,
        "cover_url": cover_url,
    }


# ────────────────────── AJAX: get media URLs ──────────────────────


def get_book_media(book_id: str, security_ls_key: str, slug: str = "") -> dict | None:
    """
    Two-step AJAX flow to get the HLS URL and chapter list.

    Step 1: POST /ajax/player/token  → {token}
    Step 2: POST /ajax/b/{book_id}   → {hres (encrypted), items, srv}

    Returns dict: {m3u8_url, items, srv} or None on error.
    """
    session = _get_session()
    page_url = f"{SITE}/{slug}" if slug else SITE + "/"

    xhr_headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": SITE,
        "Referer": page_url,
    }

    # Step 1: get player token
    ts = int(time.time() * 1000)
    try:
        token_resp = session.post(
            f"{SITE}/ajax/player/token",
            data={"bid": book_id, "ts": ts, "security_ls_key": security_ls_key},
            headers=xhr_headers,
            timeout=config.REQUEST_TIMEOUT,
        )
        token_resp.raise_for_status()
        if not token_resp.text.strip():
            logger.error("akniga token response empty", extra={"book_id": book_id})
            return None
        token_data = token_resp.json()
        token = token_data.get("token", "")
        if not token:
            logger.error(
                "akniga token missing in response",
                extra={"book_id": book_id, "resp": token_data},
            )
            return None
    except Exception as e:  # noqa: BLE001
        logger.error("akniga token request failed", exc_info=e, extra={"book_id": book_id})
        return None

    # Step 2: get media data
    try:
        media_resp = session.post(
            f"{SITE}/ajax/b/{book_id}",
            data={"bid": book_id, "token": token, "hls": 1, "security_ls_key": security_ls_key},
            headers=xhr_headers,
            timeout=config.REQUEST_TIMEOUT,
        )
        if media_resp.status_code == 403:
            # DDoSGuard challenge — reset session and retry once
            logger.warning("akniga /ajax/b/ returned 403, resetting session", extra={"book_id": book_id})
            _reset_session()
            session = _get_session()
            time.sleep(1)
            # Re-fetch security key from page
            page_data = get_book_page(slug) if slug else None
            if page_data:
                return get_book_media(
                    page_data["book_id"],
                    page_data["security_ls_key"],
                    slug=slug,
                )
            return None
        media_resp.raise_for_status()
        if not media_resp.text.strip():
            logger.error("akniga media response empty", extra={"book_id": book_id})
            return None
        data = media_resp.json()
    except Exception as e:  # noqa: BLE001
        logger.error("akniga media request failed", exc_info=e, extra={"book_id": book_id})
        return None

    if data.get("bStateError"):
        logger.error("akniga media error", extra={"book_id": book_id, "msg": data.get("sMsg")})
        return None

    # Decrypt HLS URL from "hres" field
    m3u8_url = ""
    hres_enc = data.get("hres", "")
    if hres_enc:
        try:
            raw = cryptojs_decrypt(hres_enc)
            # raw may be JSON-string-quoted: "\"https://...\""
            m3u8_url = raw.strip().strip('"').replace("\\/", "/")
        except Exception as e:  # noqa: BLE001
            logger.error("akniga hres decrypt failed", exc_info=e, extra={"book_id": book_id})

    # Parse items (chapter list)
    raw_items = data.get("items", "[]")
    if isinstance(raw_items, str):
        try:
            raw_items = json.loads(raw_items)
        except json.JSONDecodeError:
            raw_items = []
    items: list = raw_items if isinstance(raw_items, list) else []

    srv = data.get("srv", "")

    logger.info(
        "akniga media loaded",
        extra={"book_id": book_id, "chapters": len(items), "m3u8": m3u8_url[:60]},
    )
    return {"m3u8_url": m3u8_url, "items": items, "srv": srv}


# ────────────────────── Chapter parsing ──────────────────────


def parse_chapters(items: list) -> list[AudiobookChapter]:
    """Convert raw items array from AJAX into AudiobookChapter list."""
    chapters = []
    for i, item in enumerate(items):
        if isinstance(item, dict):
            title = item.get("title", f"Глава {i + 1}")
            duration = item.get("duration", 0)
            try:
                duration_sec = int(float(duration))
            except (ValueError, TypeError):
                duration_sec = 0
            time_from_start = item.get("time_from_start", 0)
            try:
                time_from_start = int(float(time_from_start))
            except (ValueError, TypeError):
                time_from_start = 0
            chapters.append(
                AudiobookChapter(
                    index=i,
                    title=title,
                    duration_sec=duration_sec,
                    time_from_start=time_from_start,
                )
            )
        else:
            chapters.append(AudiobookChapter(index=i, title=f"Глава {i + 1}"))
    return chapters


# ────────────────────── Duration formatting ──────────────────────


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h} ч {m} мин" if h else f"{m} мин"


def format_duration_from_chapters(chapters: list[AudiobookChapter]) -> str:
    total = sum(c.duration_sec for c in chapters)
    if total == 0:
        return ""
    return _format_duration(total)


# ────────────────────── Audio download ──────────────────────


def download_chapter_hls(
    m3u8_url: str,
    chapter_title: str = "",
    time_offset: int = 0,
    duration_sec: int = 0,
) -> bytes | None:
    """
    Download a chapter from the HLS stream via ffmpeg and return MP3 bytes.

    time_offset: seconds from the start of the full stream (time_from_start).
    duration_sec: chapter duration in seconds (0 = to end of stream).
    """
    logger.info(
        "Downloading HLS chapter",
        extra={"url": m3u8_url[:80], "offset": time_offset, "duration": duration_sec},
    )

    cmd = ["ffmpeg", "-y", "-v", "warning"]
    if time_offset > 0:
        cmd += ["-ss", str(time_offset)]
    cmd += ["-i", m3u8_url]
    if duration_sec > 0:
        cmd += ["-t", str(duration_sec)]
    # 64kbps mono is sufficient for audiobooks and keeps file size within Telegram's 50MB limit
    # (e.g. 90-minute chapter: 5400s × 64000bps ÷ 8 ≈ 43MB)
    cmd += ["-vn", "-acodec", "libmp3lame", "-b:a", "64k", "-ac", "1", "-f", "mp3", "-"]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=config.FFMPEG_TIMEOUT)
        if result.returncode != 0:
            logger.error(
                "ffmpeg failed",
                extra={"stderr": result.stderr.decode(errors="replace")[-500:]},
            )
            return None
        data = result.stdout
        if not data:
            logger.error("ffmpeg produced empty output")
            return None
        if len(data) > config.AUDIO_MAX_SIZE:
            logger.warning(
                "Chapter too large for Telegram",
                extra={"size": len(data), "title": chapter_title},
            )
            return None
        return data
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out", extra={"url": m3u8_url[:80]})
        return None
    except FileNotFoundError:
        logger.error("ffmpeg not found — make sure it is installed")
        return None


def download_chapter_mp3(url: str) -> bytes | None:
    """Download a direct MP3 file and return bytes."""
    session = _get_session()
    try:
        resp = session.get(url, timeout=(15, 120), stream=True)
        resp.raise_for_status()
        buf = io.BytesIO()
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            buf.write(chunk)
            total += len(chunk)
            if total > config.AUDIO_MAX_SIZE:
                logger.warning("MP3 chapter exceeded size limit")
                return None
        return buf.getvalue()
    except requests.RequestException as e:
        logger.error("download_chapter_mp3 failed", exc_info=e)
        return None


# ────────────────────── High-level API ──────────────────────


def load_audiobook(slug: str) -> tuple[Audiobook | None, dict | None]:
    """
    Full pipeline: scrape page → call AJAX → return (Audiobook, media_data).

    media_data contains m3u8_url, items, srv — needed to download chapters.
    """
    page_data = get_book_page(slug)
    if not page_data or not page_data.get("book_id"):
        return None, None

    media = get_book_media(
        book_id=page_data["book_id"],
        security_ls_key=page_data["security_ls_key"],
        slug=slug,
    )

    chapters = []
    if media and media.get("items"):
        chapters = parse_chapters(media["items"])

    book = Audiobook(
        book_id=page_data["book_id"],
        slug=slug,
        title=page_data.get("title") or slug,
        author=page_data.get("author") or "",
        narrator=page_data.get("narrator", ""),
        description=page_data.get("description", ""),
        cover_url=page_data.get("cover_url", ""),
        chapters=chapters,
    )
    return book, media


def fetch_chapter_audio(slug: str, chapter_idx: int) -> tuple[bytes | None, str]:
    """
    Fetch audio bytes for a specific chapter.

    Re-fetches AJAX data every call (HLS URLs are time-limited).
    Returns (mp3_bytes, chapter_title).
    """
    _, media = load_audiobook(slug)
    if not media:
        return None, ""

    items = media.get("items", [])
    m3u8_url = media.get("m3u8_url", "")

    chapter_title = f"Глава {chapter_idx + 1}"
    time_offset = 0
    duration_sec = 0

    if chapter_idx < len(items):
        item = items[chapter_idx]
        if isinstance(item, dict):
            chapter_title = item.get("title", chapter_title)
            time_offset = int(float(item.get("time_from_start", 0)))
            duration_sec = int(float(item.get("duration", 0)))

    if not m3u8_url:
        logger.error("No m3u8_url for chapter download", extra={"slug": slug, "idx": chapter_idx})
        return None, chapter_title

    data = download_chapter_hls(
        m3u8_url,
        chapter_title=chapter_title,
        time_offset=time_offset,
        duration_sec=duration_sec,
    )
    return data, chapter_title
