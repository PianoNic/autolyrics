from typing import ClassVar

from autolyrics.domain.lyrics import Lyrics


class LanguageGuesser:
    """The lyrics' language: the metadata's when known, else a stop-word vote."""

    HINTS: ClassVar = {
        "de": {"ich", "und", "nicht", "der", "die", "das", "ist", "du", "mit", "auf", "bin", "mein"},
        "en": {"the", "and", "you", "i'm", "is", "my", "it", "to", "me", "don't", "that"},
    }

    def __init__(self, fallback: str = "en"):
        self._fallback = fallback

    def guess(self, lyrics: Lyrics) -> str:
        if lyrics.metadata.language:
            return lyrics.metadata.language
        words = [w.text.strip().lower() for w in lyrics.all_words]
        votes = {lang: sum(w in hints for w in words) for lang, hints in self.HINTS.items()}
        best = max(votes, key=votes.get)
        return best if votes[best] > 0 and list(votes.values()).count(votes[best]) == 1 \
            else self._fallback
