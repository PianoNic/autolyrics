from collections import Counter

from autolyrics.domain.lyrics import Lyrics, Word


class LyricsValidator:
    """Last automatic checks before export. Problems become word flags for the review screen."""

    def __init__(self, max_word: float = 6.0, min_word: float = 0.03, max_gap_in_line: float = 4.0,
                 out_of_order: float = 1.0):
        self._max_word = max_word  # a single word held longer than this is almost always mistimed
        self._min_word = min_word
        self._max_gap = max_gap_in_line
        self._out_of_order = out_of_order  # a line may start this much before the previous one

    def check(self, lyrics: Lyrics, duration: float | None) -> dict:
        problems: list[dict] = []
        previous_begin = None
        for i, line in enumerate(lyrics.lines):
            for words in (line.words, line.background):
                self._check_words(words, duration, i, problems)
            bounds = line.bounds()
            if bounds is None:
                continue
            if (previous_begin is not None and line.words
                    and bounds[0] < previous_begin - self._out_of_order):
                self._report(line.words[0], "out-of-order", i, problems)
            previous_begin = bounds[0]

        return {
            "problems": problems,
            "by_issue": dict(Counter(p["issue"] for p in problems)),
            "flagged_words": sum(1 for w in lyrics.all_words if w.flags),
            "total_words": len(lyrics.all_words),
        }

    def _check_words(self, words: list[Word], duration: float | None, line_index: int,
                     problems: list[dict]) -> None:
        for k, w in enumerate(words):
            if not w.timed:
                continue
            length = w.end - w.begin
            if length > self._max_word:
                self._report(w, "too-long", line_index, problems)
            elif length < self._min_word:
                self._report(w, "too-short", line_index, problems)
            if duration and w.end > duration + 0.5:
                self._report(w, "past-end", line_index, problems)
            if k > 0 and words[k - 1].timed:
                gap = w.begin - words[k - 1].end
                if gap < -0.01:
                    self._report(w, "overlap", line_index, problems)
                elif gap > self._max_gap:
                    self._report(w, "big-gap", line_index, problems)

    @staticmethod
    def _report(word: Word, issue: str, line_index: int, problems: list[dict]) -> None:
        word.flag(issue)
        problems.append({"line": line_index, "word": word.text.strip(), "issue": issue})
