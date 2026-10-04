import re

from autolyrics.domain.lyrics import Line, Lyrics, Word


class JapaneseText:
    """Readings and word boundaries for Japanese, which is written without spaces and whose kanji
    a generic romaniser reads as Chinese. Uses pykakasi (GPL-3.0-or-later)."""

    SCRIPT = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")

    def __init__(self):
        self._kakasi = None

    @classmethod
    def contains_japanese(cls, text: str) -> bool:
        return bool(cls.SCRIPT.search(text))

    def segments(self, text: str) -> list[tuple[str, str]]:
        """(written, romaji) pieces, roughly one per word."""
        return [(part["orig"], part["hepburn"]) for part in self._converter().convert(text)]

    def romaji(self, text: str) -> str:
        return " ".join(reading for _, reading in self.segments(text))

    def _converter(self):
        if self._kakasi is None:
            import pykakasi

            self._kakasi = pykakasi.kakasi()
        return self._kakasi


class WordSegmenter:
    """Splits lines of space-less scripts into words before alignment, so each gets its own time.
    The pieces of one written word carry no trailing space, so the line reads exactly as before."""

    def __init__(self, japanese: JapaneseText):
        self._japanese = japanese

    def segment(self, lyrics: Lyrics, language: str) -> int:
        """Split in place; returns how many words were split."""
        if language.startswith("zh"):
            return sum(self._characters(line) for line in lyrics.lines)
        if not language.startswith("ja"):
            return 0
        split = 0
        for line in lyrics.lines:
            split += self._segment_line(line)
        return split

    @staticmethod
    def _characters(line: Line) -> int:
        """Chinese: every character is a sung syllable; Latin runs stay whole."""
        split = 0
        for attr in ("words", "background"):
            out: list[Word] = []
            for word in getattr(line, attr):
                core = word.text.rstrip()
                pieces, run = [], ""
                for ch in core:
                    if 0x4E00 <= ord(ch) <= 0x9FFF:
                        if run:
                            pieces.append(run)
                            run = ""
                        pieces.append(ch)
                    elif pieces and not ch.isalnum() and not run:
                        pieces[-1] += ch  # punctuation joins the character before it
                    else:
                        run += ch
                if run:
                    pieces.append(run)
                if len(pieces) <= 1:
                    out.append(word)
                    continue
                split += 1
                pieces[-1] += word.text[len(core):]
                out += [Word(text=p, flags=list(word.flags)) for p in pieces]
            setattr(line, attr, out)
        return split

    def _segment_line(self, line: Line) -> int:
        split = 0
        for attr in ("words", "background"):
            out: list[Word] = []
            for word in getattr(line, attr):
                pieces = self._pieces(word.text) if self._japanese.contains_japanese(word.text) else []
                if len(pieces) <= 1:
                    out.append(word)
                    continue
                split += 1
                trailing = word.text.endswith(" ")
                for k, piece in enumerate(pieces):
                    last = k == len(pieces) - 1
                    out.append(Word(text=piece + (" " if last and trailing else ""),
                                    flags=list(word.flags)))
            setattr(line, attr, out)
        return split

    def _pieces(self, text: str) -> list[str]:
        pieces: list[str] = []
        for written, _ in self._japanese.segments(text.strip()):
            # Latin runs inside a Japanese word ("My brain") keep their own spaces.
            parts = written.split(" ")
            for k, part in enumerate(parts):
                if not part:
                    continue
                if k < len(parts) - 1:
                    pieces.append(part + " ")
                else:
                    pieces.append(part)
        return pieces
