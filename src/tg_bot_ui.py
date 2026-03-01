DIVIDER = "━━━━━━━━━━━━━━━━━━━━━"


def truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    return text[: limit - 1] + "…" if len(text) > limit else text


def breadcrumbs(*parts: str) -> str:
    clean = [p for p in parts if p]
    if not clean:
        return ""
    return " > ".join(clean)


def screen(title: str, body: str, trail: str | None = None) -> str:
    lines = [f"{title}"]
    if trail:
        lines.append(f"_{trail}_")
    lines.append("")
    lines.append(DIVIDER)
    lines.append(body.strip())
    return "\n".join(lines)
