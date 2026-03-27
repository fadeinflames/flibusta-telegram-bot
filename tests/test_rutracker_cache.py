"""Helpers for local audio cache (skip re-download when file already on disk)."""
from pathlib import Path

from src.rutracker_downloader import _file_size_ready, _find_resolved_audio_path


def test_file_size_ready_matches(tmp_path: Path) -> None:
    p = tmp_path / "a.mp3"
    p.write_bytes(b"x" * 50_000)
    assert _file_size_ready(p, 50_000)
    assert not _file_size_ready(p, 50_000 * 2)


def test_file_size_ready_unknown_expected_accepts_nonempty(tmp_path: Path) -> None:
    p = tmp_path / "a.mp3"
    p.write_bytes(b"x" * 2000)
    assert _file_size_ready(p, 0)


def test_file_size_ready_rejects_empty(tmp_path: Path) -> None:
    p = tmp_path / "a.mp3"
    p.write_bytes(b"")
    assert not _file_size_ready(p, 0)


def test_find_resolved_audio_path_by_basename(tmp_path: Path) -> None:
    sub = tmp_path / "nested"
    sub.mkdir()
    p = sub / "Chapter 01.mp3"
    p.write_bytes(b"x" * 100)
    assert _find_resolved_audio_path(tmp_path, "Chapter 01.mp3") == p
    assert _find_resolved_audio_path(tmp_path, "foo/Chapter 01.mp3") == p
