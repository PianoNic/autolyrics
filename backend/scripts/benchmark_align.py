"""Measure alignment accuracy against lyrics that already have real word timing.

    python scripts/benchmark_align.py <job_dir> <ground_truth.ttml>

The ground truth's text is aligned twice: once keeping only its line times (like an LRC from
LRCLIB) and once with no times at all (like plain text). Reports how far each aligned word start is
from the real one.
"""

import sys
import time
from pathlib import Path

import numpy as np

from autolyrics.align import Aligner, align_lyrics, load_vocals_16k
from autolyrics.formats.ttml import parse_ttml
from autolyrics.separation import separate_vocals


def line_synced_copy(truth):
    lyrics = truth.model_copy(deep=True)
    lines = [line for line in lyrics.lines if line.words]
    for i, line in enumerate(lines):
        begin, end = line.bounds()
        # LRC only knows when a line starts; it ends when the next one begins.
        line.begin = begin
        line.end = lines[i + 1].bounds()[0] if i + 1 < len(lines) else end
    for line in lyrics.lines:
        for w in line.all_words:
            w.begin = w.end = None
    return lyrics


def plain_copy(truth):
    lyrics = truth.model_copy(deep=True)
    lyrics.strip_timing()
    return lyrics


def errors(truth, aligned) -> tuple[np.ndarray, float]:
    """Absolute start errors after removing the constant offset between the ground truth's
    audio master and ours (that offset is a property of the source, not of the aligner)."""
    diffs = []
    for t_line, a_line in zip(truth.lines, aligned.lines, strict=True):
        for t, a in zip(t_line.words, a_line.words, strict=True):
            if t.timed and a.timed:
                diffs.append(a.begin - t.begin)
    diffs = np.array(diffs)
    offset = float(np.median(diffs))
    return np.abs(diffs - offset), offset


def report(name: str, result: tuple[np.ndarray, float], stats: dict, seconds: float) -> None:
    diffs, offset = result
    print(f"{name:<12} words={len(diffs):4d}  offset={offset * 1000:+5.0f}ms  "
          f"median={np.median(diffs) * 1000:6.0f}ms  "
          f"p90={np.percentile(diffs, 90) * 1000:6.0f}ms  "
          f"<100ms={np.mean(diffs < 0.1):5.1%}  <250ms={np.mean(diffs < 0.25):5.1%}  "
          f"<500ms={np.mean(diffs < 0.5):5.1%}  conf={stats['mean_confidence']}  "
          f"low={stats['low_confidence']}  off={stats['line_offset']}  re={stats['reanchored']}  {seconds:.1f}s")


def main() -> None:
    job_dir, truth_path = Path(sys.argv[1]), Path(sys.argv[2])
    truth = parse_ttml(truth_path.read_text(encoding="utf-8"))
    audio = next(p for p in job_dir.iterdir() if p.stem == "source")

    started = time.time()
    vocals = separate_vocals(audio, job_dir)
    print(f"separation   {time.time() - started:.1f}s")
    samples = load_vocals_16k(vocals, job_dir)

    aligner = Aligner()
    for name, make in (("line-synced", line_synced_copy), ("plain", plain_copy)):
        lyrics = make(truth)
        started = time.time()
        stats = align_lyrics(lyrics, samples, aligner)
        report(name, errors(truth, lyrics), stats, time.time() - started)
    aligner.close()


if __name__ == "__main__":
    main()
