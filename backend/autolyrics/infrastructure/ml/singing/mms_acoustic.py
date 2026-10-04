import numpy as np

from autolyrics.infrastructure.ml.mms_model import MmsModel
from autolyrics.infrastructure.ml.singing.acoustic import Emissions, IAcousticModel
from autolyrics.infrastructure.ml.text_normalizer import AlignmentTextNormalizer


class MmsCharacterModel(IAcousticModel):
    """torchaudio's MMS_FA (speech, 1,100+ languages) as an acoustic model: letters of the
    romanised word, with its `*` token between lines for sound the lyrics do not cover. The
    fallback for languages the singing model does not know (Japanese)."""

    name = "mms-characters"
    sample_rate = MmsModel.SAMPLE_RATE

    def __init__(self, model: MmsModel, normalizer: AlignmentTextNormalizer):
        self._model = model
        self._normalizer = normalizer
        self._dictionary = model.dictionary
        self.line_gap = self._dictionary["*"]

    def supports(self, language: str) -> bool:
        return True

    def emissions(self, samples: np.ndarray) -> Emissions:
        logp = self._model.emissions(samples).float().numpy()
        return Emissions(logp=logp, frame_seconds=MmsModel.FRAME_SECONDS, blank=0)

    def tokens(self, words: list[str], language: str) -> list[list[int]]:
        return [[self._dictionary[c] for c in self._normalizer.normalize(w, language)]
                for w in words]

    def close(self) -> None:
        self._model.close()
