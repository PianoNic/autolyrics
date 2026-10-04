"""Last automatic checks before export. Problems become word flags for the review screen."""

from collections import Counter

from autolyrics.model import Lyrics, Word

MAX_WORD = 6.0  # a single word held longer than this is almost always a mistiming
MIN_WORD = 0.03
MAX_GAP_IN_LINE = 4.0
OUT_OF_ORDER = 1.0  # a line may start this much before the previous one (overlapping vocals)


def _flag(word: Word, issue: str, problems: list, line_index: int) -> None:
    if issue not in word.flags:
        word.flags.append(issue)
    problems.append({"line": line_index, "word": word.text.strip(), "issue": issue})


def check_lyrics(lyrics: Lyrics, duration: float | None) -> dict:
    problems: list[dict] = []
    previous_begin = None
    for i, line in enumerate(lyrics.lines):
        for words in (line.words, line.background):
            for k, w in enumerate(words):
                if not w.timed:
                    continue
                length = w.end - w.begin
                if length > MAX_WORD:
                    _flag(w, "too-long", problems, i)
                elif length < MIN_WORD:
                    _flag(w, "too-short", problems, i)
                if duration and w.end > duration + 0.5:
                    _flag(w, "past-end", problems, i)
                if k > 0 and words[k - 1].timed:
                    gap = w.begin - words[k - 1].end
                    if gap < -0.01:
                        _flag(w, "overlap", problems, i)
                    elif gap > MAX_GAP_IN_LINE:
                        _flag(w, "big-gap", problems, i)
        bounds = line.bounds()
        if bounds is None:
            continue
        if previous_begin is not None and bounds[0] < previous_begin - OUT_OF_ORDER and line.words:
            _flag(line.words[0], "out-of-order", problems, i)
        previous_begin = bounds[0]

    flagged = [w for line in lyrics.lines for w in line.all_words if w.flags]
    return {
        "problems": problems,
        "by_issue": dict(Counter(p["issue"] for p in problems)),
        "flagged_words": len(flagged),
        "total_words": sum(len(line.all_words) for line in lyrics.lines),
    }
