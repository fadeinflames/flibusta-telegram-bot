from src import config


def escape_md(text: str) -> str:
    """Escape MarkdownV1 special characters in user-provided text."""
    if not text:
        return ""
    for ch in ("_", "*", "`", "[", "]"):
        text = text.replace(ch, f"\\{ch}")
    return text


def get_user_level(search_count: int, download_count: int) -> str:
    """Return achievement level name for counters."""
    level = config.ACHIEVEMENT_LEVELS[0]
    for lvl in config.ACHIEVEMENT_LEVELS:
        if search_count >= lvl["searches"] and download_count >= lvl["downloads"]:
            level = lvl
    return level["name"]


def next_level_info(search_count: int, download_count: int) -> str:
    """Return human-readable progress toward the next level."""
    for lvl in config.ACHIEVEMENT_LEVELS:
        if search_count < lvl["searches"] or download_count < lvl["downloads"]:
            need_s = max(0, lvl["searches"] - search_count)
            need_d = max(0, lvl["downloads"] - download_count)
            parts = []
            if need_s > 0:
                parts.append(f"{need_s} поисков")
            if need_d > 0:
                parts.append(f"{need_d} скачиваний")
            return f"До «{lvl['name']}»: {', '.join(parts)}"
    return "Максимальный уровень достигнут! 🎉"


def shelf_label(tag: str) -> str:
    """Return user-facing shelf label."""
    return config.FAVORITE_SHELVES.get(tag, tag or "Все")
