from autolyrics.domain.lyrics import Line, Word


class TimingRepairer:
    """Fixes up aligned word times within a line: fills untimed words, re-anchors stray ones,
    closes small gaps, enforces order and a minimum length, and flags weak words."""

    def __init__(self, low_confidence: float = 0.03, detached_confidence: float = 0.05,
                 detached_gap: float = 0.5, close_gap: float = 0.30, min_word: float = 0.05):
        self._low_confidence = low_confidence
        self._detached_confidence = detached_confidence
        self._detached_gap = detached_gap
        self._close_gap = close_gap  # sung words run into each other
        self._min_word = min_word

    def repair(self, line: Line, window: tuple[float, float] | None = None) -> None:
        """The full sequence for one line; `window` stands in for untimed line bounds."""
        frame = Line(begin=window[0], end=window[1]) if window else line
        self.reanchor_detached(line.words)
        self.fill_gaps(line.words, frame)
        self.fill_gaps(line.background, frame)
        self.tidy(line.words)
        self.tidy(line.background)

    def reanchor_detached(self, words: list[Word]) -> None:
        """A barely-recognised word far from the rest of its line was almost always pulled onto a
        backing vocal or an echo; put it back against its neighbour."""
        for k, w in enumerate(words):
            if not w.timed or (w.confidence or 0) >= self._detached_confidence:
                continue
            nxt = words[k + 1] if k + 1 < len(words) and words[k + 1].timed else None
            prev = words[k - 1] if k > 0 and words[k - 1].timed else None
            length = min(w.end - w.begin, 0.4)
            if nxt is not None and nxt.begin - w.end > self._detached_gap:
                w.begin, w.end = nxt.begin - length, nxt.begin
                w.flags.append("reanchored")
            elif nxt is None and prev is not None and w.begin - prev.end > self._detached_gap:
                w.begin, w.end = prev.end, prev.end + length
                w.flags.append("reanchored")

    def fill_gaps(self, words: list[Word], line: Line) -> None:
        """Time unaligned words by spreading them between their timed neighbours by length."""
        i = 0
        while i < len(words):
            if words[i].timed:
                i += 1
                continue
            j = i
            while j < len(words) and not words[j].timed:
                j += 1
            prev_end = words[i - 1].end if i > 0 else None
            next_begin = words[j].begin if j < len(words) else None
            if prev_end is None and next_begin is None:
                if line.begin is None:
                    return
                prev_end, next_begin = line.begin, line.end
            elif prev_end is None:
                prev_end = max(0.0, next_begin - 0.3 * (j - i))
            elif next_begin is None:
                next_begin = prev_end + 0.3 * (j - i)
            self.spread(words[i:j], prev_end, max(0.05 * (j - i), next_begin - prev_end),
                        "interpolated")
            i = j

    def tidy(self, words: list[Word]) -> None:
        for k, w in enumerate(words):
            if not w.timed:
                continue
            if k > 0 and words[k - 1].timed and w.begin < words[k - 1].end:
                w.begin = words[k - 1].end
            if k + 1 < len(words) and words[k + 1].timed:
                gap = words[k + 1].begin - w.end
                if 0 < gap < self._close_gap:
                    w.end = words[k + 1].begin
            w.end = max(w.end, w.begin + self._min_word)
            w.begin, w.end = round(w.begin, 3), round(w.end, 3)
            if w.confidence is not None and w.confidence < self._low_confidence:
                w.flag("low-confidence")

    @staticmethod
    def spread(words: list[Word], start: float, span: float, *flags: str) -> None:
        """Lay words end to end over [start, start + span], each as long as its text."""
        weights = [max(1, len(w.text.strip())) for w in words]
        total = sum(weights)
        t = start
        for w, weight in zip(words, weights, strict=True):
            w.begin, w.end = t, t + span * weight / total
            t = w.end
            for flag in flags:
                w.flag(flag)
