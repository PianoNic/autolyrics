import re
import xml.etree.ElementTree as ET
from typing import ClassVar

from autolyrics.domain.lyrics import Line, Lyrics, Metadata, SyncType, Word


class QrcFormat:
    """QQ Music QRC: `[lineStartMs,lineDurMs]word(startMs,durMs)...`, optionally wrapped in XML."""

    LINE_HEADER = re.compile(r"\[(\d+),(\d+)\]")
    WORD_TAG = re.compile(r"\((\d+),(\d+)\)")
    HEADER_TAG = re.compile(r"\[([a-z]+):([^\]]*)\]", re.IGNORECASE)
    COLON = re.compile(r"[:：]")
    CREDIT_PREFIXES: ClassVar = {
        "lyricsby", "composedby", "arrangedby", "producedby", "writtenby", "lyricist", "composer",
        "producer", "arranger", "mixedby", "masteredby", "recordedby",
    }
    CREDIT_SUFFIXES = ("词", "詞", "曲", "声", "聲", "音")

    def detect(self, content: str) -> SyncType:
        if not self.LINE_HEADER.search(content):
            return SyncType.UNSYNCED
        return SyncType.WORD if self.WORD_TAG.search(content) else SyncType.LINE

    @staticmethod
    def _lyric_content(content: str) -> str:
        if "<QrcInfos" not in content:
            return content
        try:
            root = ET.fromstring(content.encode("utf-8"))
        except ET.ParseError:
            return content
        for el in root.iter():
            if "LyricContent" in el.attrib:
                return el.attrib["LyricContent"]
        return ""

    def is_credit(self, text: str) -> bool:
        """QQ mixes credit lines ("Lyrics by：…", "词：…") into the lyrics."""
        m = self.COLON.search(text)
        if not m:
            return False
        prefix = re.sub(r"\s+", "", text[: m.start()]).lower()
        if not prefix:
            return False
        if prefix in self.CREDIT_PREFIXES:
            return True
        return len(prefix) <= 4 and prefix.endswith(self.CREDIT_SUFFIXES)

    @staticmethod
    def _is_title_line(text: str, metadata: Metadata) -> bool:
        """The first line is often "Title - Artist"."""
        if not metadata.title:
            return False
        normalized = " ".join(text.split()).lower()
        return normalized.startswith(metadata.title.lower()) and " - " in normalized

    def parse(self, content: str, duration: float | None = None) -> Lyrics:
        body = self._lyric_content(content)
        metadata = Metadata(duration=duration)
        offset = self._read_headers(body, metadata)

        headers = list(self.LINE_HEADER.finditer(body))
        lines: list[Line] = []
        for i, header in enumerate(headers):
            segment = body[header.end(): headers[i + 1].start() if i + 1 < len(headers)
                           else len(body)].rstrip("\r\n")
            line_begin = int(header.group(1)) / 1000 - offset
            line_end = line_begin + int(header.group(2)) / 1000
            plain = self.WORD_TAG.sub("", segment).strip()
            if not plain or self.is_credit(plain) or self._is_title_line(plain, metadata):
                continue
            words, residue = self._parse_words(segment, offset)
            if words and not residue:
                words[-1].text = words[-1].text.rstrip()
                lines.append(Line(words=words))
            else:
                lines.append(Line(words=Word.tokenize(plain), begin=max(0.0, line_begin),
                                  end=line_end))
        self._backfill_zero_lengths(lines, duration)
        return Lyrics(lines=lines, metadata=metadata)

    def _read_headers(self, body: str, metadata: Metadata) -> float:
        offset = 0.0
        for m in self.HEADER_TAG.finditer(body):
            tag, value = m.group(1).lower(), m.group(2).strip()
            if tag == "ti" and value:
                metadata.title = value
            elif tag == "ar" and value:
                metadata.artists = [value]
            elif tag == "al" and value:
                metadata.album = value
            elif tag == "offset" and value.lstrip("-").isdigit():
                offset = int(value) / 1000
        return offset

    def _parse_words(self, segment: str, offset: float) -> tuple[list[Word], str]:
        words: list[Word] = []
        cursor = 0
        for tag in self.WORD_TAG.finditer(segment):
            text = segment[cursor: tag.start()]
            cursor = tag.end()
            begin = int(tag.group(1)) / 1000 - offset
            end = begin + int(tag.group(2)) / 1000
            if not text.strip():
                # QQ times the spaces between words; fold them into the previous word.
                if words:
                    words[-1].text = words[-1].text.rstrip() + " "
                continue
            if text[0].isspace() and words:
                words[-1].text = words[-1].text.rstrip() + " "
            trailing = " " if text != text.rstrip() else ""
            words.append(Word(text=text.strip() + trailing, begin=max(0.0, begin), end=end))
        return words, segment[cursor:].strip()

    @staticmethod
    def _backfill_zero_lengths(lines: list[Line], duration: float | None) -> None:
        """Zero-length final words mean "until the next line"."""
        for i, line in enumerate(lines):
            last = line.words[-1] if line.words else None
            if last and last.timed and last.end == last.begin:
                nxt = lines[i + 1].bounds() if i + 1 < len(lines) else None
                if nxt and nxt[0] > last.begin:
                    last.end = nxt[0]
                elif duration and duration > last.begin:
                    last.end = duration

    @staticmethod
    def write(lyrics: Lyrics) -> str:
        out = []
        meta = lyrics.metadata
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
            b_ms, e_ms = round(bounds[0] * 1000), round(bounds[1] * 1000)
            if line.word_timed:
                body = "".join(
                    f"{w.text}({round(w.begin * 1000)},{round((w.end - w.begin) * 1000)})"
                    for w in line.words)
            else:
                body = line.text
            out.append(f"[{b_ms},{e_ms - b_ms}]{body}")
        return "\n".join(out) + "\n"
