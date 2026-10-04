from itertools import pairwise
from typing import ClassVar

from autolyrics.domain.lyrics import Word
from autolyrics.infrastructure.services.ml.singing.ctc_solver import WordSpan
from autolyrics.infrastructure.services.ml.singing.lam_model import PHONES


class Syllabifier:
    """Written syllables, in two styles. `spoken` follows the sound the way Apple's syllable
    lyrics do: one syllable per vowel group, the consonant before a vowel opening its syllable
    ("slee-ping", "wan-ting", "cri-mi-nal"). `pieces` uses hyphenation patterns (pyphen), the
    fallback when the spoken split does not match the sung vowels."""

    VOWELS: ClassVar = set("aeiouyäöüàâéèêëîïôûùáíóú")
    TOGETHER: ClassVar = ("sch", "ch", "sh", "th", "ph", "qu")
    CODA: ClassVar = ("ng", "ck")

    DICTIONARIES: ClassVar = {"en": "en_US", "de": "de_DE", "fr": "fr_FR", "es": "es",
                              "it": "it_IT"}

    def __init__(self):
        self._dictionaries: dict[str, object] = {}

    def spoken(self, text: str) -> list[str]:
        core = text.rstrip()
        trailing = text[len(core):]
        if len(core) < 3 or any(ch.isspace() for ch in core):
            return [text]
        lower = core.lower()
        nuclei, i = [], 0
        while i < len(lower):
            if lower[i] in self.VOWELS and not (lower[i] == "y" and i + 1 < len(lower)
                                                and lower[i + 1] in self.VOWELS):
                start = i
                while i < len(lower) and lower[i] in self.VOWELS:
                    i += 1
                nuclei.append((start, i))
            else:
                i += 1
        if len(nuclei) < 2:
            return [text]
        cuts = []
        for (_, prev_end), (next_start, _) in pairwise(nuclei):
            consonants = next_start - prev_end
            cut = next_start - 1 if consonants >= 1 else next_start
            # "ng" and "ck" close a syllable ("sing-ing", "kick-ing").
            if lower[prev_end:next_start] in self.CODA:
                cuts.append(next_start)
                continue
            # Keep letter pairs that make one sound together ("ch", "sch").
            for pair in self.TOGETHER:
                if consonants >= len(pair) and lower[next_start - len(pair):next_start] == pair:
                    cut = next_start - len(pair)
                    break
            cuts.append(max(cut, prev_end))
        bounds = [0, *cuts, len(core)]
        pieces = [core[a:b] for a, b in pairwise(bounds) if b > a]
        if len(pieces) != len(nuclei) or not all(any(c.isalpha() for c in piece)
                                                 for piece in pieces):
            return [text]
        pieces[-1] += trailing
        return pieces

    def pieces(self, text: str, language: str) -> list[str]:
        """The word's text split into syllables; the last piece keeps the trailing space."""
        core = text.rstrip()
        trailing = text[len(core):]
        dictionary = self._dictionary(language)
        if dictionary is None or len(core) < 4 or any(ch.isspace() for ch in core):
            return [text]  # a span holding several words keeps the source's grouping
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
        if len(tokens) != len(span.tokens) or not word.timed:
            return [word]
        pieces, starts = [word.text], None
        for candidate in (self._syllabifier.spoken(word.text),
                          self._syllabifier.pieces(word.text, language)):
            if len(candidate) < 2:
                continue
            starts = (self._phoneme_starts(tokens, len(candidate)) if phonemes
                      else self._letter_starts(candidate, len(tokens)))
            if starts is not None:
                pieces = candidate
                break
        if starts is None and phonemes:
            pieces, starts = self._spelled(word.text, tokens)
        if starts is None:
            return [word]
        times = [word.begin] + [span.tokens[k].begin * frame_seconds for k in starts[1:]]
        times.append(word.end)
        if any(b - a < self.MIN_SYLLABLE for a, b in pairwise(times)):
            return [word]
        return [Word(text=piece, begin=round(a, 3), end=round(b, 3),
                     confidence=word.confidence, flags=list(word.flags))
                for piece, a, b in zip(pieces, times, times[1:], strict=False)]

    def _spelled(self, text: str, tokens: list[int]) -> tuple[list[str], list[int] | None]:
        """Names and acronyms in capitals ("SSIO" sung "Es-sio") have no written syllables to
        match: split them by their sung syllables, sharing the letters out in proportion."""
        core = text.rstrip()
        trailing = text[len(core):]
        letters = [i for i, ch in enumerate(core) if ch.isalpha()]
        if not core.isupper() or len(letters) < 3 or any(ch.isspace() for ch in core):
            return [text], None
        vowels = [i for i, t in enumerate(tokens) if t in self._vowel_ids]
        count = min(len(vowels), len(letters))
        starts = self._phoneme_starts(tokens, count) if count >= 2 else None
        if starts is None:
            return [text], None
        # Letters per piece in proportion to the sung syllable's phonemes, at least one each.
        bounds = [*starts, len(tokens)]
        sizes = [b - a for a, b in pairwise(bounds)]
        cuts, used = [], 0
        for k, size in enumerate(sizes[:-1]):
            left = len(sizes) - k - 1  # pieces still to come, one letter each at least
            share = round(len(letters) * size / len(tokens))
            used = min(max(used + 1, used + share), len(letters) - left)
            cuts.append(letters[used] if used < len(letters) else len(core))
        edges = [0, *cuts, len(core)]
        pieces = [core[a:b] for a, b in pairwise(edges)]
        pieces[-1] += trailing
        return pieces, starts

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
