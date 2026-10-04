"""Fit the timing judge (TimingJudge) on the benchmark songs.

    python scripts/fit_judge.py [benchmarks_dir]

Every word of every separated song is aligned; its evidence is labelled "right" when its start
lies within 0.3 s of the hand-made timing (after removing the song's constant offset). A logistic
regression over the evidence gives the weights to paste into TimingJudge. Songs are split
alternately into fitting and checking halves, so the reported quality is on unseen songs.
"""

import sys
from pathlib import Path

import numpy as np
from benchmark_suite import SongBenchmark

from autolyrics.composition.container import Container
from autolyrics.infrastructure.runtime.background_priority import BackgroundPriority

RIGHT = 0.3


def collect(container: Container, folder: Path) -> tuple[np.ndarray, np.ndarray]:
    bench = SongBenchmark(container, folder)
    workspace = folder / SongBenchmark.WORKSPACE
    stems = container.separator.stems(folder / bench.meta["audio"], workspace)
    lyrics = bench.line_synced()
    truth = bench.merged(bench.truth)
    lines = [line for line in lyrics.lines]
    original = [[w.model_copy() for w in line.words] for line in lines]
    container.aligner.align(lyrics, stems, workspace)
    evidence = container.aligner.last_evidence
    diffs, rows = [], []
    content = [i for i, line in enumerate(truth.lines) if line.words]
    for (li, wi), ev in evidence.items():
        t_word = truth.lines[content[li]].words[wi] if li < len(content) else None
        a_begin = _begin_of(lyrics.lines[content[li]], original[content[li]], wi)
        if t_word is None or not t_word.timed or a_begin is None:
            continue
        diffs.append(a_begin - t_word.begin)
        rows.append(ev.features())
    diffs = np.array(diffs)
    offset = float(np.median(diffs)) if diffs.size else 0.0
    return np.array(rows), (np.abs(diffs - offset) <= RIGHT).astype(int)


def _begin_of(line, original_words, index: int) -> float | None:
    """The begin of the index-th original word after syllable splitting."""
    groups, current = [], []
    for i, w in enumerate(line.words):
        current.append(w)
        if w.text.endswith(" ") or i == len(line.words) - 1:
            groups.append(current)
            current = []
    if index >= len(groups) or len(groups) != len(original_words):
        return None
    return groups[index][0].begin


def main() -> None:
    BackgroundPriority().apply()
    from sklearn.linear_model import LogisticRegression

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("benchmarks")
    container = Container()
    folders = sorted(p for p in root.iterdir()
                     if (p / SongBenchmark.WORKSPACE / "lead.wav").exists())
    data = []
    for folder in folders:
        x, y = collect(container, folder)
        print(f"{folder.name:40s} words {len(y):4d}  right {y.mean():.0%}", flush=True)
        data.append((x, y))
    fit = [d for i, d in enumerate(data) if i % 2 == 0]
    check = [d for i, d in enumerate(data) if i % 2 == 1] or fit
    x_fit, y_fit = np.vstack([d[0] for d in fit]), np.concatenate([d[1] for d in fit])
    x_check, y_check = np.vstack([d[0] for d in check]), np.concatenate([d[1] for d in check])
    model = LogisticRegression(max_iter=1000).fit(x_fit, y_fit)
    probability = model.predict_proba(x_check)[:, 1]
    for threshold in (0.5, 0.7, 0.8, 0.85, 0.9, 0.95):
        flagged = probability < threshold
        caught = (flagged & (y_check == 0)).sum() / max(1, (y_check == 0).sum())
        precision = (flagged & (y_check == 0)).sum() / max(1, flagged.sum())
        print(f"threshold {threshold}: flags {flagged.mean():.0%} of words, catches "
              f"{caught:.0%} of wrong ones, {precision:.0%} of flags are really wrong")
    final = LogisticRegression(max_iter=1000).fit(
        np.vstack([d[0] for d in data]), np.concatenate([d[1] for d in data]))
    print("WEIGHTS =", [round(float(w), 3) for w in final.coef_[0]])
    print("BIAS =", round(float(final.intercept_[0]), 3))
    container.aligner.release()


if __name__ == "__main__":
    main()
