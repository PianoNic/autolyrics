from statistics import median

from autolyrics.domain.lyrics import Line, Lyrics


class OffsetEstimator:
    """How far given times sit from where an alignment heard the words."""

    def __init__(self, confident: float = 0.1, neighbours: int = 4, min_words: int = 10):
        self._confident = confident  # no misplaced word in the benchmarks scored above this
        self._neighbours = neighbours
        self._min_words = min_words

    def local_line_offsets(self, lines: list[Line]) -> list[float]:
        """Per line, line time vs. its first confidently aligned word, as a median over the
        neighbouring lines: a music video that inserts a skit shifts everything after it, so the
        offset changes partway through the song. Empty when there is too little to go on."""
        diffs: list[float | None] = []
        for line in lines:
            first = next((w for w in line.words
                          if w.timed and (w.confidence or 0) >= self._confident), None)
            diffs.append(first.begin - line.begin
                         if first is not None and line.begin is not None else None)
        known = [d for d in diffs if d is not None]
        if len(known) < 3:
            return []
        fallback = median(known)
        offsets = []
        for i in range(len(lines)):
            near = [d for d in diffs[max(0, i - self._neighbours): i + self._neighbours + 1]
                    if d is not None]
            offsets.append(median(near) if len(near) >= 2 else fallback)
        return offsets

    def word_offset(self, source: Lyrics, aligned: Lyrics) -> dict:
        """Constant offset between a word-timed source and an alignment of the same text,
        with its spread (median absolute deviation) to tell a real shift from noise."""
        diffs = []
        for src_line, probe_line in zip(source.lines, aligned.lines, strict=True):
            for src, probe in zip(src_line.words, probe_line.words, strict=True):
                if src.timed and probe.timed and (probe.confidence or 0) >= self._confident:
                    diffs.append(probe.begin - src.begin)
        if len(diffs) < self._min_words:
            return {"offset": 0.0, "spread": None, "words": len(diffs)}
        offset = median(diffs)
        spread = median(abs(d - offset) for d in diffs)
        return {"offset": round(offset, 3), "spread": round(spread, 3), "words": len(diffs)}
