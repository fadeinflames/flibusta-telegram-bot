"""RuTracker scraper: login, search audiobooks, download torrent files."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.config import RUTRACKER_FORUMS, RUTRACKER_PASSWORD, RUTRACKER_USERNAME

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
_session: Optional[requests.Session] = None


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
    forum_name: str = ""
    registered: str = ""


@dataclass
class RTopicFiles:
    topic_id: str
    title: str
    description: str
    files: list[str] = field(default_factory=list)  # filenames from torrent
    audio_files: list[str] = field(default_factory=list)  # mp3/m4b/flac etc.


@dataclass
class FileEntry:
    filename: str
    size_bytes: int
    index_in_torrent: int


_AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".ogg", ".flac", ".opus", ".aac", ".wav"}


def search(query: str, limit: int = 10) -> list[RTopic]:
    """Search RuTracker audiobook categories.  Returns up to *limit* results."""
    s = get_session()
    try:
        resp = s.post(
            f"{_BASE}/tracker.php",
            data={"nm": query, "f": RUTRACKER_FORUMS},
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
            data={"nm": query, "f": RUTRACKER_FORUMS},
            timeout=15,
        )
        resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "lxml")
    rows = soup.select("tr.tCenter.hl-tr")
    results: list[RTopic] = []

    for row in rows[:limit]:
        link = row.select_one("a.tLink")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        m = re.search(r"t=(\d+)", href)
        if not m:
            continue
        topic_id = m.group(1)

        size_td = row.select_one("td.tor-size")
        size = size_td.get_text(strip=True).split()[0] if size_td else "?"

        # Seeds: look for seedmed span/td
        seeds_span = row.select_one("b.seedmed, span.seedmed")
        try:
            seeds = int(seeds_span.get_text(strip=True)) if seeds_span else 0
        except ValueError:
            seeds = 0

        results.append(RTopic(topic_id=topic_id, title=title, size=size, seeds=seeds))

    return results


def get_topic_info(topic_id: str) -> RTopicFiles:
    """Fetch topic page, parse description and file list from torrent."""
    s = get_session()
    resp = s.get(f"{_BASE}/viewtopic.php?t={topic_id}", timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "lxml")
    title_tag = soup.select_one("h1.maintitle, #topic-title")
    title = title_tag.get_text(strip=True) if title_tag else f"Топик {topic_id}"

    post_body = soup.select_one("div.post_body")
    description = post_body.get_text("\n", strip=True)[:800] if post_body else ""

    return RTopicFiles(topic_id=topic_id, title=title, description=description)


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
    return audio_only
