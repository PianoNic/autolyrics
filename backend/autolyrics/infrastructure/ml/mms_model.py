import itertools
import logging
import math
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Span:
    begin: float
    end: float
    score: float


class MmsModel:
    """torchaudio's MMS_FA: wav2vec2 trained on 1,100+ languages, used for CTC forced alignment.
    The `*` star token soaks up audio the text does not cover (ad-libs, intros)."""

    SAMPLE_RATE = 16000
    FRAME_SECONDS = 320 / SAMPLE_RATE  # wav2vec2 downsamples 16 kHz audio by 320
    CHUNK_SECONDS = 30.0
    CONTEXT_SECONDS = 1.0

    def __init__(self, device: str | None = None):
        import torch
        import torchaudio

        self._torch = torch
        self._functional = torchaudio.functional
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        bundle = torchaudio.pipelines.MMS_FA
        self._model = bundle.get_model(with_star=True).to(self.device).eval()
        self._dictionary = bundle.get_dict(star="*")
        self.alphabet = {c for c in self._dictionary if c not in ("-", "*")}

    def close(self) -> None:
        del self._model
        if self.device == "cuda":
            self._torch.cuda.empty_cache()

    @classmethod
    def frame(cls, seconds: float) -> int:
        return max(0, int(seconds / cls.FRAME_SECONDS))

    @classmethod
    def frame_ceil(cls, seconds: float) -> int:
        return math.ceil(seconds / cls.FRAME_SECONDS)

    def emissions(self, waveform: np.ndarray):
        """Log-probabilities per 20 ms frame for the whole recording, computed in chunks."""
        torch = self._torch
        total = len(waveform)
        chunk = int(self.CHUNK_SECONDS * self.SAMPLE_RATE)
        context = int(self.CONTEXT_SECONDS * self.SAMPLE_RATE)
        frames = []
        with torch.inference_mode():
            for start in range(0, total, chunk):
                left = max(0, start - context)
                right = min(total, start + chunk + context)
                segment = torch.from_numpy(waveform[left:right]).float()[None].to(self.device)
                # Already log-probabilities over the alphabet; the star column is a constant 0.
                emission, _ = self._model(segment)
                skip = round((start - left) / 320)
                keep = round((min(total, start + chunk) - start) / 320)
                frames.append(emission[0][skip: skip + keep].cpu())
        return torch.cat(frames)

    def align(self, emission, words: list[str], offset_frame: int) -> list[Span] | None:
        """Align normalised words inside an emission slice. None when they cannot fit."""
        torch = self._torch
        transcript = ["*", *words, "*"]
        tokens = [self._dictionary[c] for w in transcript for c in w]
        # CTC needs a frame per token plus one blank between repeated letters.
        repeats = sum(1 for a, b in itertools.pairwise(tokens) if a == b)
        if emission.shape[0] < len(tokens) + repeats:
            return None
        targets = torch.tensor([tokens], dtype=torch.int32, device=self.device)
        try:
            alignment, scores = self._functional.forced_align(
                emission[None].to(self.device), targets, blank=0)
        except RuntimeError as error:
            log.warning("forced_align failed: %s", error)
            return None
        spans = self._functional.merge_tokens(alignment[0].cpu(), scores[0].exp().cpu())
        out: list[Span] = []
        i = 0
        for k, word in enumerate(transcript):
            word_spans = spans[i: i + len(word)]
            i += len(word)
            if k == 0 or k == len(transcript) - 1:
                continue
            length = sum(s.end - s.start for s in word_spans)
            score = sum(s.score * (s.end - s.start) for s in word_spans) / max(length, 1)
            out.append(Span((word_spans[0].start + offset_frame) * self.FRAME_SECONDS,
                            (word_spans[-1].end + offset_frame) * self.FRAME_SECONDS,
                            float(score)))
        return out
