import math
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class WordEvidence:
    """What the aligner knows about one placed word, for the judge."""

    score: float  # mean token probability in the combined emissions (0..1)
    disagreement: float  # seconds between where the lead-only and all-vocals solves put it
    outside_window: float  # seconds outside its line's source span (0 when inside or no span)
    voiced_start: bool  # a voice starts or sounds within 0.1 s of the word start
    duration_ratio: float  # duration / (tokens x typical token length)

    def features(self) -> list[float]:
        return [
            math.log(max(self.score, 1e-4)),
            min(self.disagreement, 3.0),
            min(self.outside_window, 3.0),
            1.0 if self.voiced_start else 0.0,
            abs(math.log(max(self.duration_ratio, 1e-2))),
        ]


class TimingJudge:
    """Calibrated "is this word's timing right?" probability, the role Jev plays for Better
    Lyrics' edits: high confidence is accepted, low confidence is flagged for a human, nothing
    is patched blindly. A logistic model over the evidence, fitted on the benchmark songs
    (scripts/fit_judge.py) with "right" meaning a start within 0.3 s of the hand-made timing."""

    # Fitted by scripts/fit_judge.py; see its output for the data behind them.
    WEIGHTS: ClassVar = [0.55, -2.4, -1.6, 0.6, -0.5]
    BIAS = 2.6
    UNSURE = 0.6  # below this probability a word is flagged for review

    def __init__(self, weights: list[float] | None = None, bias: float | None = None):
        self._weights = weights or self.WEIGHTS
        self._bias = self.BIAS if bias is None else bias

    def probability(self, evidence: WordEvidence) -> float:
        z = self._bias + sum(w * x for w, x in zip(self._weights, evidence.features(),
                                                   strict=True))
        return 1.0 / (1.0 + math.exp(-z))
