from dataclasses import dataclass

import numpy as np


@dataclass
class Piece:
    start: int  # sample index
    end: int


class VocalActivity:
    """Finds where isolated vocals are sung and cuts them into pieces Whisper can take whole:
    its model only ever hears 30 seconds, so a longer stretch would be decoded window by window
    and parts can get skipped."""

    def __init__(self, sample_rate: int = 16000, hop_seconds: float = 0.05,
                 bridge_seconds: float = 0.6, min_seconds: float = 0.3, pad_seconds: float = 0.2,
                 group_seconds: float = 25.0, max_seconds: float = 28.0, join_gap_seconds: float = 2.0,
                 relative_threshold: float = 0.06):
        self._rate = sample_rate
        self._hop = int(hop_seconds * sample_rate)
        self._bridge = int(bridge_seconds / hop_seconds)
        self._min = int(min_seconds / hop_seconds)
        self._pad = int(pad_seconds * sample_rate)
        self._group = int(group_seconds * sample_rate)
        self._max = int(max_seconds * sample_rate)
        self._join_gap = int(join_gap_seconds * sample_rate)
        self._relative = relative_threshold

    def pieces(self, samples: np.ndarray) -> list[Piece]:
        regions = self._regions(samples)
        split = [part for region in regions for part in self._split_long(samples, region)]
        return self._group_pieces(split)

    def _rms(self, samples: np.ndarray) -> np.ndarray:
        frames = len(samples) // self._hop
        if frames == 0:
            return np.zeros(0)
        trimmed = samples[: frames * self._hop].reshape(frames, self._hop)
        return np.sqrt(np.mean(trimmed.astype(np.float64) ** 2, axis=1))

    def _regions(self, samples: np.ndarray) -> list[Piece]:
        rms = self._rms(samples)
        if not len(rms) or rms.max() == 0:
            return []
        active = rms > self._relative * np.percentile(rms, 95)
        regions: list[list[int]] = []
        for i, on in enumerate(active):
            if not on:
                continue
            if regions and i - regions[-1][1] <= self._bridge:
                regions[-1][1] = i + 1
            else:
                regions.append([i, i + 1])
        out = []
        for a, b in regions:
            if b - a < self._min:
                continue
            out.append(Piece(max(0, a * self._hop - self._pad), min(len(samples), b * self._hop + self._pad)))
        return out

    def _split_long(self, samples: np.ndarray, piece: Piece) -> list[Piece]:
        """Cut anything longer than the limit at its quietest moment past the group length."""
        out, start = [], piece.start
        while piece.end - start > self._max:
            lo, hi = start + self._group // 2, start + self._max
            window = self._rms(samples[lo:hi])
            cut = lo + (int(np.argmin(window)) * self._hop if len(window) else self._max // 2)
            out.append(Piece(start, cut))
            start = cut
        out.append(Piece(start, piece.end))
        return out

    def _group_pieces(self, pieces: list[Piece]) -> list[Piece]:
        """Neighbouring phrases share a piece (Whisper hears more context) up to the group length."""
        grouped: list[Piece] = []
        for piece in pieces:
            last = grouped[-1] if grouped else None
            if (last is not None and piece.start - last.end <= self._join_gap
                    and piece.end - last.start <= self._group):
                last.end = piece.end
            else:
                grouped.append(Piece(piece.start, piece.end))
        return grouped
