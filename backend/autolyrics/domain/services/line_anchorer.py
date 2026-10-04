import difflib
import re

from autolyrics.domain.lyrics import Lyrics


class LineAnchorer:
    """Gives untimed lyric lines approximate times from a transcription of the same song: the
    transcription's words are often wrong, but where it heard them is right. Lines are matched
    word by word, in order; only solid matches count (runs of words, or long words), and lines
    without one are placed between their neighbours by length."""

    WORD = re.compile(r"[\w']+")

    def __init__(self, min_run: int = 2, min_single: int = 4, seconds_per_word: float = 0.3):
        self._min_run = min_run
        self._min_single = min_single
        self._per_word = seconds_per_word

    @classmethod
    def _key(cls, text: str) -> str:
        return "".join(cls.WORD.findall(text.lower()))

    def anchor(self, lyrics: Lyrics, transcript: Lyrics, duration: float) -> int:
        """Set begin/end on every content line of `lyrics`; returns how many lines were matched
        directly (the rest are interpolated). Lines get no times if nothing matched at all."""
        heard = self._timed_transcript_words(transcript)
        lines = lyrics.content_lines
        ours = [(i, self._key(w.text)) for i, line in enumerate(lines) for w in line.words]
        ours = [(i, k) for i, k in ours if k]
        if not heard or not ours:
            return 0

        matcher = difflib.SequenceMatcher(a=[k for _, k in ours], b=[k for k, _ in heard],
                                          autojunk=False)
        first_hit: dict[int, float] = {}
        position: dict[int, int] = {}
        for block in matcher.get_matching_blocks():
            if block.size == 0:
                continue
            solid = block.size >= self._min_run or len(ours[block.a][1]) >= self._min_single
            if not solid:
                continue
            for k in range(block.size):
                line_index, _ = ours[block.a + k]
                if line_index not in first_hit:
                    first_hit[line_index] = heard[block.b + k][1]
                    position[line_index] = self._word_position(lines[line_index], ours[block.a + k][1])
        if not first_hit:
            return 0

        begins: list[float | None] = [None] * len(lines)
        for i, t in first_hit.items():
            # Step back over the line's words before the first matched one.
            begins[i] = max(0.0, t - position[i] * self._per_word)
        self._enforce_order(begins)
        self._interpolate(begins, lines, duration)
        for i, line in enumerate(lines):
            line.begin = begins[i]
            line.end = begins[i + 1] if i + 1 < len(lines) else min(
                duration, begins[i] + max(2.0, len(line.words) * 0.6))
            if line.end <= line.begin:
                line.end = line.begin + max(0.5, len(line.words) * self._per_word)
        return len(first_hit)

    def _timed_transcript_words(self, transcript: Lyrics) -> list[tuple[str, float]]:
        """Each heard word with its start: the transcriber's own word time, or else its line's
        span shared by length."""
        out = []
        for line in transcript.lines:
            if line.words and all(w.timed for w in line.words):
                out += [(key, w.begin) for w in line.words if (key := self._key(w.text))]
                continue
            if line.begin is None or line.end is None:
                continue
            keys = [self._key(w.text) for w in line.words]
            weights = [max(1, len(k)) for k in keys]
            total, t = sum(weights), line.begin
            for key, weight in zip(keys, weights, strict=True):
                if key:
                    out.append((key, t))
                t += (line.end - line.begin) * weight / total
        return out

    def _word_position(self, line, key: str) -> int:
        keys = [self._key(w.text) for w in line.words]
        return keys.index(key) if key in keys else 0

    @staticmethod
    def _enforce_order(begins: list[float | None]) -> None:
        """A match that would start a line before an earlier line is dropped."""
        last = -1.0
        for i, b in enumerate(begins):
            if b is None:
                continue
            if b < last:
                begins[i] = None
            else:
                last = b

    def _interpolate(self, begins: list[float | None], lines, duration: float) -> None:
        known = [i for i, b in enumerate(begins) if b is not None]
        for i in range(len(begins)):
            if begins[i] is not None:
                continue
            prev = max((k for k in known if k < i), default=None)
            nxt = min((k for k in known if k > i), default=None)
            if prev is not None and nxt is not None:
                span_words = sum(len(lines[k].words) for k in range(prev, nxt)) or 1
                before = sum(len(lines[k].words) for k in range(prev, i))
                begins[i] = begins[prev] + (begins[nxt] - begins[prev]) * before / span_words
            elif prev is not None:
                before = sum(len(lines[k].words) for k in range(prev, i))
                begins[i] = min(duration, begins[prev] + before * self._per_word * 2)
            else:
                after = sum(len(lines[k].words) for k in range(i, nxt))
                begins[i] = max(0.0, begins[nxt] - after * self._per_word * 2)
