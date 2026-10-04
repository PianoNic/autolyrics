import logging
import threading
from pathlib import Path
from statistics import mean, median

import numpy as np
import soundfile as sf

from autolyrics.application.interfaces.audio import ILyricsAligner, VocalStems
from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
from autolyrics.domain.lyrics import Line, Lyrics, Word
from autolyrics.domain.services.language_guesser import LanguageGuesser
from autolyrics.domain.services.offset_estimator import OffsetEstimator
from autolyrics.domain.services.timing_repairer import TimingRepairer
from autolyrics.infrastructure.media.ffmpeg import Ffmpeg
from autolyrics.infrastructure.ml.japanese_text import WordSegmenter
from autolyrics.infrastructure.ml.singing.acoustic import Emissions, IAcousticModel
from autolyrics.infrastructure.ml.singing.ctc_solver import GlobalCtcSolver, SolverLine, WordSpan
from autolyrics.infrastructure.ml.singing.syllables import SyllableTimer
from autolyrics.infrastructure.ml.singing.timing_judge import TimingJudge, WordEvidence
from autolyrics.infrastructure.ml.singing.vocal_analyzer import VocalAnalyzer, VocalEvents

log = logging.getLogger(__name__)


class AcousticModels:
    """Loads the acoustic models on first use and frees them together: the singing model for
    the languages it was trained on, MMS for the rest."""

    def __init__(self, singing_factory, mms_factory):
        self._factories = {"singing": singing_factory, "mms": mms_factory}
        self._loaded: dict[str, IAcousticModel] = {}

    def for_language(self, language: str) -> IAcousticModel:
        singing = self._get("singing")
        return singing if singing is not None and singing.supports(language) else self._get("mms")

    def _get(self, name: str) -> IAcousticModel | None:
        if name not in self._loaded:
            try:
                self._loaded[name] = self._factories[name]()
            except Exception as error:
                if name == "mms":
                    raise
                log.warning("singing model unavailable, using MMS: %s", error)
                self._loaded[name] = None
        return self._loaded[name]

    def release(self) -> None:
        for model in self._loaded.values():
            if model is not None:
                model.close()
        self._loaded.clear()


