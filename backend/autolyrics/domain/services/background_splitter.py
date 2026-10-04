import re

from autolyrics.domain.lyrics import Word


class BackgroundSplitter:
    """Splits a lyric line into its main words and the background vocals in parentheses."""

    PARENTHESES = re.compile(r"\(([^()]*)\)")

    def split(self, text: str) -> tuple[list[Word], list[Word]]:
        background = " ".join(m.strip() for m in self.PARENTHESES.findall(text) if m.strip())
        main = " ".join(self.PARENTHESES.sub(" ", text).split())
        return Word.tokenize(main), Word.tokenize(background)
