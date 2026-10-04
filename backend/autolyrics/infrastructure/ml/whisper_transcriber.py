"""Whisper transcription of isolated vocals: the fallback when no lyrics source has the song."""

import gc
import logging
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.application.interfaces.audio import ITranscriber
from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
from autolyrics.domain.lyrics import Line, Lyrics, Metadata, Word
from autolyrics.domain.services.language_guesser import LanguageGuesser
from autolyrics.infrastructure.media.ffmpeg import Ffmpeg
from autolyrics.infrastructure.ml.vocal_activity import VocalActivity

log = logging.getLogger(__name__)


class WhisperTranscriber(ITranscriber):
    """Whisper through `transformers`, on the GPU when there is one, with word timestamps: the
    line matcher needs to know where each heard word is. Words are grouped into lines at pauses
    and sentence ends; the forced aligner later times the final text more precisely."""

    SAMPLE_RATE = 16000
    VOCALS_16K = "vocals16k.wav"
    BATCH = 8  # pieces per GPU batch; also how often the progress moves
    GHOST = 0.02  # seconds: shorter "words" are Whisper repeating itself, not singing
    PAUSE = 0.6  # seconds of silence that end a line
    LINE_WORDS = 14  # a line longer than this is split at the next word
    SENTENCE_END = (".", "!", "?")

    def __init__(self, ffmpeg: Ffmpeg, languages: LanguageGuesser, activity: VocalActivity,
                 model_id: str = "openai/whisper-large-v3-turbo"):
        self._ffmpeg = ffmpeg
        self._activity = activity
        self._languages = languages
        self._model_id = model_id
        self._pipeline = None
        self._lock = threading.Lock()

    def transcribe(self, vocals: Path, workspace: Path, language: str | None = None,
                   progress: IProgress = NO_PROGRESS) -> Lyrics:
        with self._lock:
            progress.update(None, "loading Whisper")
            samples = self._samples(vocals, workspace)
            asr = self._ensure_pipeline()
            language = language or self._detect_language(asr, samples)
            kwargs = {"task": "transcribe"}
            if language:
                kwargs["language"] = language
            # Whisper hears 30 s at a time. Each sung stretch of the isolated vocals is cut into a
            # piece of at most that and transcribed on its own, so nothing is skipped the way
            # long-form decoding can skip when it loses its place.
            pieces = self._activity.pieces(samples)
            inputs = [{"raw": samples[p.start:p.end], "sampling_rate": self.SAMPLE_RATE}
                      for p in pieces]
            results = []
            for first in range(0, len(inputs), self.BATCH):
                batch = inputs[first:first + self.BATCH]
                results += asr(batch, return_timestamps="word", batch_size=self.BATCH,
                               generate_kwargs=kwargs)
                done = first + len(batch)
                progress.update(done / len(inputs), f"{done} of {len(inputs)} pieces")
            heard = [self._heard_words(result, piece.start / self.SAMPLE_RATE)
                     for piece, result in zip(pieces, results, strict=True)]
            lyrics = self._to_lyrics(heard, len(samples) / self.SAMPLE_RATE)
            lyrics.metadata.language = language or self._languages.guess(lyrics)
            return lyrics

    def release(self) -> None:
        with self._lock:
            if self._pipeline is None:
                return
            self._pipeline = None
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    # -- internals ------------------------------------------------------------

    def _ensure_pipeline(self):
        if self._pipeline is None:
            import torch
            from transformers import pipeline

            cuda = torch.cuda.is_available()
            self._pipeline = pipeline(
                "automatic-speech-recognition", model=self._model_id,
                dtype=torch.float16 if cuda else torch.float32,
                device="cuda" if cuda else "cpu")
        return self._pipeline

    def _samples(self, vocals: Path, workspace: Path) -> np.ndarray:
        wav = workspace / self.VOCALS_16K
        if not wav.exists():
            self._ffmpeg.to_wav(vocals, wav, sample_rate=self.SAMPLE_RATE, mono=True)
        data, _ = sf.read(wav, dtype="float32")
        return data

    def _detect_language(self, asr, samples: np.ndarray) -> str | None:
        """Whisper's own language guess on the loudest half minute (an intro may be silent)."""
        try:
            window = 30 * self.SAMPLE_RATE
            if len(samples) > window:
                energy = np.convolve(np.abs(samples), np.ones(self.SAMPLE_RATE), "valid")
                start = int(np.argmax(energy[: max(1, len(energy) - window)]))
                clip = samples[start: start + window]
            else:
                clip = samples
            features = asr.feature_extractor(clip, sampling_rate=self.SAMPLE_RATE,
                                             return_tensors="pt").input_features
            features = features.to(asr.model.device, dtype=asr.model.dtype)
            token = asr.model.detect_language(features)[0]
            code = asr.tokenizer.decode([int(token)]).strip("<|>")
            return code if 2 <= len(code) <= 3 else None
        except Exception as error:  # noqa: BLE001 - an API difference must not stop the transcription
            log.warning("Whisper language detection failed, transcribing without it: %s", error)
            return None

    def _heard_words(self, result: dict, offset: float) -> list[tuple[str, float, float]]:
        """One piece's words as (text, begin, end) in song time, without the ghosts."""
        words = []
        for chunk in result.get("chunks") or []:
            text = (chunk.get("text") or "").strip()
            begin, end = chunk.get("timestamp") or (None, None)
            if not text or begin is None or end is None or end - begin < self.GHOST:
                continue
            words.append((text, float(begin) + offset, float(end) + offset))
        return words

    def _to_lyrics(self, pieces: list[list[tuple[str, float, float]]],
                   duration: float) -> Lyrics:
        """Timed words grouped into lines: a line ends at a pause, a sentence end, the end of a
        piece, or when it grows too long."""
        lines: list[Line] = []
        for piece in pieces:
            current: list[tuple[str, float, float]] = []
            for word in piece:
                if current and (word[1] - current[-1][2] >= self.PAUSE
                                or current[-1][0].endswith(self.SENTENCE_END)
                                or len(current) >= self.LINE_WORDS):
                    lines.append(self._line(current))
                    current = []
                current.append(word)
            if current:
                lines.append(self._line(current))
        return Lyrics(lines=lines, metadata=Metadata(duration=duration))

    @staticmethod
    def _line(words: list[tuple[str, float, float]]) -> Line:
        last = len(words) - 1
        return Line(words=[Word(text=text + (" " if i < last else ""), begin=begin, end=end)
                           for i, (text, begin, end) in enumerate(words)],
                    begin=words[0][1], end=words[-1][2])
