"""Background torrent downloader using aria2c subprocess.

Maintains a simple in-memory + DB queue.  Each task downloads a full
torrent into a per-topic directory, then notifies the requesting user
via Telegram.

Requires: aria2c installed on the system (apt-get install aria2 / brew install aria2).
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

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
        self._cancelled_ids: Set[int] = set()
        self._active_task_id: Optional[int] = None
        self._active_proc: Optional[asyncio.subprocess.Process] = None
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
        logger.info(
            "rt enqueue: task_id=%s user=%s chat=%s topic=%s file_index=%s filename=%s qsize=%s",
            task_id,
            user_id,
            chat_id,
            topic_id,
            file_index,
            filename,
            self._queue.qsize(),
        )
        return task_id

    def cancel_task(self, task_id: int) -> tuple[bool, str]:
        """Mark task as cancelled; kill aria2c if this task is active. Admin-only via bot."""
        row = db.rt_get_task(task_id)
        if not row:
            return False, "Задача не найдена"
        st = row.get("status", "")
        if st in ("done", "failed", "cancelled"):
            return False, f"Задача уже в статусе «{st}»"
        db.rt_update_status(task_id, "cancelled")
        self._cancelled_ids.add(task_id)
        if self._active_task_id == task_id and self._active_proc:
            try:
                self._active_proc.terminate()
            except ProcessLookupError:
                pass
            logger.info("rt cancel: terminated aria2c for task_id=%s", task_id)
        return True, "Отмена запрошена"

    def delete_task_files(self, topic_id: str) -> None:
        """Remove downloaded data for a topic from disk."""
        path = dest_dir_for_cleanup(topic_id)
        shutil.rmtree(str(path), ignore_errors=True)
        logger.info("rt delete: removed dir %s", path)

    def delete_task(self, task_id: int) -> tuple[bool, str]:
        """Remove DB row, kill active download, wipe files on disk. Admin-only via bot."""
        row = db.rt_get_task(task_id)
        if not row:
            return False, "Задача не найдена"
        topic_id = row["topic_id"]
        self._cancelled_ids.add(task_id)
        if self._active_task_id == task_id and self._active_proc:
            try:
                self._active_proc.terminate()
            except ProcessLookupError:
                pass
            logger.info("rt delete: terminated aria2c for task_id=%s", task_id)
        db.rt_delete_task(task_id)
        self.delete_task_files(topic_id)
        self._cancelled_ids.discard(task_id)
        return True, "Удалено"

    def delete_all_tasks(self) -> tuple[bool, str]:
        """Clear entire queue: kill active aria2c, delete all DB rows, wipe all topic dirs."""
        topic_ids = db.rt_all_topic_ids()
        if self._active_proc:
            try:
                self._active_proc.terminate()
            except ProcessLookupError:
                pass
            logger.info("rt delete_all: terminated active aria2c")
        self._active_task_id = None
        self._active_proc = None
        self._cancelled_ids.clear()
        deleted = db.rt_delete_all_rows()
        for tid in topic_ids:
            self.delete_task_files(tid)
        return True, f"Удалено записей: {deleted}, каталогов раздач: {len(topic_ids)}"

    async def _handle_cancelled_mid_task(self, task: DownloadTask) -> None:
        self._cancelled_ids.discard(task.task_id)
        if db.rt_get_task(task.task_id):
            db.rt_update_status(task.task_id, "cancelled")
        self.delete_task_files(task.topic_id)
        await self._notify(
            task.chat_id,
            f"⏹️ <b>Задача #{task.task_id} отменена</b>\n«{html.escape(task.title)}»",
        )

    async def _worker(self) -> None:
        while True:
            task = await self._queue.get()
            logger.info("rt worker: picked task_id=%s topic=%s", task.task_id, task.topic_id)
            try:
                await self._process(task)
            except Exception as exc:
                if task.task_id in self._cancelled_ids:
                    self._cancelled_ids.discard(task.task_id)
                    logger.info("Download task %s aborted (cancelled)", task.task_id)
                else:
                    logger.exception("Download task %s failed: %s", task.task_id, exc)
                    db.rt_update_status(task.task_id, "failed")
                    await self._notify(task.chat_id, f"⚠️ Ошибка скачивания «{task.title}»: {exc}")
            finally:
                self._queue.task_done()

    async def _process(self, task: DownloadTask) -> None:
        row = db.rt_get_task(task.task_id)
        if not row:
            logger.info("rt process: task_id=%s missing from DB (deleted), skip", task.task_id)
            return
        if row.get("status") == "cancelled" or task.task_id in self._cancelled_ids:
            self._cancelled_ids.discard(task.task_id)
            await self._notify(
                task.chat_id,
                f"⏹️ <b>Задача #{task.task_id} отменена</b>\n«{html.escape(task.title)}»",
            )
            return

        started_at = time.time()
        db.rt_update_status(task.task_id, "downloading")
        logger.info(
            "rt process: start task_id=%s topic=%s file_index=%s filename=%s",
            task.task_id,
            task.topic_id,
            task.file_index,
            task.filename,
        )
        status_message = await self._notify(
            task.chat_id,
            "🚀 <b>Задача запущена</b>\n"
            f"ID: #{task.task_id}\n"
            f"Сиды: {task.seeders}\n"
            f"Размер релиза: {task.topic_size or '?'}\n"
            f"Файл: <code>{html.escape(task.filename or 'не указан')}</code>\n"
            "Статус: подготовка…",
        )

        # Download .torrent bytes
        torrent_bytes = await asyncio.get_event_loop().run_in_executor(
            None, rutracker.download_torrent, task.topic_id
        )
        logger.info("rt process: downloaded torrent bytes=%s task_id=%s", len(torrent_bytes), task.task_id)

        # Save torrent file to temp
        dest_dir = Path(RUTRACKER_DOWNLOAD_DIR) / task.topic_id
        # Ensure we don't mix files from previous attempts for this topic.
        shutil.rmtree(dest_dir, ignore_errors=True)
        dest_dir.mkdir(parents=True, exist_ok=True)

        torrent_path = dest_dir / f"{task.topic_id}.torrent"
        torrent_path.write_bytes(torrent_bytes)

        if task.task_id in self._cancelled_ids:
            await self._handle_cancelled_mid_task(task)
            return
        if not db.rt_get_task(task.task_id):
            self.delete_task_files(task.topic_id)
            logger.info("rt process: task_id=%s deleted before aria2, skip", task.task_id)
            return

        # Run aria2c
        ok = await self._aria2c_download_with_progress(
            task=task,
            torrent_path=str(torrent_path),
            dest_dir=str(dest_dir),
            status_message_id=status_message.message_id if status_message else None,
        )
        torrent_path.unlink(missing_ok=True)

        if not ok:
            if not db.rt_get_task(task.task_id):
                self.delete_task_files(task.topic_id)
                logger.info("rt process: task_id=%s removed during download", task.task_id)
                return
            if task.task_id in self._cancelled_ids:
                await self._handle_cancelled_mid_task(task)
                return
            logger.error("rt process: aria2c failed task_id=%s topic=%s", task.task_id, task.topic_id)
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
            logger.error("rt process: no audio files after download task_id=%s topic=%s", task.task_id, task.topic_id)
            raise RuntimeError("No audio files found after download")

        db.rt_update_status(task.task_id, "done")
        logger.info("Downloaded %d audio files for topic %s", len(audio_files), task.topic_id)
        elapsed = max(1, int(time.time() - started_at))
        await self._edit_status(
            task.chat_id,
            status_message.message_id if status_message else None,
            "✅ <b>Скачивание завершено</b>\n"
            f"ID: #{task.task_id}\n"
            f"Время: {elapsed} сек\n"
            "Статус: готовлю отправку…",
        )

        # Send to user
        await self._send_audio_files(task, audio_files)

    async def _send_audio_files(
        self, task: DownloadTask, audio_files: list[Path]
    ) -> None:
        if self._app is None:
            return
        if not db.rt_get_task(task.task_id):
            logger.info("rt send: task_id=%s removed from DB, skip send", task.task_id)
            shutil.rmtree(str(dest_dir_for_cleanup(task.topic_id)), ignore_errors=True)
            return
        bot = self._app.bot
        count = len(audio_files)
        await self._notify(task.chat_id, f"✅ <b>{task.title}</b>\n\nСкачалось {count} файл(ов). Отправляю по порядку...")
        for idx, fpath in enumerate(audio_files, 1):
            logger.info("rt send: task_id=%s file=%s idx=%s/%s", task.task_id, fpath.name, idx, count)
            send_path = fpath
            size_mb = send_path.stat().st_size / 1024 / 1024
            if size_mb > 49:
                logger.warning(
                    "rt send: file too big task_id=%s file=%s size_mb=%.2f; try recompress",
                    task.task_id,
                    fpath.name,
                    size_mb,
                )
                recompressed = await asyncio.get_event_loop().run_in_executor(
                    None, _compress_for_telegram, str(fpath)
                )
                if recompressed:
                    send_path = Path(recompressed)
                    size_mb = send_path.stat().st_size / 1024 / 1024
                    logger.info(
                        "rt send: recompress ok task_id=%s file=%s new_file=%s size_mb=%.2f",
                        task.task_id,
                        fpath.name,
                        send_path.name,
                        size_mb,
                    )
                if size_mb > 49:
                    logger.error(
                        "rt send: still too big task_id=%s file=%s size_mb=%.2f",
                        task.task_id,
                        send_path.name,
                        size_mb,
                    )
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
        logger.info("rt cleanup: task_id=%s topic=%s", task.task_id, task.topic_id)

    async def _notify(self, chat_id: int, text: str):
        if self._app is None:
            return None
        try:
            return await self._app.bot.send_message(
                chat_id=chat_id, text=text, parse_mode="HTML"
            )
        except Exception as exc:
            logger.warning("Notify failed: %s", exc)
            return None

    async def _edit_status(self, chat_id: int, message_id: int | None, text: str) -> None:
        if self._app is None or message_id is None:
            return
        try:
            await self._app.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception:
            # Editing can fail if message was deleted/too old; ignore.
            pass

    async def _aria2c_disk_progress_loop(
        self,
        task: DownloadTask,
        torrent_path: Path,
        dest_dir: Path,
        status_message_id: int | None,
        done: asyncio.Event,
    ) -> None:
        """Poll bytes on disk so Telegram shows real progress (not fragile aria2 stdout parsing)."""
        if status_message_id is None:
            while not done.is_set():
                try:
                    await asyncio.wait_for(done.wait(), timeout=2.0)
                    break
                except asyncio.TimeoutError:
                    if task.task_id in self._cancelled_ids:
                        break
            return

        expected = task.file_size or 0
        last_size = 0
        last_t = time.time()
        started = last_t
        poll_s = 1.8

        while not done.is_set():
            if task.task_id in self._cancelled_ids:
                break

            def _measure() -> int:
                return _dir_bytes_excluding_torrent(dest_dir, torrent_path)

            size = await asyncio.get_running_loop().run_in_executor(None, _measure)
            now = time.time()
            elapsed = int(now - started)
            dt = now - last_t
            speed_bps = (size - last_size) / dt if dt > 0.4 and size >= last_size else 0.0

            if size == 0 and elapsed < 25:
                phase = "🔄 <b>Подключение к пирам</b> — метаданные и поиск сидов…"
            elif size == 0:
                phase = (
                    "🔄 <b>Ожидание данных</b> — на диске пока 0 байт. "
                    "Если так долго, у релиза может не быть сидов."
                )
            else:
                phase = "📥 <b>Идёт загрузка на диск</b>"

            size_line = _fmt_bytes_short(size)
            if expected > 0:
                size_line += f" / {_fmt_bytes_short(expected)}"
                pct = min(100, int(100 * size / expected))
                pct_line = f"\nПо размеру файла: ~{pct}%"
            else:
                pct_line = "\nРазмер из торрента неизвестен — смотрим только фактические байты."

            speed_txt = _fmt_speed_bps(speed_bps)
            if size > 0 and speed_bps < 2048 and elapsed > 45:
                speed_txt += " (очень медленно или пауза)"

            text = (
                f"{phase}\n"
                f"ID: #{task.task_id}\n"
                f"Сиды (из поиска): {task.seeders}\n"
                f"Файл: <code>{html.escape(task.filename or 'не указан')}</code>\n\n"
                f"Скачано на диск: <b>{size_line}</b>{pct_line}\n"
                f"Скорость: {speed_txt}\n"
                f"Время: {elapsed} сек"
            )
            await self._edit_status(task.chat_id, status_message_id, text)

            last_size = size
            last_t = now

            try:
                await asyncio.wait_for(done.wait(), timeout=poll_s)
                break
            except asyncio.TimeoutError:
                continue

    async def _aria2c_download_with_progress(
        self,
        task: DownloadTask,
        torrent_path: str,
        dest_dir: str,
        status_message_id: int | None,
    ) -> bool:
        aria2c = shutil.which("aria2c")
        if not aria2c:
            raise RuntimeError("aria2c not found. Install: apt-get install aria2 / brew install aria2")

        tpath = Path(torrent_path)
        dpath = Path(dest_dir)

        cmd = [
            aria2c,
            "--dir",
            dest_dir,
            "--seed-time=0",
            "--max-connection-per-server=4",
            "--split=4",
            "--file-allocation=none",
            "--summary-interval=2",
            "--console-log-level=warn",
        ]
        if task.file_index is not None:
            cmd.extend(["--select-file", str(task.file_index)])
        cmd.append(torrent_path)
        logger.info("aria2c cmd: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._active_task_id = task.task_id
        self._active_proc = proc
        done = asyncio.Event()

        async def _drain_stdout() -> None:
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.readline()
                if not chunk:
                    break
                line = chunk.decode("utf-8", errors="ignore").strip()
                if line:
                    logger.debug("aria2c out task_id=%s: %s", task.task_id, line[:300])

        drain_task = asyncio.create_task(_drain_stdout())
        poll_task = asyncio.create_task(
            self._aria2c_disk_progress_loop(task, tpath, dpath, status_message_id, done)
        )

        try:
            rc = await proc.wait()
            done.set()
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
            await drain_task
            logger.info("aria2c finished: task_id=%s rc=%s", task.task_id, rc)
            return rc == 0
        finally:
            if not done.is_set():
                done.set()
            if not poll_task.done():
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
            if self._active_task_id == task.task_id:
                self._active_task_id = None
                self._active_proc = None


def dest_dir_for_cleanup(topic_id: str) -> Path:
    return Path(RUTRACKER_DOWNLOAD_DIR) / topic_id


def _dir_bytes_excluding_torrent(root: Path, torrent_path: Path) -> int:
    """Sum size of files under root except the .torrent metadata file (real download progress)."""
    if not root.exists():
        return 0
    total = 0
    try:
        t_res = torrent_path.resolve()
    except OSError:
        t_res = None
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            if t_res is not None and p.resolve() == t_res:
                continue
        except OSError:
            pass
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def _fmt_speed_bps(bps: float) -> str:
    if bps < 512:
        return "≈0 (ждём пиров)"
    if bps < 1024 * 1024:
        return f"~{bps / 1024:.1f} KB/s"
    return f"~{bps / 1024 / 1024:.2f} MB/s"


def _fmt_bytes_short(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / 1024 / 1024:.2f} MB"
    return f"{n / 1024**3:.2f} GB"


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
        logger.error("ffmpeg recompress failed: src=%s rc=%s", path, result.returncode)
        return None
    logger.info("ffmpeg recompress success: src=%s out=%s", path, out)
    return str(out)


# Module-level singleton
downloader = RutrackerDownloader()
