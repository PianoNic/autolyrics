import gc
import random
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.application.interfaces.audio import IVocalSeparator, VocalStems
from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
from autolyrics.infrastructure.clients.media.ffmpeg import Ffmpeg


class DemucsVocalSeparator(IVocalSeparator):
    """Vocal isolation with Demucs, so the aligner hears the voice and not the beat."""

    VOCALS_FILE = "vocals.wav"
    SEED = 1234

    def __init__(self, ffmpeg: Ffmpeg, model_name: str = "htdemucs_ft"):
        self._ffmpeg = ffmpeg
        self._model_name = model_name

    def stems(self, audio: Path, workspace: Path,
              progress: IProgress = NO_PROGRESS) -> VocalStems:
        vocals = self._separate(audio, workspace, progress)
        return VocalStems(lead=vocals, vocals=vocals)

    def _separate(self, audio: Path, workspace: Path, progress: IProgress) -> Path:
        vocals_path = workspace / self.VOCALS_FILE
        if vocals_path.exists():
            return vocals_path

        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model

        mix_path = self._ffmpeg.to_wav(audio, workspace / "mix.wav", sample_rate=44100)
        data, rate = sf.read(mix_path, dtype="float32", always_2d=True)
        wav = torch.from_numpy(data.T.copy())  # (channels, samples)
        model = get_model(self._model_name)
        model.eval()
        if rate != model.samplerate:
            raise RuntimeError(f"expected {model.samplerate} Hz audio, got {rate}")

        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # Demucs shifts the input by a random amount; a fixed seed makes the same song always give
        # the same vocals, and so the same timing.
        random.seed(self.SEED)
        torch.manual_seed(self.SEED)
        with torch.no_grad():
            sources = apply_model(model, ((wav - mean) / std)[None], device=device, shifts=1,
                                  split=True, overlap=0.25, progress=False,
                                  callback=self._reporter(progress, wav.shape[-1], rate))[0]
        vocals = sources[model.sources.index("vocals")] * std + mean
        sf.write(vocals_path, vocals.cpu().numpy().T.astype(np.float32), rate, subtype="PCM_16")

        del model, sources, vocals, wav
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        mix_path.unlink(missing_ok=True)
        return vocals_path

    @staticmethod
    def _reporter(progress: IProgress, length: int, rate: int):
        """Demucs calls back as each segment of each model in the bag finishes."""
        def callback(info: dict) -> None:
            if info.get("state") != "end":
                return
            models = max(1, info.get("models", 1))
            done = min(1.0, (info.get("segment_offset", 0) + 8 * rate) / max(1, length))
            model = info.get("model_idx_in_bag", 0)
            progress.update((model + done) / models, f"model {model + 1} of {models}")
        return callback
