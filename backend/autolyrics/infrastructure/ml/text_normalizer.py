import re
from typing import ClassVar

from autolyrics.infrastructure.ml.japanese_text import JapaneseText


class AlignmentTextNormalizer:
    """Spells a lyric word in the aligner's a-z alphabet: "Größe" -> "grosse", "187" ->
    "hundertsiebenundachtzig". Works for any language the romaniser and num2words know."""

    DIGITS = re.compile(r"\d+")
    SYMBOLS: ClassVar = {
        "de": {"&": " und ", "+": " plus ", "%": " prozent ", "$": " dollar ", "€": " euro "},
        "en": {"&": " and ", "+": " plus ", "%": " percent ", "$": " dollar ", "€": " euro "},
    }

    def __init__(self, alphabet: set[str], japanese: "JapaneseText | None" = None):
        self._alphabet = alphabet
        self._japanese = japanese

    def normalize(self, word: str, language: str) -> str:
        from unidecode import unidecode

        text = word.lower()
        if (self._japanese is not None and not language.startswith(("zh", "ko"))
                and self._japanese.contains_japanese(text)):
            # Kanji have Japanese readings; a generic romaniser would read them as Chinese.
            text = self._japanese.romaji(text)
        symbols = self.SYMBOLS["de" if language.startswith("de") else "en"]
        for symbol, spoken in symbols.items():
            text = text.replace(symbol, spoken)
        text = self.DIGITS.sub(lambda m: self._spell_number(int(m.group(0)), language), text)
        text = unidecode(text).lower().replace("`", "'").replace("’", "'")
        return "".join(c for c in text if c in self._alphabet)

    @staticmethod
    def _spell_number(number: int, language: str) -> str:
        from num2words import num2words

        try:
            spoken = num2words(number, lang=language.split("-")[0])
        except (NotImplementedError, OverflowError, ValueError):
            spoken = num2words(number)
        if language.startswith("de"):
            # Said "hundertsiebenundachtzig", not "einhundert...".
            spoken = re.sub(r"^ein(hundert|tausend)", r"\1", spoken)
        return spoken
