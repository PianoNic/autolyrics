from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.infrastructure.media.ffmpeg import Ffmpeg


@dataclass
class Note:
    start: float
    end: float
    pitch_hz: float


@dataclass
class VocalEvents:
    """The "event map" of a vocal: per frame whether a voice sounds, how loud, at what pitch,
    and the sung notes. What the aligner's word ends and syllable splits are checked against."""

    frame_seconds: float
    voiced: np.ndarray  # bool per frame
    loudness_db: np.ndarray
    pitch_hz: np.ndarray
    notes: list[Note] = field(default_factory=list)

    def frame(self, seconds: float) -> int:
        return int(min(max(0, round(seconds / self.frame_seconds)), len(self.voiced) - 1))

    def voiced_until(self, seconds: float, limit: float) -> float:
        """Where the voice that sounds at `seconds` stops (at most `limit`); `seconds` itself
        when it is not voiced there."""
        t = self.frame(seconds)
        if not self.voiced[t]:
            return seconds
        end = self.frame(limit)
        stops = np.flatnonzero(~self.voiced[t:end + 1])
        stop = t + int(stops[0]) if stops.size else end
        return min(limit, stop * self.frame_seconds)

    def note_starts(self, start: float, end: float) -> list[float]:
        return [n.start for n in self.notes if start < n.start < end]


class VocalAnalyzer:
    """Pitch, voicing and loudness with SwiftF0 (MIT; a small CPU model, a song in about a
    second), and notes from its pitch track. Results are cached next to the stem."""

    SAMPLE_RATE = 16000
    MIN_GAP = 0.06  # seconds of silence shorter than this do not end a voiced stretch

    def __init__(self, ffmpeg: Ffmpeg, confidence: float = 0.5):
        self._ffmpeg = ffmpeg
        self._confidence = confidence
        self._detector = None

    def analyze(self, vocal: Path) -> VocalEvents:
        cache = vocal.with_suffix(".events.npz")
        if cache.exists() and cache.stat().st_mtime >= vocal.stat().st_mtime:
            return self._load(cache)
        from swift_f0 import FRAME_PERIOD, SwiftF0, segment_notes

        if self._detector is None:
            self._detector = SwiftF0()
        samples = self._samples(vocal)
        result = self._detector.detect(samples, self.SAMPLE_RATE)
        voiced = self._close_gaps(np.asarray(result.confidence) >= self._confidence,
                                  int(self.MIN_GAP / FRAME_PERIOD))
        notes = [Note(float(n.start), float(n.end), float(n.pitch_hz))
                 for n in segment_notes(result)]
        events = VocalEvents(FRAME_PERIOD, voiced, np.asarray(result.loudness_db, np.float32),
                             np.asarray(result.pitch_hz, np.float32), notes)
        np.savez(cache, frame_seconds=FRAME_PERIOD, voiced=voiced,
                 loudness_db=events.loudness_db, pitch_hz=events.pitch_hz,
                 notes=np.array([[n.start, n.end, n.pitch_hz] for n in notes]).reshape(-1, 3))
        return events

    def _samples(self, vocal: Path) -> np.ndarray:
        mono = vocal.with_suffix(".16k.wav")
        if not mono.exists():
            self._ffmpeg.to_wav(vocal, mono, sample_rate=self.SAMPLE_RATE, mono=True)
        data, _ = sf.read(mono, dtype="float32")
        return data

    @staticmethod
    def _close_gaps(voiced: np.ndarray, frames: int) -> np.ndarray:
        """Fill unvoiced runs shorter than `frames` inside voiced singing (consonants)."""
        out = voiced.copy()
        t, n = 0, len(out)
        while t < n:
            if out[t]:
                t += 1
                continue
            stop = t
            while stop < n and not out[stop]:
                stop += 1
            if 0 < t and stop < n and stop - t < frames:
                out[t:stop] = True
            t = stop
        return out

    @staticmethod
    def _load(cache: Path) -> VocalEvents:
        data = np.load(cache)
        notes = [Note(float(a), float(b), float(c)) for a, b, c in data["notes"]]
        return VocalEvents(float(data["frame_seconds"]), data["voiced"].astype(bool),
                           data["loudness_db"], data["pitch_hz"], notes)
