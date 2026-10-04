from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class Emissions:
    """Per-frame log-probabilities of an acoustic model over its token set."""

    logp: np.ndarray  # (frames, tokens), float32
    frame_seconds: float
    blank: int

    @property
    def frames(self) -> int:
        return self.logp.shape[0]

    def frame(self, seconds: float) -> int:
        return round(seconds / self.frame_seconds)

    def seconds(self, frame: float) -> float:
        return frame * self.frame_seconds


class IAcousticModel(ABC):
    """Turns a vocal recording into token probabilities, and words into token sequences."""

    name: str
    sample_rate: int
    # Token sung between words (the singing model was trained with one), or None.
    word_gap: int | None = None
    # Token that soaks up sound the lyrics do not cover, put between lines, or None.
    line_gap: int | None = None

    @abstractmethod
    def supports(self, language: str) -> bool: ...

    @abstractmethod
    def emissions(self, samples: np.ndarray) -> Emissions:
        """`samples`: mono float32 at `sample_rate`."""

    @abstractmethod
    def tokens(self, words: list[str], language: str) -> list[list[int]]:
        """Each word's tokens; an empty list for a word with nothing to align."""

    @abstractmethod
    def close(self) -> None:
        """Free the model (GPU memory)."""
