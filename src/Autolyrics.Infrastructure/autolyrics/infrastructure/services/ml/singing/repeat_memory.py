import re
from collections import defaultdict
from statistics import mean, median

from autolyrics.domain.lyrics import Line


class RepeatMemory:
    """Choruses are sung to the same rhythm every time. A repeat of a line whose words the judge
    doubts borrows the rhythm of the repeats it trusts, anchored on its own surest word; it
    does so only when the trusted repeats agree with each other (a changed melody is left
    alone). Returns the (line, word) positions that were re-timed."""

    WORD = re.compile(r"[\w']+")

    def __init__(self, trusted: float = 0.97, unsure: float = 0.92, doubtful_share: float = 0.3,
                 agreement: float = 0.2, min_words: int = 3):
        self._trusted = trusted  # mean confidence of a repeat whose rhythm can be lent
        self._unsure = unsure  # a word below this confidence is doubtful
        self._doubtful_share = doubtful_share  # share of doubtful words that makes a repeat borrow
        self._agreement = agreement  # seconds trusted repeats may differ by, word for word
        self._min_words = min_words

    def apply(self, lines: list[Line]) -> set[tuple[int, int]]:
        changed: set[tuple[int, int]] = set()
        for repeats in self._groups(lines).values():
            if len(repeats) < 2:
                continue
            trusted = [i for i in repeats if self._confidence(lines[i]) >= self._trusted]
            pattern = self._pattern([lines[i] for i in trusted])
            if pattern is None:
                continue
            for i in repeats:
                if i in trusted or not self._doubtful(lines[i]):
                    continue
                changed |= {(i, wi) for wi in self._borrow(lines[i], pattern)}
        return changed

    def _groups(self, lines: list[Line]) -> dict[str, list[int]]:
        groups: dict[str, list[int]] = defaultdict(list)
        for i, line in enumerate(lines):
            if len(line.words) >= self._min_words:
                key = " ".join(self.WORD.findall(" ".join(w.text for w in line.words).lower()))
                groups[key].append(i)
        return groups

    @staticmethod
    def _confidence(line: Line) -> float:
        scores = [w.confidence for w in line.words if w.confidence is not None]
        return mean(scores) if scores and all(w.timed for w in line.words) else 0.0

    def _doubtful(self, line: Line) -> bool:
        doubtful = sum((w.confidence or 0.0) < self._unsure for w in line.words)
        return doubtful / len(line.words) >= self._doubtful_share

    def _pattern(self, lines: list[Line]) -> list[tuple[float, float]] | None:
        """Each word's (begin, end) relative to the line start, agreed by the trusted repeats."""
        if not lines:
            return None
        rel = [[(w.begin - line.words[0].begin, w.end - line.words[0].begin) for w in line.words]
               for line in lines]
        pattern = [(median(r[k][0] for r in rel), median(r[k][1] for r in rel))
                   for k in range(len(rel[0]))]
        for r in rel:
            if max(abs(a[0] - p[0]) for a, p in zip(r, pattern, strict=True)) > self._agreement:
                return None
        return pattern

    def _borrow(self, line: Line, pattern: list[tuple[float, float]]) -> list[int]:
        timed = [(k, w) for k, w in enumerate(line.words) if w.timed]
        if not timed:
            return []
        k, anchor = max(timed, key=lambda kw: kw[1].confidence or 0.0)
        start = anchor.begin - pattern[k][0]
        for word, (b, e) in zip(line.words, pattern, strict=True):
            word.begin, word.end = round(start + b, 3), round(start + e, 3)
            word.flag("from-repeat")
        return list(range(len(line.words)))
