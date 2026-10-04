"""Measure alignment accuracy against lyrics that already have real word timing.

    python scripts/benchmark_align.py <job_dir> <ground_truth.ttml>

The ground truth's text is aligned twice: once keeping only its line times (like an LRC from
LRCLIB) and once with no times at all (like plain text). Reports how far each aligned word start
is from the real one, after removing the constant offset between the two audio masters.
"""

import sys
import time
from pathlib import Path

import numpy as np

from autolyrics.composition.container import Container
from autolyrics.domain.lyrics import Lyrics


class AlignmentBenchmark:
    def __init__(self, container: Container, job_dir: Path, truth: Lyrics):
        self._container = container
        self._job_dir = job_dir
        self._truth = truth

    def run(self) -> None:
        audio = next(p for p in self._job_dir.iterdir() if p.stem == "source" and p.is_file())
        started = time.time()
        vocals = self._container.separator.separate(audio, self._job_dir)
        print(f"separation   {time.time() - started:.1f}s")
        for name, lyrics in (("line-synced", self.line_synced()), ("plain", self.plain())):
            started = time.time()
            stats = self._container.aligner.align(lyrics, vocals, self._job_dir)
            self.report(name, lyrics, stats, time.time() - started)
        self._container.aligner.release()

    def line_synced(self) -> Lyrics:
        lyrics = self._truth.model_copy(deep=True)
        lines = [line for line in lyrics.lines if line.words]
        for i, line in enumerate(lines):
            begin, end = line.bounds()
            # LRC only knows when a line starts; it ends when the next one begins.
            line.begin = begin
            line.end = lines[i + 1].bounds()[0] if i + 1 < len(lines) else end
        for word in lyrics.all_words:
            word.begin = word.end = None
        return lyrics

    def plain(self) -> Lyrics:
        lyrics = self._truth.model_copy(deep=True)
        lyrics.strip_timing()
        return lyrics

    def errors(self, aligned: Lyrics) -> tuple[np.ndarray, float]:
        diffs = [a.begin - t.begin
                 for t_line, a_line in zip(self._truth.lines, aligned.lines, strict=True)
                 for t, a in zip(t_line.words, a_line.words, strict=True)
                 if t.timed and a.timed]
        diffs = np.array(diffs)
        offset = float(np.median(diffs))
        return np.abs(diffs - offset), offset

    def report(self, name: str, aligned: Lyrics, stats: dict, seconds: float) -> None:
        diffs, offset = self.errors(aligned)
        print(f"{name:<12} words={len(diffs):4d}  offset={offset * 1000:+5.0f}ms  "
              f"median={np.median(diffs) * 1000:6.0f}ms  "
              f"p90={np.percentile(diffs, 90) * 1000:6.0f}ms  "
              f"<100ms={np.mean(diffs < 0.1):5.1%}  <250ms={np.mean(diffs < 0.25):5.1%}  "
              f"<500ms={np.mean(diffs < 0.5):5.1%}  conf={stats['mean_confidence']}  "
              f"low={stats['low_confidence']}  off={stats['line_offset']}  "
              f"re={stats['reanchored']}  {seconds:.1f}s")

    @classmethod
    def main(cls) -> None:
        container = Container()
        truth = container.formats.parse("ttml", Path(sys.argv[2]).read_text(encoding="utf-8"))
        cls(container, Path(sys.argv[1]), truth).run()


if __name__ == "__main__":
    AlignmentBenchmark.main()
