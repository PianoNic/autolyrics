"""Forced alignment: known lyrics text + isolated vocals -> a time for every word."""

import threading
from pathlib import Path
from statistics import mean

import numpy as np
import soundfile as sf

from autolyrics.application.interfaces.audio import ILyricsAligner
from autolyrics.domain.lyrics import Line, Lyrics, Word
from autolyrics.domain.services.language_guesser import LanguageGuesser
from autolyrics.domain.services.offset_estimator import OffsetEstimator
from autolyrics.domain.services.timing_repairer import TimingRepairer
from autolyrics.infrastructure.media.ffmpeg import Ffmpeg
from autolyrics.infrastructure.ml.mms_model import MmsModel
from autolyrics.infrastructure.ml.text_normalizer import AlignmentTextNormalizer


class AlignmentRun:
    """One recording's emissions plus the model, for aligning words inside time windows."""

    def __init__(self, model: MmsModel, normalizer: AlignmentTextNormalizer,
                 samples: np.ndarray, language: str):
        self.model = model
        self.normalizer = normalizer
        self.language = language
        self.duration = len(samples) / MmsModel.SAMPLE_RATE
        self.emission = model.emissions(samples)

    def align_words(self, words: list[Word], start: float, end: float) -> bool:
        """Time `words` inside [start, end]. Words without letters stay untimed."""
        alignable = [(w, n) for w in words
                     if (n := self.normalizer.normalize(w.text, self.language))]
        if not alignable:
            return False
        start, end = max(0.0, start), min(self.duration, end)
        lo = MmsModel.frame(start)
        hi = min(self.emission.shape[0], MmsModel.frame_ceil(end))
        spans = self.model.align(self.emission[lo:hi], [n for _, n in alignable], lo)
        if spans is None:
            return False
        for (word, _), span in zip(alignable, spans, strict=True):
            word.begin, word.end, word.confidence = span.begin, span.end, span.score
        return True

    def align_song(self, lines: list[Line]) -> None:
        """The whole song in one pass, with a star between lines."""
        transcript: list[str] = []
        owners: list[Word | None] = []
        for line in lines:
            for w in line.words:
                n = self.normalizer.normalize(w.text, self.language)
                if n:
                    transcript.append(n)
                    owners.append(w)
            transcript.append("*")
            owners.append(None)
        spans = self.model.align(self.emission, transcript[:-1], 0)
        if spans is None:
            raise RuntimeError("the lyrics are longer than the audio can hold")
        for word, span in zip(owners[:-1], spans, strict=True):
            if word is not None:
                word.begin, word.end, word.confidence = span.begin, span.end, span.score


