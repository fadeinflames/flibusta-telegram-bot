"""akniga.org client — scraping, AJAX, AES crypto, HLS/MP3 download."""

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from src import config
from src.custom_logging import get_logger

logger = get_logger(__name__)

# ────────────────────── Constants ──────────────────────

SITE = config.AKNIGA_SITE
AJAX_KEY = config.AKNIGA_AJAX_KEY

_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({"User-Agent": config.USER_AGENT})
    return _SESSION


# ────────────────────── Data models ──────────────────────


@dataclass
class AudiobookChapter:
    index: int
    title: str
    duration_sec: int = 0


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
# akniga.org uses CryptoJS.AES with a passphrase — key derived via MD5 KDF,
# same as OpenSSL's EVP_BytesToKey with MD5 and 1 iteration.


def _evp_kdf(password: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """Derive 32-byte key and 16-byte IV from password + salt using MD5 KDF."""
    d = b""
    d_i = b""
    while len(d) < 48:
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:32], d[32:48]


def cryptojs_encrypt(plaintext: str, passphrase: str = AJAX_KEY) -> str:
    """Encrypt plaintext with CryptoJS AES (passphrase-based, JSON output format)."""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    salt = os.urandom(8)
    key, iv = _evp_kdf(passphrase.encode(), salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(plaintext.encode(), AES.block_size))
    return json.dumps({"ct": base64.b64encode(ct).decode(), "iv": iv.hex(), "s": salt.hex()})


def cryptojs_decrypt(ciphertext_json: str, passphrase: str = AJAX_KEY) -> str:
    """Decrypt CryptoJS AES JSON-encoded ciphertext."""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    data = json.loads(ciphertext_json)
    salt = bytes.fromhex(data["s"])
    ct = base64.b64decode(data["ct"])
    iv = bytes.fromhex(data["iv"])
    key, _ = _evp_kdf(passphrase.encode(), salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ct), AES.block_size).decode()


# ────────────────────── HTML scraping ──────────────────────


