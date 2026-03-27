"""Background torrent downloader using aria2c subprocess.

Maintains a simple in-memory + DB queue.  Each task downloads a full
torrent into a per-topic directory, then notifies the requesting user
via Telegram.

Requires: aria2c installed on the system (apt-get install aria2 / brew install aria2).
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src import database as db
from src import rutracker
from src.config import RUTRACKER_DOWNLOAD_DIR

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".ogg", ".flac", ".opus", ".aac"}


@dataclass
class DownloadTask:
    task_id: int
    user_id: int
    chat_id: int
    topic_id: str
    title: str
    file_index: int | None = None
    filename: str = ""
    file_size: int = 0
    seeders: int = 0
    topic_size: str = ""
    created_at: float = field(default_factory=time.time)


class RutrackerDownloader:
    """Singleton background downloader.  Call `start(app)` once at bot startup."""

    _instance: Optional["RutrackerDownloader"] = None

    def __new__(cls) -> "RutrackerDownloader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._app: Optional["Application"] = None
        self._queue: asyncio.Queue[DownloadTask] = asyncio.Queue()
        self._running = False
        self._initialised = True

    def start(self, app: "Application") -> None:
        self._app = app
        if not self._running:
            self._running = True
            asyncio.get_event_loop().create_task(self._worker())
            logger.info("RutrackerDownloader: worker started")

    def enqueue(
        self,
        user_id: int,
        chat_id: int,
        topic_id: str,
        title: str,
        file_index: int | None = None,
        filename: str = "",
        file_size: int = 0,
        seeders: int = 0,
        topic_size: str = "",
    ) -> int:
        """Add a download to the queue.  Returns the task DB id."""
        task_id = db.rt_enqueue(
            user_id,
            chat_id,
            topic_id,
            title,
            file_index=file_index,
            filename=filename,
            file_size=file_size,
        )
        task = DownloadTask(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            topic_id=topic_id,
            title=title,
            file_index=file_index,
            filename=filename,
            file_size=file_size,
            seeders=seeders,
            topic_size=topic_size,
        )
        self._queue.put_nowait(task)
        logger.info("Enqueued torrent download: topic=%s user=%s", topic_id, user_id)
        return task_id

    async def _worker(self) -> None:
        while True:
            task = await self._queue.get()
            try:
                await self._process(task)
            except Exception as exc:
                logger.exception("Download task %s failed: %s", task.task_id, exc)
                db.rt_update_status(task.task_id, "failed")
                await self._notify(task.chat_id, f"⚠️ Ошибка скачивания «{task.title}»: {exc}")
            finally:
                self._queue.task_done()

    async def _process(self, task: DownloadTask) -> None:
        started_at = time.time()
        db.rt_update_status(task.task_id, "downloading")
        logger.info("Downloading torrent topic=%s", task.topic_id)
        await self._notify(
            task.chat_id,
            "🚀 <b>Задача запущена</b>\n"
            f"ID: #{task.task_id}\n"
            f"Сиды: {task.seeders}\n"
            f"Размер релиза: {task.topic_size or '?'}\n"
            f"Файл: <code>{task.filename or 'не указан'}</code>",
        )

        # Download .torrent bytes
        torrent_bytes = await asyncio.get_event_loop().run_in_executor(
            None, rutracker.download_torrent, task.topic_id
        )

        # Save torrent file to temp
        dest_dir = Path(RUTRACKER_DOWNLOAD_DIR) / task.topic_id
        # Ensure we don't mix files from previous attempts for this topic.
        shutil.rmtree(dest_dir, ignore_errors=True)
        dest_dir.mkdir(parents=True, exist_ok=True)

        torrent_path = dest_dir / f"{task.topic_id}.torrent"
        torrent_path.write_bytes(torrent_bytes)

        # Run aria2c
        ok = await asyncio.get_event_loop().run_in_executor(
            None, _aria2c_download, str(torrent_path), str(dest_dir), task.file_index
        )
        torrent_path.unlink(missing_ok=True)

        if not ok:
            raise RuntimeError("aria2c exited with non-zero code")

        # Collect audio files (sorted by filename -> chapter order for numbered tracks)
        audio_files = sorted(
            p for p in dest_dir.rglob("*") if p.suffix.lower() in AUDIO_EXTENSIONS
        )
        if task.filename:
            target_name = Path(task.filename).name.lower()
            selected = [p for p in audio_files if p.name.lower() == target_name]
            if selected:
                audio_files = selected[:1]
            elif audio_files:
                # Fallback: if exact name is missing, send just one file, never a batch.
                audio_files = audio_files[:1]
        if not audio_files:
            raise RuntimeError("No audio files found after download")

        db.rt_update_status(task.task_id, "done")
        logger.info("Downloaded %d audio files for topic %s", len(audio_files), task.topic_id)
        elapsed = max(1, int(time.time() - started_at))
        await self._notify(task.chat_id, f"📥 Скачивание завершено за {elapsed} сек. Готовлю отправку…")

        # Send to user
        await self._send_audio_files(task, audio_files)

    async def _send_audio_files(
        self, task: DownloadTask, audio_files: list[Path]
    ) -> None:
        if self._app is None:
            return
        bot = self._app.bot
        count = len(audio_files)
        await self._notify(task.chat_id, f"✅ <b>{task.title}</b>\n\nСкачалось {count} файл(ов). Отправляю по порядку...")
        for idx, fpath in enumerate(audio_files, 1):
            send_path = fpath
            size_mb = send_path.stat().st_size / 1024 / 1024
            if size_mb > 49:
                recompressed = await asyncio.get_event_loop().run_in_executor(
                    None, _compress_for_telegram, str(fpath)
                )
                if recompressed:
                    send_path = Path(recompressed)
                    size_mb = send_path.stat().st_size / 1024 / 1024
                if size_mb > 49:
                    await self._notify(
                        task.chat_id,
                        f"⚠️ Файл {fpath.name} слишком большой ({size_mb:.0f} МБ), не удалось ужать до лимита",
                    )
                    continue
            try:
                with open(send_path, "rb") as f:
                    await bot.send_audio(
                        chat_id=task.chat_id,
                        audio=f,
                        title=send_path.stem,
                        filename=send_path.name,
                        caption=f"[{idx}/{count}] {task.title}" if count > 1 else None,
                    )
            except Exception as exc:
                logger.warning("Failed to send %s: %s", send_path.name, exc)
                await self._notify(task.chat_id, f"⚠️ Не удалось отправить {send_path.name}: {exc}")
            finally:
                if send_path != fpath:
                    send_path.unlink(missing_ok=True)

        # Cleanup
        shutil.rmtree(str(dest_dir_for_cleanup(task.topic_id)), ignore_errors=True)

    async def _notify(self, chat_id: int, text: str) -> None:
        if self._app is None:
            return
        try:
            await self._app.bot.send_message(
                chat_id=chat_id, text=text, parse_mode="HTML"
            )
        except Exception as exc:
            logger.warning("Notify failed: %s", exc)


def dest_dir_for_cleanup(topic_id: str) -> Path:
    return Path(RUTRACKER_DOWNLOAD_DIR) / topic_id


def _aria2c_download(torrent_path: str, dest_dir: str, file_index: int | None = None) -> bool:
    """Run aria2c synchronously.  Returns True on success."""
    aria2c = shutil.which("aria2c")
    if not aria2c:
        raise RuntimeError(
            "aria2c not found. Install: apt-get install aria2 / brew install aria2"
        )
    cmd = [
        aria2c,
        "--dir", dest_dir,
        "--seed-time=0",          # don't seed after download
        "--max-connection-per-server=4",
        "--split=4",
        "--file-allocation=none",
        "--console-log-level=warn",
        "--quiet=true",
    ]
    if file_index is not None:
        cmd.extend(["--select-file", str(file_index)])
    cmd.append(torrent_path)
    logger.info("aria2c cmd: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=7200)  # 2h max
    return result.returncode == 0


def _compress_for_telegram(path: str) -> str | None:
    """Try to re-encode audio to fit Telegram send_audio limit."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    src = Path(path)
    out = src.with_name(f"{src.stem}.tg.mp3")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "22050",
        "-b:a",
        "56k",
        str(out),
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    if result.returncode != 0 or not out.exists():
        return None
    return str(out)


# Module-level singleton
downloader = RutrackerDownloader()