class SingingLyricsAligner(ILyricsAligner):
    """Pipeline v2 word timing.

    1. The acoustic model listens to the dry lead vocal (a model trained on singing where the
       language allows).
    2. One CTC Viterbi over the whole song places every word; the source's line times are a soft
       pull, measured for a constant offset first and then applied with it.
    3. Word ends follow the voice: a held note lasts as long as it sounds, not until the next
       word happens to start.
    4. Background lines are placed on the backing-vocal stem, near their main line.
    """

    TOKEN_SECONDS = 0.08  # typical length of one sung phoneme or letter
    MAX_HOLD = 4.0  # seconds a word may be held past where the aligner ended it
    BACKGROUND_BEFORE, BACKGROUND_AFTER = 1.5, 2.5

    def __init__(self, ffmpeg: Ffmpeg, models: AcousticModels, solver: GlobalCtcSolver,
                 analyzer: VocalAnalyzer, repairer: TimingRepairer, offsets: OffsetEstimator,
                 languages: LanguageGuesser, segmenter: WordSegmenter,
                 syllables: SyllableTimer, judge: TimingJudge | None = None):
        self._syllables = syllables
        self._timing_judge = judge or TimingJudge()
        self.last_evidence: dict = {}
        self._ffmpeg = ffmpeg
        self._models = models
        self._solver = solver
        self._analyzer = analyzer
        self._repairer = repairer
        self._offsets = offsets
        self._languages = languages
        self._segmenter = segmenter
        self._lock = threading.Lock()

    # -- ILyricsAligner -------------------------------------------------------

    def align(self, lyrics: Lyrics, stems: VocalStems, workspace: Path,
              progress: IProgress = NO_PROGRESS) -> dict:
        with self._lock:
            language = self._languages.guess(lyrics) or "en"
            model = self._models.for_language(language)
            segmented = 0
            if model.word_gap is None:
                # A model without word boundaries needs the words of space-less scripts first.
                segmented = self._segmenter.segment(lyrics, language)
            lines = lyrics.content_lines
            line_synced = bool(lines) and all(line.begin is not None for line in lines)
            for word in (w for line in lines for w in line.all_words):
                word.begin = word.end = word.confidence = None
                word.flags = []

            progress.update(None, "listening to the vocals")
            heard = self._hear(model, stems, workspace)
            em = self._combine(heard)
            progress.update(0.3, "placing every word")
            offset, placed, solver_lines = self._place(lines, model, em, language, line_synced)
            progress.update(0.5, "judging every word")
            events = self._analyzer.analyze(stems.lead)
            self._judge(lines, model, solver_lines, placed, heard, offset, events)
            progress.update(0.65, "following the voice")
            self._follow_voice(lines, events)
            syllables = self._split_syllables(lines, placed, model, language, em.frame_seconds)
            progress.update(0.75, "background vocals")
            backing = stems.backing if stems.backing and stems.backing.exists() else stems.lead
            self._align_background(lines, model, language,
                                   self._emissions(model, backing, workspace))
            for line in lines:
                self._repairer.repair(line)
                line.begin = line.end = None
            progress.update(1.0, "done")
            stats = self._stats(lyrics, model, language, line_synced, offset, segmented)
            return {**stats, "syllable_words": syllables}

    def measure_offset(self, lyrics: Lyrics, stems: VocalStems, workspace: Path) -> dict:
        probe = lyrics.model_copy(deep=True)
        for line in probe.lines:
            bounds = line.bounds()
            if bounds is not None:
                line.begin, line.end = bounds
        self.align(probe, stems, workspace)
        return self._offsets.word_offset(lyrics, probe)

    def realign_line(self, line: Line, stems: VocalStems, workspace: Path, language: str,
                     start: float, end: float) -> bool:
        with self._lock:
            model = self._models.for_language(language)
            em = self._combine(self._hear(model, stems, workspace))
            tokens = model.tokens([w.text for w in line.words], language)
            spans = self._solve_window(em, tokens, model, start, end)
            if not spans:
                return False
            for w in line.all_words:
                w.begin = w.end = w.confidence = None
            self._apply(spans, [line])
            self._follow_voice([line], self._analyzer.analyze(stems.lead), limit=end)
            self._repairer.repair(line, window=(start, end))
            return True

    def release(self) -> None:
        with self._lock:
            self._models.release()

    # -- placing words --------------------------------------------------------

    def _place(self, lines: list[Line], model: IAcousticModel, em: Emissions, language: str,
               line_synced: bool) -> tuple[float, dict, list[SolverLine]]:
        solver_lines = []
        for i, line in enumerate(lines):
            prior_end = None
            if line_synced:
                # A line-synced source's line lasts until the next one begins.
                prior_end = lines[i + 1].begin if i + 1 < len(lines) else line.end
            solver_lines.append(SolverLine(model.tokens([w.text for w in line.words], language),
                                           line.begin if line_synced else None, prior_end))
        spans = self._solver.solve(em, solver_lines, model.word_gap, model.line_gap)
        offset = 0.0
        if line_synced:
            # The source's times may belong to another master of the song: measure the constant
            # offset, then pull with it.
            starts = {}
            for s in spans:
                starts.setdefault(s.line, s.begin)
            diffs = [starts[i] - line.begin for i, line in enumerate(lines) if i in starts]
            offset = float(median(diffs)) if diffs else 0.0
            if abs(offset) > 0.05:
                spans = self._solver.solve(em, solver_lines, model.word_gap, model.line_gap,
                                           prior_offset=offset)
        self._apply(spans, lines)
        placed = {(s.line, s.word): (s, solver_lines[s.line].words[s.word]) for s in spans}
        return offset, placed, solver_lines

    # -- judging --------------------------------------------------------------

    def _judge(self, lines: list[Line], model: IAcousticModel, solver_lines: list[SolverLine],
               placed: dict, heard: list[Emissions], offset: float,
               events: VocalEvents) -> None:
        """Every word gets a calibrated probability that its timing is right (its confidence),
        and a flag when that is low. The strongest evidence is agreement: the lead alone and
        all vocals alone are solved separately, and a word they disagree on is a guess."""
        separate = []
        if len(heard) > 1:
            for em in heard:
                spans = self._solver.solve(em, solver_lines, model.word_gap, model.line_gap,
                                           prior_offset=offset)
                separate.append({(s.line, s.word): s.begin for s in spans})
        self.last_evidence = {}
        for (li, wi), (span, tokens) in placed.items():
            word = lines[li].words[wi]
            begins = [found[(li, wi)] for found in separate if (li, wi) in found]
            line = solver_lines[li]
            outside = 0.0
            if line.prior_start is not None and line.prior_end is not None:
                lo, hi = line.prior_start + offset, line.prior_end + offset
                outside = max(0.0, lo - span.begin, span.end - hi)
            evidence = WordEvidence(
                score=span.score,
                disagreement=max(begins) - min(begins) if len(begins) > 1 else 0.0,
                outside_window=outside,
                voiced_start=events.voiced_near(span.begin, 0.1),
                duration_ratio=(span.end - span.begin) / (len(tokens) * self.TOKEN_SECONDS))
            probability = self._timing_judge.probability(evidence)
            self.last_evidence[(li, wi)] = evidence
            word.confidence = round(probability, 3)
            if probability < self._timing_judge.UNSURE:
                word.flag("low-confidence")

    def _split_syllables(self, lines: list[Line], placed: dict, model: IAcousticModel,
                         language: str, frame_seconds: float) -> int:
        """Words become their timed syllables where the aligner heard each one start."""
        phonemes = model.word_gap is not None
        split = 0
        for li, line in enumerate(lines):
            words: list[Word] = []
            for wi, word in enumerate(line.words):
                found = placed.get((li, wi))
                pieces = ([word] if found is None else
                          self._syllables.split(word, found[0], found[1], language, phonemes,
                                                frame_seconds))
                split += len(pieces) > 1
                words.extend(pieces)
            line.words = words
        return split

    @staticmethod
    def _apply(spans: list[WordSpan], lines: list[Line]) -> None:
        for s in spans:
            word = lines[s.line].words[s.word]
            word.begin, word.end, word.confidence = round(s.begin, 3), round(s.end, 3), s.score

    def _solve_window(self, em: Emissions, tokens: list[list[int]], model: IAcousticModel,
                      start: float, end: float) -> list[WordSpan]:
        lo, hi = max(0, em.frame(start)), min(em.frames, em.frame(end))
        if hi - lo < 2 * sum(len(t) for t in tokens) + 1:
            return []
        window = Emissions(em.logp[lo:hi], em.frame_seconds, em.blank)
        spans = self._solver.solve(window, [SolverLine(tokens)], model.word_gap, model.line_gap)
        shift = em.seconds(lo)
        for s in spans:
            s.begin += shift
            s.end += shift
        return spans

    # -- following the voice --------------------------------------------------

    def _follow_voice(self, lines: list[Line], events: VocalEvents,
                      limit: float | None = None) -> None:
        """CTC ends a word on its last peak; a sung word lasts while the voice holds it. Each
        word is extended through the voiced stretch it ends in, up to the next word."""
        words = sorted((w for line in lines for w in line.words if w.timed),
                       key=lambda w: w.begin)
        for i, word in enumerate(words):
            nxt = words[i + 1].begin if i + 1 < len(words) else (limit or word.end + self.MAX_HOLD)
            cap = min(nxt, word.end + self.MAX_HOLD)
            held = events.voiced_until(max(word.begin, word.end - events.frame_seconds), cap)
            if held > word.end:
                word.end = round(held, 3)

    # -- background vocals ----------------------------------------------------

    def _align_background(self, lines: list[Line], model: IAcousticModel, language: str,
                          em: Emissions) -> None:
        for line in lines:
            if not line.background:
                continue
            timed = [w for w in line.words if w.timed]
            if not timed:
                continue
            tokens = model.tokens([w.text for w in line.background], language)
            spans = self._solve_window(em, tokens, model,
                                       timed[0].begin - self.BACKGROUND_BEFORE,
                                       timed[-1].end + self.BACKGROUND_AFTER)
            for s in spans:
                word = line.background[s.word]
                word.begin, word.end, word.confidence = round(s.begin, 3), round(s.end, 3), s.score

    # -- helpers --------------------------------------------------------------

    def _hear(self, model: IAcousticModel, stems: VocalStems, workspace: Path) -> list[Emissions]:
        """What the model hears in the dry lead and in all vocals."""
        heard = [self._emissions(model, stems.lead, workspace)]
        if stems.vocals != stems.lead and stems.vocals.exists():
            heard.append(self._emissions(model, stems.vocals, workspace))
        return heard

    @staticmethod
    def _combine(heard: list[Emissions]) -> Emissions:
        """Both hearings averaged. The lead is clean where the singer is clear; the full vocals
        keep what the lead/backing split takes from a whispered or doubled lead. Together they
        beat either one on every benchmark song."""
        if len(heard) == 1:
            return heard[0]
        frames = min(em.frames for em in heard)
        logp = np.logaddexp(heard[0].logp[:frames], heard[1].logp[:frames]) - np.log(2.0)
        return Emissions(logp.astype(np.float32), heard[0].frame_seconds, heard[0].blank)

    def _emissions(self, model: IAcousticModel, vocal: Path, workspace: Path) -> Emissions:
        cache = workspace / f"{vocal.stem}.{model.name}.npz"
        if cache.exists() and cache.stat().st_mtime >= vocal.stat().st_mtime:
            data = np.load(cache)
            return Emissions(data["logp"], float(data["frame_seconds"]), int(data["blank"]))
        mono = workspace / f"{vocal.stem}.{model.sample_rate}.wav"
        if not mono.exists() or mono.stat().st_mtime < vocal.stat().st_mtime:
            self._ffmpeg.to_wav(vocal, mono, sample_rate=model.sample_rate, mono=True)
        samples, _ = sf.read(mono, dtype="float32")
        em = model.emissions(samples)
        np.savez(cache, logp=em.logp, frame_seconds=em.frame_seconds, blank=em.blank)
        return em

    def _stats(self, lyrics: Lyrics, model: IAcousticModel, language: str, line_synced: bool,
               offset: float, segmented: int) -> dict:
        words: list[Word] = [w for line in lyrics.content_lines for w in line.all_words]
        scored = [w.confidence for w in words if w.confidence is not None]
        return {
            "engine": "v2", "acoustic_model": model.name, "language": language,
            "mode": "global, line-prior" if line_synced else "global",
            "line_offset": round(offset, 3), "words": len(words),
            "low_confidence": sum("low-confidence" in w.flags for w in words),
            "interpolated": sum("interpolated" in w.flags for w in words),
            "reanchored": 0, "failed_lines": 0, "source_timed_lines": 0,
            "mean_confidence": round(mean(scored), 3) if scored else None,
            "segmented_words": segmented,
        }
