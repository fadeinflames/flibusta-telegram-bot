"""Audiobook API — search, topic files, streaming, progress."""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from api.auth import decode_access_token
from api.deps import CurrentUser
from src import database as db
from src import rutracker
from src.config import RUTRACKER_DOWNLOAD_DIR


class UpdateProgressBody(BaseModel):
    chapter: int = 0

router = APIRouter(prefix="/api/audiobooks", tags=["audiobooks"])


@router.get("/search")
async def search_audiobooks(q: str, user: CurrentUser, limit: int = 15):
    """Search RuTracker audiobook categories."""
    if len(q.strip()) < 2:
        raise HTTPException(400, "Query too short")
    topics = await asyncio.to_thread(rutracker.search, q.strip(), limit)
    return {
        "items": [
            {
                "topic_id": t.topic_id,
                "title": t.title,
                "size": t.size,
                "seeds": t.seeds,
                "leeches": t.leeches,
                "forum_name": t.forum_name,
            }
            for t in topics
        ],
        "total": len(topics),
    }


@router.get("/{topic_id}/info")
async def get_topic_info(topic_id: str, user: CurrentUser):
    """Get topic info with file list."""
    info = await asyncio.to_thread(rutracker.get_topic_info, topic_id)
    if not info:
        raise HTTPException(404, "Topic not found")
    return {
        "topic_id": info.topic_id,
        "title": info.title,
        "description": info.description,
        "forum_name": info.forum_name,
        "topic_url": info.topic_url,
        "files": info.files,
        "audio_files": info.audio_files,
    }


@router.get("/{topic_id}/files")
async def get_topic_files(topic_id: str, user: CurrentUser):
    """Get structured file list with sizes."""
    files = await asyncio.to_thread(rutracker.get_topic_files, topic_id)
    return {
        "items": [
            {
                "filename": f.filename,
                "size_bytes": f.size_bytes,
                "index": f.index_in_torrent,
            }
            for f in files
        ],
        "total": len(files),
    }


@router.get("/{topic_id}/stream/{file_index}")
async def stream_audio(topic_id: str, file_index: int, request: Request, token: str = Query(...)):
    """Stream an audio file with HTTP Range support for seeking."""
    user = decode_access_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    dl_dir = Path(RUTRACKER_DOWNLOAD_DIR) / topic_id
    if not dl_dir.exists():
        raise HTTPException(404, "Files not downloaded yet")

    # Find the target file by index
    audio_exts = {".mp3", ".m4b", ".m4a", ".ogg", ".flac", ".opus", ".aac", ".wav"}
    audio_files = sorted(
        [f for f in dl_dir.rglob("*") if f.suffix.lower() in audio_exts and f.is_file()],
        key=lambda f: f.name,
    )

    if file_index < 0 or file_index >= len(audio_files):
        raise HTTPException(404, f"File index {file_index} not found (have {len(audio_files)} files)")

    filepath = audio_files[file_index]
    file_size = filepath.stat().st_size

    # Determine content type
    ext = filepath.suffix.lower()
    content_types = {
        ".mp3": "audio/mpeg",
        ".m4b": "audio/mp4",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".opus": "audio/opus",
        ".aac": "audio/aac",
        ".wav": "audio/wav",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    # Handle Range header for seeking
    range_header = request.headers.get("range")
    if range_header:
        # Parse "bytes=start-end"
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def iter_range():
            with open(filepath, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_range(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
            },
        )

    # No range — return full file
    return FileResponse(
        filepath,
        media_type=content_type,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
    )


@router.post("/{topic_id}/download")
async def enqueue_download(topic_id: str, user: CurrentUser):
    """Enqueue a topic for background download."""
    user_id = int(user["id"])
    # Check if already queued
    pending = await asyncio.to_thread(db.rt_pending_for_user, user_id)
    for task in pending:
        if task["topic_id"] == topic_id:
            return {"status": "already_queued", "task_id": task["id"]}

    task_id = await asyncio.to_thread(
        db.rt_enqueue,
        user_id=user_id,
        chat_id=user_id,  # for web, chat_id = user_id
        topic_id=topic_id,
        title="",
    )
    return {"status": "queued", "task_id": task_id}


@router.get("/queue")
async def get_download_queue(user: CurrentUser):
    """Get current user's download queue."""
    user_id = int(user["id"])
    tasks = await asyncio.to_thread(db.rt_pending_for_user, user_id)
    return {
        "items": [
            {
                "task_id": t["id"],
                "topic_id": t["topic_id"],
                "title": t["title"],
                "filename": t["filename"],
                "status": t["status"],
            }
            for t in tasks
        ],
    }


@router.get("/progress")
async def get_listening_progress(user: CurrentUser):
    """Get user's listening progress (currently reading audiobooks)."""
    user_id = int(user["id"])
    items = await asyncio.to_thread(db.reading_progress_list, user_id)
    return {
        "items": [
            {
                "id": item["id"],
                "topic_id": item.get("rutracker_topic_id", ""),
                "title": item.get("title", ""),
                "author": item.get("author", ""),
                "current_chapter": item.get("current_chapter", 0),
                "total_chapters": item.get("total_chapters", 0),
                "updated_at": item.get("updated_at", 0),
            }
            for item in items
            if item.get("kind") == "audio"
        ],
    }


@router.patch("/progress/{topic_id}")
async def update_listening_progress(
    topic_id: str,
    body: UpdateProgressBody,
    user: CurrentUser,
):
    """Update current chapter for an audiobook."""
    user_id = int(user["id"])
    chapter = body.chapter
    await asyncio.to_thread(db.reading_progress_update_chapter, user_id, topic_id, chapter)
    return {"status": "ok"}
