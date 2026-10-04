import re

from autolyrics.domain.lyrics import Line, Lyrics
from autolyrics.domain.services.background_splitter import BackgroundSplitter


class PlainTextFormat:
    """One line per line; parenthesised parts become background vocals."""

    # Section labels such as "[Chorus]" or "[Part 2: SSIO]" that some sources mix into the text.
    SECTION = re.compile(r"^\s*\[[^\]]*\]\s*$")

    def __init__(self, splitter: BackgroundSplitter):
        self._splitter = splitter

    def parse(self, content: str) -> Lyrics:
        lines = []
        for raw in content.splitlines():
            if not raw.strip() or self.SECTION.match(raw):
                continue
            main, background = self._splitter.split(raw)
            if main or background:
                lines.append(Line(words=main, background=background))
        return Lyrics(lines=lines)
