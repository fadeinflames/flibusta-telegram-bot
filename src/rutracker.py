"""RuTracker scraper: login, search audiobooks, download torrent files."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from src.config import RUTRACKER_CATEGORY, RUTRACKER_PASSWORD, RUTRACKER_USERNAME
from src import rt_cache

logger = logging.getLogger(__name__)

_BASE = "https://rutracker.org/forum"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) "
        "Gecko/20100101 Firefox/120.0"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

# Singleton session — login once, reuse across requests
_session: requests.Session | None = None

_SERIES_PATTERNS = [
    r"\bserial\b",
    r"\bсезон\b",
    r"\bсерии\b",
    r"\bs\d{1,2}e\d{1,2}\b",
    r"\bseason\b",
    r"\bepisodes?\b",
]
_BOOK_PATTERNS = [
    r"\bаудиокниг",
    r"\bкниг",
    r"\bроман\b",
    r"\bповест",
    r"\bрассказ",
    r"\bbook\b",
]


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def get_session() -> requests.Session:
    """Return an authenticated session, logging in if needed."""
    global _session
    if _session is None:
        _session = _new_session()
        _login(_session)
    return _session


def _login(s: requests.Session) -> None:
    if not RUTRACKER_USERNAME or not RUTRACKER_PASSWORD:
        raise RuntimeError("RUTRACKER_USERNAME / RUTRACKER_PASSWORD not configured")
    resp = s.post(
        f"{_BASE}/login.php",
        data={
            "login_username": RUTRACKER_USERNAME,
            "login_password": RUTRACKER_PASSWORD,
            "login": "вход",
        },
        allow_redirects=True,
        timeout=15,
    )
    resp.raise_for_status()
    if "logout" not in resp.text.lower() and "выйти" not in resp.text.lower():
        raise RuntimeError("RuTracker login failed — check credentials")
    logger.info("RuTracker: logged in as %s", RUTRACKER_USERNAME)


def reset_session() -> None:
    """Force re-login on next request (e.g. after session expiry)."""
    global _session
    _session = None


@dataclass
class RTopic:
    topic_id: str
    title: str
    size: str
    seeds: int
    leeches: int = 0
    forum_name: str = ""
    registered: str = ""


@dataclass
class RTopicFiles:
    topic_id: str
    title: str
    description: str
    forum_name: str = ""
    topic_url: str = ""
    files: list[str] = field(default_factory=list)  # filenames from torrent
    audio_files: list[str] = field(default_factory=list)  # mp3/m4b/flac etc.


@dataclass
class FileEntry:
    filename: str
    size_bytes: int
    index_in_torrent: int


_AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".ogg", ".flac", ".opus", ".aac", ".wav"}


def _looks_like_series(title: str) -> bool:
    text = (title or "").lower()
    return any(re.search(pat, text) for pat in _SERIES_PATTERNS)


def _looks_like_book(title: str) -> bool:
    text = (title or "").lower()
    if any(re.search(pat, text) for pat in _BOOK_PATTERNS):
        return True
    # Typical audiobook title format: "Автор - Название"
    return " - " in text


def search(query: str, limit: int = 10) -> list[RTopic]:
    """Search RuTracker audiobook categories.  Returns up to *limit* results."""
    # Check search cache
    cache_key = rt_cache.search_key(f"{query}:{limit}")
    cached = rt_cache.get(cache_key)
    if cached:
        logger.debug("search(%r): cache hit (%d results)", query, len(cached))
        return [RTopic(**r) for r in cached]

    s = get_session()
    try:
        resp = s.post(
            f"{_BASE}/tracker.php",
            data={"nm": query, "c": RUTRACKER_CATEGORY},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        # Session may have expired — retry once
        logger.warning("RuTracker search error, resetting session: %s", exc)
        reset_session()
        s = get_session()
        resp = s.post(
            f"{_BASE}/tracker.php",
            data={"nm": query, "c": RUTRACKER_CATEGORY},
            timeout=15,
        )
        resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "lxml")
    rows = soup.select("tr.tCenter.hl-tr")
    results: list[RTopic] = []

    for row in rows[:80]:
        link = row.select_one("a.tLink")
        if not link:
            continue
        title = link.get_text(strip=True)
        if _looks_like_series(title):
            continue
        if not _looks_like_book(title):
            continue
        href = link.get("href", "")
        m = re.search(r"t=(\d+)", href)
        if not m:
            continue
        topic_id = m.group(1)

        size_td = row.select_one("td.tor-size")
        size = size_td.get_text(strip=True).split()[0] if size_td else "?"

        # Seeds / leechers (columns on tracker; «пиры» в разговорной речи часто = личи + сиды)
        seeds_span = row.select_one("b.seedmed, span.seedmed")
        try:
            seeds = int(seeds_span.get_text(strip=True)) if seeds_span else 0
        except ValueError:
            seeds = 0

        leech_span = row.select_one("b.leechmed, span.leechmed, b.leechMed, span.leechMed")
        if not leech_span:
            for td in row.select("td"):
                cls = " ".join(td.get("class") or [])
                if "leech" in cls.lower():
                    leech_span = td.select_one("b, span")
                    break
        try:
            leeches = int(leech_span.get_text(strip=True)) if leech_span else 0
        except ValueError:
            leeches = 0

        # Keep only releases where torrent actually contains audio files.
        try:
            if not get_topic_files(topic_id):
                continue
        except Exception:
            continue

        results.append(
            RTopic(topic_id=topic_id, title=title, size=size, seeds=seeds, leeches=leeches)
        )
        if len(results) >= limit:
            break

    # Сверху — раздачи с большим числом пиров в поиске (сиды + личи)
    results.sort(key=lambda t: (t.seeds + t.leeches, t.seeds), reverse=True)

    # Cache search results
    if results:
        rt_cache.set(
            cache_key,
            [{"topic_id": r.topic_id, "title": r.title, "size": r.size,
              "seeds": r.seeds, "leeches": r.leeches, "forum_name": r.forum_name}
             for r in results],
            rt_cache.TTL_SEARCH,
        )

    return results


def _clean_topic_description(raw: str, max_len: int = 3500) -> str:
    """Normalize whitespace; cap length for Telegram."""
    if not raw:
        return ""
    text = re.sub(r"[ \t]+\n", "\n", raw)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def get_topic_info(topic_id: str) -> RTopicFiles:
    """Fetch topic page: full title, forum, long description (first post body)."""
    # Check cache first
    cache_key = rt_cache.topic_info_key(topic_id)
    cached = rt_cache.get(cache_key)
    if cached:
        logger.debug("get_topic_info(%s): cache hit", topic_id)
        return RTopicFiles(**cached)

    s = get_session()
    topic_url = f"{_BASE}/viewtopic.php?t={topic_id}"
    resp = s.get(topic_url, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "lxml")
    title_tag = soup.select_one("h1.maintitle, a.maintitle, #topic-title")
    title = title_tag.get_text(strip=True) if title_tag else f"Топик {topic_id}"

    forum_name = ""
    # Breadcrumb: last link before topic is often the subforum
    for a in soup.select('a[href*="viewforum.php"]'):
        fn = a.get_text(strip=True)
        if fn and len(fn) < 120:
            forum_name = fn
    # Fallback: nav row
    if not forum_name:
        nav = soup.select_one("td.nav, p.nav")
        if nav:
            links = nav.select("a")
            if links:
                forum_name = links[-1].get_text(strip=True)[:120]

    post_body = soup.select_one("div.post_body")
    if post_body:
        # Remove quote blocks noise (optional)
        for tag in post_body.select("div.sp-wrap, script, style"):
            tag.decompose()
        description = _clean_topic_description(post_body.get_text("\n", strip=True))
    else:
        description = ""

    result = RTopicFiles(
        topic_id=topic_id,
        title=title,
        description=description,
        forum_name=forum_name,
        topic_url=topic_url,
    )

    # Cache the result
    rt_cache.set(cache_key, {
        "topic_id": result.topic_id,
        "title": result.title,
        "description": result.description,
        "forum_name": result.forum_name,
        "topic_url": result.topic_url,
    }, rt_cache.TTL_TOPIC_INFO)

    return result


def download_torrent(topic_id: str) -> bytes:
    """Download the .torrent file bytes for a given topic."""
    s = get_session()
    resp = s.get(f"{_BASE}/dl.php?t={topic_id}", timeout=30)
    resp.raise_for_status()
    if b"application/x-bittorrent" not in resp.headers.get("content-type", "").encode():
        # Maybe session expired
        logger.warning("RuTracker DL unexpected content-type, resetting session")
        reset_session()
        s = get_session()
        resp = s.get(f"{_BASE}/dl.php?t={topic_id}", timeout=30)
        resp.raise_for_status()
    return resp.content


def _bdecode(data: bytes, idx: int = 0):
    ch = data[idx : idx + 1]
    if ch == b"i":
        end = data.index(b"e", idx)
        return int(data[idx + 1 : end]), end + 1
    if ch == b"l":
        idx += 1
        out = []
        while data[idx : idx + 1] != b"e":
            val, idx = _bdecode(data, idx)
            out.append(val)
        return out, idx + 1
    if ch == b"d":
        idx += 1
        out = {}
        while data[idx : idx + 1] != b"e":
            key, idx = _bdecode(data, idx)
            val, idx = _bdecode(data, idx)
            if isinstance(key, bytes):
                key = key.decode("utf-8", errors="ignore")
            out[key] = val
        return out, idx + 1
    if ch.isdigit():
        colon = data.index(b":", idx)
        ln = int(data[idx:colon])
        start = colon + 1
        end = start + ln
        return data[start:end], end
    raise ValueError("Invalid bencode payload")


def get_topic_files(topic_id: str) -> list[FileEntry]:
    """Return audio files from topic torrent metadata."""
    # Check cache first
    cache_key = rt_cache.topic_files_key(topic_id)
    cached = rt_cache.get(cache_key)
    if cached:
        logger.debug("get_topic_files(%s): cache hit", topic_id)
        return [FileEntry(**f) for f in cached]

    torrent = download_torrent(topic_id)
    root, _ = _bdecode(torrent)
    info = root.get("info", {}) if isinstance(root, dict) else {}
    entries: list[FileEntry] = []

    if "files" in info:
        files = info.get("files") or []
        for idx, item in enumerate(files, start=1):
            path_parts = item.get("path", [])
            parts = []
            for p in path_parts:
                if isinstance(p, bytes):
                    parts.append(p.decode("utf-8", errors="ignore"))
                else:
                    parts.append(str(p))
            name = "/".join(parts).strip("/") or f"file_{idx}"
            size = int(item.get("length", 0) or 0)
            entries.append(FileEntry(filename=name, size_bytes=size, index_in_torrent=idx))
    else:
        name = info.get("name", b"")
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="ignore")
        size = int(info.get("length", 0) or 0)
        entries.append(FileEntry(filename=str(name or "audio"), size_bytes=size, index_in_torrent=1))

    audio_only = []
    for e in entries:
        lower = e.filename.lower()
        if any(lower.endswith(ext) for ext in _AUDIO_EXTENSIONS):
            audio_only.append(e)
    # Торрент часто отдаёт файлы не по порядку глав — сортируем по номеру в имени
    audio_only.sort(key=lambda e: _audio_sort_key(e.filename))

    # Cache the result (file lists are immutable)
    rt_cache.set(
        cache_key,
        [{"filename": e.filename, "size_bytes": e.size_bytes, "index_in_torrent": e.index_in_torrent} for e in audio_only],
        rt_cache.TTL_TOPIC_FILES,
    )

    return audio_only


def _audio_sort_key(filename: str) -> tuple:
    """Ключ сортировки: номер главы/части из имени файла, затем имя."""
    tail = Path(filename.replace("\\", "/")).name
    stem = Path(tail).stem
    m = re.search(r"(?i)глава\s*[:#]?\s*(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    m = re.search(r"(?i)часть\s*[:#]?\s*(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    m = re.search(r"(?i)(?:cd|диск)\s*0*(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    m = re.search(r"(?i)track\s*0*(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    m = re.search(r"(?i)chapter\s*0*(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    m = re.match(r"^0*(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    return (1, 0, stem.lower())
