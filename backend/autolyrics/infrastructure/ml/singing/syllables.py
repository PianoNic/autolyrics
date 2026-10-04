from itertools import pairwise
from typing import ClassVar

from autolyrics.domain.lyrics import Word
from autolyrics.infrastructure.ml.singing.ctc_solver import WordSpan
from autolyrics.infrastructure.ml.singing.lam_model import PHONES


class Syllabifier:
    """Written syllables by hyphenation patterns (pyphen): "beautiful" -> beau-ti-ful."""

    DICTIONARIES: ClassVar = {"en": "en_US", "de": "de_DE", "fr": "fr_FR", "es": "es",
                              "it": "it_IT"}

    def __init__(self):
        self._dictionaries: dict[str, object] = {}

    def pieces(self, text: str, language: str) -> list[str]:
        """The word's text split into syllables; the last piece keeps the trailing space."""
        core = text.rstrip()
        trailing = text[len(core):]
        dictionary = self._dictionary(language)
        if dictionary is None or len(core) < 4:
            return [text]
        cuts = [p for p in dictionary.positions(core) if 0 < p < len(core)]
        if not cuts:
            return [text]
        bounds = [0, *cuts, len(core)]
        pieces = [core[a:b] for a, b in pairwise(bounds)]
        pieces[-1] += trailing
        return pieces

    def _dictionary(self, language: str):
        code = self.DICTIONARIES.get(language.split("-")[0])
        if code is None:
            return None
        if code not in self._dictionaries:
            import pyphen

            self._dictionaries[code] = pyphen.Pyphen(lang=code)
        return self._dictionaries[code]


class SyllableTimer:
    """Splits timed words into timed syllables, from where the aligner heard each one start.

    With the singing model every token is a phoneme: a word whose written syllables match its
    sung vowels gets one syllable per vowel, each starting at the consonant just before it
    ("beau-ti-ful": t and f). With a letter model the pieces map onto letters directly. Words
    whose syllables cannot be matched this way stay whole: a guessed split would animate wrong.
    """

    VOWEL_MARKS: ClassVar = set("aeiouyæɐɑɔəɚɛɜɪʊʌø")
    MIN_SYLLABLE = 0.04  # seconds; shorter splits are noise

    def __init__(self, syllabifier: Syllabifier):
        self._syllabifier = syllabifier
        self._vowel_ids = {i for i, p in enumerate(PHONES) if p[0] in self.VOWEL_MARKS}

    def split(self, word: Word, span: WordSpan, tokens: list[int], language: str,
              phonemes: bool, frame_seconds: float) -> list[Word]:
        pieces = self._syllabifier.pieces(word.text, language)
        if len(pieces) < 2 or len(tokens) != len(span.tokens) or not word.timed:
            return [word]
        starts = (self._phoneme_starts(tokens, len(pieces)) if phonemes
                  else self._letter_starts(pieces, len(tokens)))
        if starts is None:
            return [word]
        times = [word.begin] + [span.tokens[k].begin * frame_seconds for k in starts[1:]]
        times.append(word.end)
        if any(b - a < self.MIN_SYLLABLE for a, b in pairwise(times)):
            return [word]
        return [Word(text=piece, begin=round(a, 3), end=round(b, 3),
                     confidence=word.confidence, flags=list(word.flags))
                for piece, a, b in zip(pieces, times, times[1:], strict=False)]

    def _phoneme_starts(self, tokens: list[int], count: int) -> list[int] | None:
        vowels = [i for i, t in enumerate(tokens) if t in self._vowel_ids]
        if len(vowels) != count:
            return None
        starts = [0]
        for prev, vowel in pairwise(vowels):
            # The consonant right before the vowel opens its syllable, when there is one.
            starts.append(vowel - 1 if vowel - 1 > prev else vowel)
        return starts

    @staticmethod
    def _letter_starts(pieces: list[str], tokens: int) -> list[int] | None:
        letters = [sum(ch.isalpha() for ch in p) for p in pieces]
        if sum(letters) != tokens or 0 in letters:
            return None
        starts, at = [], 0
        for n in letters:
            starts.append(at)
            at += n
        return starts