class MmsLyricsAligner(ILyricsAligner):
    """Aligns lyrics with MMS_FA. A whole-song pass first: it is the result for plain text, and
    for line-synced text it measures, line by line, how far the given line times sit from this
    audio, so each line can then be aligned inside its shifted window."""

    VOCALS_16K = "vocals16k.wav"
    LINE_PADDING = 0.75  # seconds of slack around a line-synced line's window
    WIDER = 3.0  # extra seconds when a line does not fit its window

    def __init__(self, ffmpeg: Ffmpeg, repairer: TimingRepairer, offsets: OffsetEstimator,
                 languages: LanguageGuesser):
        self._ffmpeg = ffmpeg
        self._repairer = repairer
        self._offsets = offsets
        self._languages = languages
        self._model: MmsModel | None = None
        self._lock = threading.Lock()

    # -- ILyricsAligner -------------------------------------------------------

    def align(self, lyrics: Lyrics, vocals: Path, workspace: Path) -> dict:
        with self._lock:
            run = self._run(vocals, workspace, self._languages.guess(lyrics))
            return self._align(lyrics, run)

    def measure_offset(self, lyrics: Lyrics, vocals: Path, workspace: Path) -> dict:
        with self._lock:
            probe = lyrics.model_copy(deep=True)
            self._align(probe, self._run(vocals, workspace, self._languages.guess(lyrics)))
            return self._offsets.word_offset(lyrics, probe)

    def realign_line(self, line: Line, vocals: Path, workspace: Path, language: str,
                     start: float, end: float) -> bool:
        with self._lock:
            samples = self._samples(vocals, workspace)
            # Emissions only around the line: an edit should take a second, not a song's worth.
            lo = max(0, int((start - 1) * MmsModel.SAMPLE_RATE))
            hi = min(len(samples), int((end + 1) * MmsModel.SAMPLE_RATE))
            shift = lo / MmsModel.SAMPLE_RATE
            run = AlignmentRun(self._ensure_model(), self._normalizer(), samples[lo:hi], language)
            for w in line.all_words:
                w.begin = w.end = w.confidence = None
                w.flags = []
            ok = run.align_words(line.words, start - shift, end - shift) if line.words else True
            if line.background:
                run.align_words(line.background, start - shift, end - shift)
            self._repairer.repair(line, window=(start - shift, end - shift))
            line.begin = line.end = None
            for w in line.all_words:
                if w.timed:
                    w.begin, w.end = round(w.begin + shift, 3), round(w.end + shift, 3)
            return ok

    def release(self) -> None:
        with self._lock:
            if self._model is not None:
                self._model.close()
                self._model = None

    # -- internals ------------------------------------------------------------

    def _ensure_model(self) -> MmsModel:
        if self._model is None:
            self._model = MmsModel()
        return self._model

    def _normalizer(self) -> AlignmentTextNormalizer:
        return AlignmentTextNormalizer(self._ensure_model().alphabet)

    def _samples(self, vocals: Path, workspace: Path) -> np.ndarray:
        wav = workspace / self.VOCALS_16K
        if not wav.exists():
            self._ffmpeg.to_wav(vocals, wav, sample_rate=MmsModel.SAMPLE_RATE, mono=True)
        data, _ = sf.read(wav, dtype="float32")
        return data

    def _run(self, vocals: Path, workspace: Path, language: str) -> AlignmentRun:
        return AlignmentRun(self._ensure_model(), self._normalizer(),
                            self._samples(vocals, workspace), language)

    def _window(self, line: Line, duration: float, offset: float) -> tuple[float, float]:
        return (max(0.0, line.begin + offset - self.LINE_PADDING),
                min(duration, line.end + offset + self.LINE_PADDING))

    def _align(self, lyrics: Lyrics, run: AlignmentRun) -> dict:
        lines = lyrics.content_lines
        line_synced = all(line.begin is not None and line.end is not None for line in lines)
        for w in (w for line in lines for w in line.all_words):
            w.begin = w.end = w.confidence = None
            w.flags = []

        run.align_song(lines)
        line_offset, failed = 0.0, 0
        if line_synced:
            offsets = self._offsets.local_line_offsets(lines)
            line_offset = float(np.median(offsets)) if offsets else 0.0
            for line, offset in zip(lines, offsets or [0.0] * len(lines), strict=True):
                start, end = self._window(line, run.duration, offset)
                # When the window misses, the line timing may be off: retry wider, else keep
                # the whole-song pass.
                if (line.words and not run.align_words(line.words, start, end)
                        and not run.align_words(line.words, start - self.WIDER,
                                                end + self.WIDER)):
                    failed += 1

        for line in lines:
            self._align_background(line, run, line_offset)
        for line in lines:
            self._repairer.repair(line)
            line.begin = line.end = None  # word times are the truth now

        words = [w for line in lines for w in line.all_words]
        scored = [w.confidence for w in words if w.confidence is not None]
        return {
            "language": run.language,
            "mode": "line-windows" if line_synced else "global",
            "line_offset": round(line_offset, 3),
            "words": len(words),
            "low_confidence": sum("low-confidence" in w.flags for w in words),
            "interpolated": sum("interpolated" in w.flags for w in words),
            "reanchored": sum("reanchored" in w.flags for w in words),
            "mean_confidence": round(mean(scored), 3) if scored else None,
            "failed_lines": failed,
        }

    def _align_background(self, line: Line, run: AlignmentRun, line_offset: float) -> None:
        """Background vocals overlap the main line, so they get their own pass around it."""
        if not line.background:
            return
        timed = [w for w in line.words if w.timed]
        if timed:
            start, end = timed[0].begin - 1.5, timed[-1].end + 2.5
        elif line.begin is not None:
            start, end = self._window(line, run.duration, line_offset)
        else:
            return
        run.align_words(line.background, start, end)
