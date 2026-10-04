import re

from autolyrics.domain.lyrics import Lyrics, Word


class LyricsTidier:
    """Small, safe text fixes on the lyrics a job starts from, in the style of Apple Music's
    lyrics (which most hand-made files follow):

    - punctuation separated by a space ("was geht? ,", "Bro ,") joins the word before it; as its
      own token it would also be timed as if it were sung
    - background vocals start with a capital letter: "(Ciao, ciao)"
    """

    PUNCTUATION = re.compile(r"^[,.;:!?…)\]]+$")

    def tidy(self, lyrics: Lyrics) -> int:
        changes = 0
        for line in lyrics.lines:
            for attr in ("words", "background"):
                words, joined = self._join_punctuation(getattr(line, attr))
                setattr(line, attr, words)
                changes += joined
            changes += self._capitalise(line.background)
        return changes

    def _join_punctuation(self, words: list[Word]) -> tuple[list[Word], int]:
        out: list[Word] = []
        joined = 0
        for word in words:
            core = word.text.strip()
            if out and self.PUNCTUATION.match(core):
                previous = out[-1]
                trailing = " " if word.text.endswith(" ") else ""
                previous.text = previous.text.rstrip() + core + trailing
                if word.timed and previous.timed:
                    previous.end = max(previous.end, word.end)
                joined += 1
                continue
            out.append(word)
        return out, joined

    @staticmethod
    def _capitalise(words: list[Word]) -> int:
        if not words:
            return 0
        first = words[0]
        for i, ch in enumerate(first.text):
            if ch.isalpha():
                if ch.islower():
                    first.text = first.text[:i] + ch.upper() + first.text[i + 1:]
                    return 1
                return 0
        return 0
