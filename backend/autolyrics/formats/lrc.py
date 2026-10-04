"""LRC: line-synced `[mm:ss.xx]`, optionally word-synced with enhanced `<mm:ss.xx>` tags."""

import re

from autolyrics.formats.plain import split_background
from autolyrics.formats.timefmt import format_lrc_time
from autolyrics.model import Line, Lyrics, Metadata, SyncType, Word

_LINE_TS = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_WORD_TS = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?>")
_META = re.compile(r"^\[([a-z]+):([^\]]*)\]$", re.IGNORECASE)


def _seconds(m: re.Match) -> float:
    frac = m.group(3) or "0"
    return int(m.group(1)) * 60 + int(m.group(2)) + int(frac.ljust(3, "0")[:3]) / 1000


def detect_lrc_sync_type(content: str) -> SyncType:
    saw_line = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _WORD_TS.search(line) and _LINE_TS.search(line):
            return SyncType.WORD
        if _LINE_TS.search(line) and not _META.match(line):
            saw_line = True
    return SyncType.LINE if saw_line else SyncType.UNSYNCED


def parse_lrc(content: str, duration: float | None = None) -> Lyrics:
    """Parse LRC. Line ends are the next line's start (the song end for the last line)."""
    metadata = Metadata(duration=duration)
    entries: list[tuple[float, str]] = []
    offset = 0.0
    for raw in content.splitlines():
        raw = raw.strip()
        meta = _META.match(raw)
        if meta and not _LINE_TS.match(raw):
            tag, value = meta.group(1).lower(), meta.group(2).strip()
            if tag == "ti" and value:
                metadata.title = value
            elif tag == "ar" and value:
                metadata.artists = [value]
            elif tag == "al" and value:
                metadata.album = value
            elif tag == "offset" and value.lstrip("-").isdigit():
                offset = int(value) / 1000
            continue
        stamps = list(_LINE_TS.finditer(raw))
        if not stamps:
            continue
        body = raw[stamps[-1].end():]
        for stamp in stamps:  # "[00:12.00][01:30.00]chorus" repeats one text at several times
            entries.append((max(0.0, _seconds(stamp) - offset), body))
    entries.sort(key=lambda e: e[0])

    lines: list[Line] = []
    for i, (begin, body) in enumerate(entries):
        next_begin = entries[i + 1][0] if i + 1 < len(entries) else duration
        end = next_begin if next_begin is not None and next_begin > begin else begin + 5.0
        if _WORD_TS.search(body):
            line = _parse_enhanced(body, begin, end)
        else:
            if not body.strip():
                continue  # an empty timed line only marks an instrumental gap
            main, background = split_background(body)
            line = Line(words=main, background=background, begin=begin, end=end)
        if line.words or line.background:
            lines.append(line)
    return Lyrics(lines=lines, metadata=metadata)


def _parse_enhanced(body: str, line_begin: float, line_end: float) -> Line:
    stamps = list(_WORD_TS.finditer(body))
    words: list[Word] = []
    for i, stamp in enumerate(stamps):
        text = body[stamp.end(): stamps[i + 1].start() if i + 1 < len(stamps) else len(body)]
        if not text.strip():
            continue
        begin = _seconds(stamp)
        end = _seconds(stamps[i + 1]) if i + 1 < len(stamps) else line_end
        trailing = " " if text != text.rstrip() else ""
        words.append(Word(text=text.strip() + trailing, begin=begin, end=max(end, begin)))
    if words:
        words[-1].text = words[-1].text.rstrip()
    return Line(words=words, begin=line_begin, end=line_end)


def write_lrc(lyrics: Lyrics, word_level: bool = False) -> str:
    meta = lyrics.metadata
    out = []
    if meta.title:
        out.append(f"[ti:{meta.title}]")
    if meta.artists:
        out.append(f"[ar:{', '.join(meta.artists)}]")
    if meta.album:
        out.append(f"[al:{meta.album}]")
    for line in lyrics.lines:
        bounds = line.bounds()
        if bounds is None:
            continue
        if word_level and line.word_timed:
            text = "".join(f"<{format_lrc_time(w.begin)}>{w.text}" for w in line.words)
            text += f"<{format_lrc_time(line.words[-1].end)}>"
        else:
            text = line.text
        if line.background:
            text = f"{text} ({line.background_text})"
        out.append(f"[{format_lrc_time(bounds[0])}]{text}")
    return "\n".join(out) + "\n"
