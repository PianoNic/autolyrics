"""Measure the aligner on every song of the benchmark set (see collect_benchmark.py).

    python scripts/benchmark_suite.py [benchmarks_dir] [results.json]

Each song's hand-made TTML is reduced to what a typical source gives us: its line times only,
like an LRC from LRCLIB. The aligner times the words again, and every word start (and syllable
start, for syllable-synced truths) is compared with the real one. The constant offset between the
YouTube upload and the lyrics' master is measured and removed first.

Metrics: AAE (average absolute error of word starts, the MIREX measure), the share of starts
within 100 / 300 ms, and drift (the worst line's median error, which catches lines that lost
their place).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

from autolyrics.composition.container import Container
from autolyrics.domain.lyrics import Lyrics, Word
from autolyrics.infrastructure.runtime.background_priority import BackgroundPriority


class SongBenchmark:
    WORKSPACE = "v2"  # where the stems of the configured separator are cached
    def __init__(self, container: Container, folder: Path):
        self._container = container
        self._folder = folder
        self.meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        self.truth = container.ttml.parse((folder / "truth.ttml").read_text(encoding="utf-8"))

    @staticmethod
    def whole_words(words: list[Word]) -> list[Word]:
        """Syllable pieces (a piece without a trailing space continues the word) joined."""
        out: list[Word] = []
        pieces: list[Word] = []
        for i, w in enumerate(words):
            pieces.append(w)
            if w.text.endswith(" ") or i == len(words) - 1:
                timed = [p for p in pieces if p.timed]
                out.append(Word(text="".join(p.text for p in pieces),
                                begin=timed[0].begin if timed else None,
                                end=timed[-1].end if timed else None))
                pieces = []
        return out

    def merged(self, lyrics: Lyrics) -> Lyrics:
        out = lyrics.model_copy(deep=True)
        for line in out.lines:
            line.words = self.whole_words(line.words)
            line.background = self.whole_words(line.background)
        return out

    def line_synced(self) -> Lyrics:
        lyrics = self.merged(self.truth)
        lines = [line for line in lyrics.lines if line.words]
        for i, line in enumerate(lines):
            begin, end = line.bounds()
            line.begin = begin
            line.end = lines[i + 1].bounds()[0] if i + 1 < len(lines) else end
        for word in lyrics.all_words:
            word.begin = word.end = None
        return lyrics

    def run(self) -> dict:
        audio = self._folder / self.meta["audio"]
        workspace = self._folder / self.WORKSPACE
        workspace.mkdir(exist_ok=True)
        started = time.time()
        stems = self._container.separator.stems(audio, workspace)
        separated = time.time() - started
        lyrics = self.line_synced()
        started = time.time()
        self._container.aligner.align(lyrics, stems, workspace)
        aligned = time.time() - started
        return {**self.score(lyrics), "separate_s": round(separated, 1),
                "align_s": round(aligned, 1)}

    def syllables(self, aligned: Lyrics, offset: float) -> dict:
        """Start errors of the inner syllables of words both the truth and the output split
        into the same number of pieces; and how many split words the output split at all."""
        errors, truth_split, matched = [], 0, 0
        for t_line, a_line in zip(self.truth.lines, aligned.lines, strict=True):
            t_groups, a_groups = self._groups(t_line.words), self._groups(a_line.words)
            if len(t_groups) != len(a_groups):
                continue
            for tg, ag in zip(t_groups, a_groups, strict=True):
                if len(tg) < 2:
                    continue
                truth_split += 1
                if len(ag) == len(tg) and all(p.timed for p in tg + ag):
                    matched += 1
                    errors += [abs(a.begin - t.begin - offset)
                               for t, a in zip(tg[1:], ag[1:], strict=True)]
        return {"split_words": truth_split, "split_matched": matched,
                "syllable_aae": round(float(np.mean(errors)), 3) if errors else None}

    @staticmethod
    def _groups(words: list[Word]) -> list[list[Word]]:
        groups, current = [], []
        for i, w in enumerate(words):
            current.append(w)
            if w.text.endswith(" ") or i == len(words) - 1:
                groups.append(current)
                current = []
        return groups

    def score(self, aligned: Lyrics) -> dict:
        original = aligned
        truth, aligned = self.merged(self.truth), self.merged(aligned)
        pairs = [(t, a, i) for i, (t_line, a_line) in enumerate(
                     zip(truth.lines, aligned.lines, strict=True))
                 for t, a in zip(t_line.words, a_line.words, strict=True)]
        diffs = np.array([a.begin - t.begin for t, a, _ in pairs if t.timed and a.timed])
        if diffs.size == 0:
            return {"words": 0}
        offset = float(np.median(diffs))
        syllables = self.syllables(original, offset)
        errors = np.abs(diffs - offset)
        by_line: dict[int, list[float]] = {}
        for t, a, i in pairs:
            if t.timed and a.timed:
                by_line.setdefault(i, []).append(a.begin - t.begin - offset)
        drift = max(abs(float(np.median(v))) for v in by_line.values())
        missing = sum(1 for t, a, _ in pairs if t.timed and not a.timed)
        ends = np.array([a.end - t.end - offset for t, a, _ in pairs if t.timed and a.timed])
        return {"words": int(diffs.size), "missing": missing, "offset": round(offset, 3),
                "aae": round(float(errors.mean()), 3),
                "within_100": round(float((errors <= 0.1).mean()), 3),
                "within_300": round(float((errors <= 0.3).mean()), 3),
                "worst_line_drift": round(drift, 2),
                "end_aae": round(float(np.abs(ends).mean()), 3), **syllables}


def main() -> None:
    BackgroundPriority().apply()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cached_only = "--cached" in sys.argv  # only songs whose stems exist: never separate here
    root = Path(args[0]) if args else Path("benchmarks")
    out = Path(args[1]) if len(args) > 1 else root / "results.json"
    container = Container()
    results = {}
    for folder in sorted(p for p in root.iterdir() if (p / "meta.json").exists()):
        if cached_only and not (folder / SongBenchmark.WORKSPACE / "lead.wav").exists():
            continue
        try:
            results[folder.name] = SongBenchmark(container, folder).run()
        except Exception as error:  # noqa: BLE001 - report and continue with the next song
            results[folder.name] = {"error": str(error)}
        r = results[folder.name]
        print(f"{folder.name:45s} " + (f"AAE {r['aae']:.3f}s  <100ms {r['within_100']:.0%}  "
                                       f"<300ms {r['within_300']:.0%}  drift {r['worst_line_drift']}s  "
                                       f"end {r['end_aae']:.3f}s"
                                       if "aae" in r else str(r)), flush=True)
    container.aligner.release()
    scored = [r for r in results.values() if "aae" in r]
    if scored:
        summary = {k: round(float(np.mean([r[k] for r in scored])), 3)
                   for k in ("aae", "within_100", "within_300", "worst_line_drift", "end_aae")}
        results["_mean"] = summary
        print(f"{'MEAN':45s} AAE {summary['aae']:.3f}s  <100ms {summary['within_100']:.0%}  "
              f"<300ms {summary['within_300']:.0%}  drift {summary['worst_line_drift']}s  "
              f"end {summary['end_aae']:.3f}s")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
