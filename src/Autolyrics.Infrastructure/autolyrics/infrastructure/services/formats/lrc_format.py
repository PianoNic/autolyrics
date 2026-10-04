import re

from autolyrics.domain.lyrics import Line, Lyrics, Metadata, SyncType, Word
from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.infrastructure.services.formats.time_format import TimeFormat


class LrcFormat:
    """LRC: line-synced `[mm:ss.xx]`, optionally word-synced with enhanced `<mm:ss.xx>` tags."""

    LINE_TS = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
    WORD_TS = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?>")
    META = re.compile(r"^\[([a-z]+):([^\]]*)\]$", re.IGNORECASE)
    FALLBACK_LINE = 5.0  # seconds for a last line when the song length is unknown

    def __init__(self, splitter: BackgroundSplitter):
        self._splitter = splitter

    @staticmethod
    def _seconds(m: re.Match) -> float:
        frac = m.group(3) or "0"
        return int(m.group(1)) * 60 + int(m.group(2)) + int(frac.ljust(3, "0")[:3]) / 1000

    def detect(self, content: str) -> SyncType:
        saw_line = False
        for raw in content.splitlines():
            line = raw.strip()
            if not line:
                continue
            if self.WORD_TS.search(line) and self.LINE_TS.search(line):
                return SyncType.WORD
            if self.LINE_TS.search(line) and not self.META.match(line):
                saw_line = True
        return SyncType.LINE if saw_line else SyncType.UNSYNCED

    def parse(self, content: str, duration: float | None = None) -> Lyrics:
        """Line ends are the next line's start (the song end for the last line)."""
        metadata = Metadata(duration=duration)
        entries: list[tuple[float, str]] = []
        offset = 0.0
        for raw in content.splitlines():
            raw = raw.strip()
            meta = self.META.match(raw)
            if meta and not self.LINE_TS.match(raw):
                offset = self._read_header(meta, metadata, offset)
                continue
            stamps = list(self.LINE_TS.finditer(raw))
            if not stamps:
                continue
            body = raw[stamps[-1].end():]
            for stamp in stamps:  # "[00:12.00][01:30.00]chorus" repeats one text at several times
                entries.append((max(0.0, self._seconds(stamp) - offset), body))
        entries.sort(key=lambda e: e[0])

        lines: list[Line] = []
        for i, (begin, body) in enumerate(entries):
            next_begin = entries[i + 1][0] if i + 1 < len(entries) else duration
            end = next_begin if next_begin is not None and next_begin > begin \
                else begin + self.FALLBACK_LINE
            if self.WORD_TS.search(body):
                line = self._parse_enhanced(body, begin, end)
            else:
                if not body.strip():
                    continue  # an empty timed line only marks an instrumental gap
                main, background = self._splitter.split(body)
                line = Line(words=main, background=background, begin=begin, end=end)
            if line.has_content:
                lines.append(line)
        return Lyrics(lines=lines, metadata=metadata)

    @staticmethod
    def _read_header(meta: re.Match, metadata: Metadata, offset: float) -> float:
        tag, value = meta.group(1).lower(), meta.group(2).strip()
        if tag == "ti" and value:
            metadata.title = value
        elif tag == "ar" and value:
            metadata.artists = [value]
        elif tag == "al" and value:
            metadata.album = value
        elif tag == "offset" and value.lstrip("-").isdigit():
            return int(value) / 1000
        return offset

    def _parse_enhanced(self, body: str, line_begin: float, line_end: float) -> Line:
        stamps = list(self.WORD_TS.finditer(body))
        words: list[Word] = []
        for i, stamp in enumerate(stamps):
            text = body[stamp.end(): stamps[i + 1].start() if i + 1 < len(stamps) else len(body)]
            if not text.strip():
                continue
            begin = self._seconds(stamp)
            end = self._seconds(stamps[i + 1]) if i + 1 < len(stamps) else line_end
            trailing = " " if text != text.rstrip() else ""
            words.append(Word(text=text.strip() + trailing, begin=begin, end=max(end, begin)))
        if words:
            words[-1].text = words[-1].text.rstrip()
        return Line(words=words, begin=line_begin, end=line_end)

    @staticmethod
    def write(lyrics: Lyrics, word_level: bool = False) -> str:
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
                text = "".join(f"<{TimeFormat.lrc(w.begin)}>{w.text}" for w in line.words)
                text += f"<{TimeFormat.lrc(line.words[-1].end)}>"
            else:
                text = line.text
            if line.background:
                text = f"{text} ({line.background_text})"
            out.append(f"[{TimeFormat.lrc(bounds[0])}]{text}")
        return "\n".join(out) + "\n"