def search_audiobooks(query: str, page: int = 1) -> list[dict]:
    """Search audiobooks on akniga.org. Returns list of dicts with basic metadata."""
    session = _get_session()
    params: dict = {"q": query}
    if page > 1:
        params["page"] = page
    url = f"{SITE}/search/"

    try:
        resp = session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # Try fallback URL format
        if e.response is not None and e.response.status_code == 404:
            try:
                fallback = f"{SITE}/?q={quote(query, safe='')}"
                resp = session.get(fallback, timeout=config.REQUEST_TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException as e2:
                logger.error("akniga search failed (fallback)", exc_info=e2, extra={"query": query})
                return []
        else:
            logger.error("akniga search failed", exc_info=e, extra={"query": query})
            return []
    except requests.RequestException as e:
        logger.error("akniga search failed", exc_info=e, extra={"query": query})
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    for item in soup.select("article.b-book"):
        try:
            slug_tag = item.select_one("a.b-book__name, h2.b-book__name a, .b-book__title a")
            if not slug_tag:
                continue
            href = slug_tag.get("href", "")
            slug = href.strip("/").split("/")[-1] if href else ""
            if not slug:
                continue

            title = slug_tag.get_text(strip=True)

            author_tag = item.select_one(".b-book__author a, .b-book__author")
            author = author_tag.get_text(strip=True) if author_tag else ""

            cover_tag = item.select_one("img.b-book__cover, img[src]")
            cover_url = cover_tag.get("src", "") if cover_tag else ""
            if cover_url and cover_url.startswith("/"):
                cover_url = SITE + cover_url

            book_id = item.get("data-bid", "")

            duration_tag = item.select_one(".b-book__duration, .b-book__time")
            duration = duration_tag.get_text(strip=True) if duration_tag else ""

            results.append({
                "book_id": book_id,
                "slug": slug,
                "title": title,
                "author": author,
                "cover_url": cover_url,
                "duration": duration,
            })
        except Exception as e:
            logger.warning("Failed to parse search result item", exc_info=e)
            continue

    return results


def get_book_page(slug: str) -> dict | None:
    """
    Fetch book page HTML and extract metadata + security key.
    Returns dict with: book_id, security_ls_key, title, author, narrator,
                       description, cover_url, cookies (for AJAX call).
    """
    session = _get_session()
    url = f"{SITE}/{slug}"

    try:
        resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("akniga get_book_page failed", exc_info=e, extra={"slug": slug})
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # book_id from <article data-bid="...">
    article = soup.select_one("article[data-bid]")
    if not article:
        logger.warning("No article[data-bid] found", extra={"slug": slug})
        return None
    book_id = article.get("data-bid", "")

    # LIVESTREET_SECURITY_KEY from inline <script>
    security_ls_key = ""
    key_match = re.search(r"LIVESTREET_SECURITY_KEY\s*=\s*['\"]([^'\"]+)['\"]", resp.text)
    if key_match:
        security_ls_key = key_match.group(1)

    # Metadata
    title_tag = soup.select_one("h1.b-book__name, .b-book__title h1, h1")
    title = title_tag.get_text(strip=True) if title_tag else slug.replace("-", " ").title()

    author = ""
    author_tag = soup.select_one(".b-book__author a, .b-book__author")
    if author_tag:
        author = author_tag.get_text(strip=True)

    narrator = ""
    for label_tag in soup.select(".b-book__about-item"):
        label_text = label_tag.get_text(" ", strip=True).lower()
        if "читает" in label_text or "чтец" in label_text or "исполнитель" in label_text:
            a_tag = label_tag.select_one("a")
            if a_tag:
                narrator = a_tag.get_text(strip=True)
            break

    description = ""
    desc_tag = soup.select_one(".b-book__description, .description__article-main")
    if desc_tag:
        description = desc_tag.get_text(" ", strip=True)[:500]

    cover_url = ""
    cover_tag = soup.select_one(".b-book__cover img, .b-book__image img")
    if cover_tag:
        src = cover_tag.get("src", "")
        cover_url = SITE + src if src.startswith("/") else src

    return {
        "book_id": book_id,
        "slug": slug,
        "security_ls_key": security_ls_key,
        "title": title,
        "author": author,
        "narrator": narrator,
        "description": description,
        "cover_url": cover_url,
        "cookies": dict(resp.cookies),
    }


# ────────────────────── AJAX: get media URLs ──────────────────────


def get_book_media(book_id: str, security_ls_key: str, cookies: dict) -> dict | None:
    """
    Call akniga.org AJAX endpoint to get audio URLs.
    Returns dict with: m3u8_url, items (list of chapters with file URLs), srv, key.
    """
    session = _get_session()
    ajax_url = f"{SITE}/ajax/b/{book_id}/"

    # Compute CryptoJS AES hash of the security key
    hash_payload = cryptojs_encrypt(json.dumps(security_ls_key))

    post_data = {
        "bid": book_id,
        "security_ls_key": security_ls_key,
        "hash": hash_payload,
    }

    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{SITE}/",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        resp = session.post(
            ajax_url,
            data=post_data,
            cookies=cookies,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("akniga AJAX call failed", exc_info=e, extra={"book_id": book_id})
        return None

    if not data or data.get("result") == "error":
        logger.warning("akniga AJAX returned error", extra={"book_id": book_id, "data": data})
        return None

    # Decrypt the audio URL
    m3u8_url = ""
    raw_res = data.get("res", "")
    if raw_res:
        try:
            m3u8_url = cryptojs_decrypt(raw_res)
            # Append version suffix if present
            version = data.get("version", 1)
            if version and int(version) > 1:
                m3u8_url += f"&v={version}"
        except Exception as e:
            logger.error("akniga decrypt res failed", exc_info=e)

    # Parse items (chapters)
    items = []
    raw_items = data.get("items", "[]")
    if isinstance(raw_items, str):
        try:
            raw_items = json.loads(raw_items)
        except json.JSONDecodeError:
            raw_items = []
    if isinstance(raw_items, list):
        items = raw_items

    return {
        "m3u8_url": m3u8_url,
        "items": items,
        "srv": data.get("srv", ""),
        "key": data.get("key", ""),
        "slug": data.get("slug", ""),
        "title": data.get("title", ""),
        "author": data.get("author", ""),
    }


# ────────────────────── Chapter list parsing ──────────────────────


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
            chapters.append(AudiobookChapter(index=i, title=title, duration_sec=duration_sec))
        else:
            chapters.append(AudiobookChapter(index=i, title=f"Глава {i + 1}"))
    return chapters


def get_chapter_direct_url(item: dict, srv: str, key: str) -> str:
    """
    Build direct MP3 URL for a chapter item (old/legacy format).
    For HLS books, returns empty string (use m3u8_url instead).
    """
    file_val = item.get("file", "")
    if not file_val:
        return ""
    # If it's already a full URL
    if file_val.startswith("http"):
        return file_val
    # Old format: srv + b/<book_id>/<key>/<file>
    if srv:
        return f"{srv}b/{file_val}"
    return ""


# ────────────────────── Audio download ──────────────────────


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h} ч {m} мин" if h else f"{m} мин"


