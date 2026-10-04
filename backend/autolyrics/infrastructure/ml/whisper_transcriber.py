"""Whisper transcription of isolated vocals: the fallback when no lyrics source has the song."""

import gc
import logging
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.application.interfaces.audio import ITranscriber
from autolyrics.domain.lyrics import Line, Lyrics, Metadata, Word
from autolyrics.domain.services.language_guesser import LanguageGuesser
from autolyrics.infrastructure.media.ffmpeg import Ffmpeg

log = logging.getLogger(__name__)


class WhisperTranscriber(ITranscriber):
    """Whisper through `transformers`, on the GPU when there is one. Its segments become lines;
    the words are left untimed because the forced aligner times them far more precisely."""

    SAMPLE_RATE = 16000
    VOCALS_16K = "vocals16k.wav"

    def __init__(self, ffmpeg: Ffmpeg, languages: LanguageGuesser,
                 model_id: str = "openai/whisper-large-v3-turbo"):
        self._ffmpeg = ffmpeg
        self._languages = languages
        self._model_id = model_id
        self._pipeline = None
        self._lock = threading.Lock()

    def transcribe(self, vocals: Path, workspace: Path, language: str | None = None) -> Lyrics:
        with self._lock:
            samples = self._samples(vocals, workspace)
            asr = self._ensure_pipeline()
            language = language or self._detect_language(asr, samples)
            kwargs = {"task": "transcribe"}
            if language:
                kwargs["language"] = language
            # Whisper's own sequential long-form decoding (no chunk_length_s): it returns one
            # segment per phrase, which become the lines. Chunked decoding merges them.
            result = asr({"raw": samples, "sampling_rate": self.SAMPLE_RATE},
                         return_timestamps=True, generate_kwargs=kwargs)
            lyrics = self._to_lyrics(result.get("chunks") or [], len(samples) / self.SAMPLE_RATE)
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

    @staticmethod
    def _to_lyrics(chunks: list[dict], duration: float) -> Lyrics:
        lines = []
        for chunk in chunks:
            text = (chunk.get("text") or "").strip()
            words = Word.tokenize(text)
            if not words:
                continue
            begin, end = chunk.get("timestamp") or (None, None)
            begin = float(begin) if begin is not None else None
            end = float(end) if end is not None else None
            if begin is not None and (end is None or end <= begin):
                end = min(duration, begin + max(1.0, 0.4 * len(words)))
            lines.append(Line(words=words, begin=begin, end=end))
        if lines and any(line.begin is None for line in lines):
            # Without usable segment times the aligner places everything itself.
            for line in lines:
                line.begin = line.end = None
        return Lyrics(lines=lines, metadata=Metadata(duration=duration))
