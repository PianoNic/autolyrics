from typing import ClassVar

from autolyrics.domain.lyrics import Lyrics


class LanguageGuesser:
    """The lyrics' language: the metadata's when known, else the writing system for scripts
    that name their language (hangul, kana, Han, Cyrillic), else a stop-word vote."""

    # (language, first, last code point); a song counts as one when this script makes up at
    # least a fifth of its letters. Kana is checked before Han: Japanese mixes both.
    SCRIPTS: ClassVar = (
        ("ko", 0xAC00, 0xD7A3),
        ("ja", 0x3040, 0x30FF),
        ("zh", 0x4E00, 0x9FFF),
        ("ru", 0x0400, 0x04FF),
    )

    HINTS: ClassVar = {
        "de": {"ich", "und", "nicht", "der", "die", "das", "ist", "du", "mit", "auf", "bin", "mein"},
        "en": {"the", "and", "you", "i'm", "is", "my", "it", "to", "me", "don't", "that"},
    }

    @classmethod
    def _script(cls, text: str) -> str | None:
        letters = [ord(ch) for ch in text if ch.isalpha()]
        if not letters:
            return None
        for language, first, last in cls.SCRIPTS:
            share = sum(first <= c <= last for c in letters) / len(letters)
            # Kana marks Japanese even as a small share of a kanji-heavy text.
            if share >= (0.05 if language == "ja" else 0.2):
                return language
        return None

    def __init__(self, fallback: str = "en"):
        self._fallback = fallback

    def guess(self, lyrics: Lyrics) -> str:
        if lyrics.metadata.language:
            return lyrics.metadata.language
        script = self._script(" ".join(w.text for w in lyrics.all_words))
        if script:
            return script
        words = [w.text.strip().lower() for w in lyrics.all_words]
        votes = {lang: sum(w in hints for w in words) for lang, hints in self.HINTS.items()}
        best = max(votes, key=votes.get)
        return best if votes[best] > 0 and list(votes.values()).count(votes[best]) == 1 \
            else self._fallback