def download_chapter_hls(m3u8_url: str, chapter_title: str = "") -> bytes | None:
    """
    Download a full HLS stream (single-chapter m3u8 or whole-book m3u8)
    and return MP3 bytes via ffmpeg pipe.
    """
    logger.info("Downloading HLS chapter", extra={"url": m3u8_url[:80]})
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", m3u8_url,
                "-vn",
                "-acodec", "libmp3lame",
                "-q:a", "4",
                "-f", "mp3",
                "-",
            ],
            capture_output=True,
            timeout=config.FFMPEG_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error(
                "ffmpeg failed",
                extra={"stderr": result.stderr.decode(errors="replace")[-500:]},
            )
            return None
        data = result.stdout
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
        logger.error("ffmpeg not found — install it in Dockerfile")
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


# ────────────────────── High-level: load audiobook ──────────────────────


def load_audiobook(slug: str) -> tuple[Audiobook | None, dict | None]:
    """
    Full pipeline: scrape page → call AJAX → return (Audiobook, media_data).
    media_data contains m3u8_url, items, srv, key — needed to download chapters.
    """
    page_data = get_book_page(slug)
    if not page_data or not page_data.get("book_id"):
        return None, None

    media = get_book_media(
        book_id=page_data["book_id"],
        security_ls_key=page_data["security_ls_key"],
        cookies=page_data["cookies"],
    )

    chapters = []
    if media and media.get("items"):
        chapters = parse_chapters(media["items"])

    book = Audiobook(
        book_id=page_data["book_id"],
        slug=slug,
        title=page_data.get("title") or (media or {}).get("title") or slug,
        author=page_data.get("author") or (media or {}).get("author") or "",
        narrator=page_data.get("narrator", ""),
        description=page_data.get("description", ""),
        cover_url=page_data.get("cover_url", ""),
        chapters=chapters,
    )
    return book, media


def fetch_chapter_audio(slug: str, chapter_idx: int) -> tuple[bytes | None, str]:
    """
    Convenience function: load book, find chapter URL, download and return
    (mp3_bytes, chapter_title). Re-fetches AJAX to get fresh signed URLs.
    """
    _, media = load_audiobook(slug)
    if not media:
        return None, ""

    items = media.get("items", [])
    m3u8_url = media.get("m3u8_url", "")
    srv = media.get("srv", "")
    key = media.get("key", "")

    chapter_title = f"Глава {chapter_idx + 1}"
    if chapter_idx < len(items):
        item = items[chapter_idx]
        chapter_title = item.get("title", chapter_title) if isinstance(item, dict) else chapter_title

        # Try direct URL first (old format books)
        direct_url = get_chapter_direct_url(item, srv, key) if isinstance(item, dict) else ""
        if direct_url:
            data = download_chapter_mp3(direct_url)
            if data:
                return data, chapter_title

    # Fall back to HLS (new format — whole-book m3u8, chapter selection not supported per-chapter)
    # For now: download the whole stream if only 1 chapter, otherwise use m3u8 directly
    if m3u8_url:
        data = download_chapter_hls(m3u8_url, chapter_title)
        return data, chapter_title

    return None, chapter_title


def format_duration_from_chapters(chapters: list[AudiobookChapter]) -> str:
    """Format total duration string from chapter list."""
    total = sum(c.duration_sec for c in chapters)
    if total == 0:
        return ""
    return _format_duration(total)
