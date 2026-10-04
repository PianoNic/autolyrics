"""Quick comparison of acoustic models through the global solver on separated benchmark songs.

    python scripts/compare_aligners.py <song_dir> [<song_dir> ...]
"""

import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from benchmark_suite import SongBenchmark

from autolyrics.composition.container import Container
from autolyrics.infrastructure.ml.mms_model import MmsModel
from autolyrics.infrastructure.ml.singing.ctc_solver import GlobalCtcSolver, SolverLine
from autolyrics.infrastructure.ml.singing.lam_model import Phonemizer, SingingPhonemeModel
from autolyrics.infrastructure.ml.singing.mms_acoustic import MmsCharacterModel
from autolyrics.infrastructure.ml.text_normalizer import AlignmentTextNormalizer

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path, rate: int, ffmpeg) -> np.ndarray:
    out = path.with_name(f"{path.stem}.{rate}.wav")
    if not out.exists():
        ffmpeg.to_wav(path, out, sample_rate=rate, mono=True)
    data, _ = sf.read(out, dtype="float32")
    return data


def score(bench: SongBenchmark, spans, lyrics) -> dict:
    for s in spans:
        w = lyrics.lines[s.line].words[s.word]
        w.begin, w.end = s.begin, s.end
    return bench.score(lyrics)


def main() -> None:
    container = Container()
    language = "en"
    models = {}
    for folder in map(Path, sys.argv[1:]):
        bench = SongBenchmark(container, folder)
        language = container.languages.guess(bench.truth) or "en"
        stems = folder / "v2"
        for name in ("singing", "mms"):
            if name not in models:
                if name == "singing":
                    models[name] = SingingPhonemeModel(
                        ROOT / "models/third_party/lam/checkpoints/checkpoint_Baseline",
                        Phonemizer())
                else:
                    mms = MmsModel()
                    models[name] = MmsCharacterModel(
                        mms, AlignmentTextNormalizer(mms.alphabet, container.japanese))
            model = models[name]
            if not model.supports(language):
                continue
            for stem in ("lead", "vocals"):
                samples = load(stems / f"{stem}.wav", model.sample_rate, container.ffmpeg)
                em = model.emissions(samples)
                truth = bench.line_synced()
                lines = [SolverLine(model.tokens([w.text for w in line.words], language),
                                    line.begin) for line in truth.lines]
                for prior in (False, True):
                    started = time.time()
                    use = lines if prior else [SolverLine(l.words) for l in lines]
                    spans = GlobalCtcSolver().solve(em, use, model.word_gap, model.line_gap)
                    if prior:  # second pass with the measured offset
                        found = {s.line: s.begin for s in spans if s.word == min(
                            x.word for x in spans if x.line == s.line)}
                        offs = [found[i] - l.prior_start for i, l in enumerate(lines)
                                if i in found and l.prior_start is not None]
                        spans = GlobalCtcSolver().solve(em, use, model.word_gap, model.line_gap,
                                                        float(np.median(offs)) if offs else 0)
                    r = score(bench, spans, bench.line_synced())
                    print(f"{folder.name:30s} {name:8s} {stem:6s} prior={prior!s:5s} "
                          f"AAE {r['aae']:.3f}  <100 {r['within_100']:.0%}  "
                          f"<300 {r['within_300']:.0%}  drift {r['worst_line_drift']}  "
                          f"({time.time() - started:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
