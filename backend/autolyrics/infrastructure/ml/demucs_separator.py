import gc
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.application.interfaces.audio import IVocalSeparator
from autolyrics.infrastructure.media.ffmpeg import Ffmpeg


class DemucsVocalSeparator(IVocalSeparator):
    """Vocal isolation with Demucs, so the aligner hears the voice and not the beat."""

    VOCALS_FILE = "vocals.wav"

    def __init__(self, ffmpeg: Ffmpeg, model_name: str = "htdemucs_ft"):
        self._ffmpeg = ffmpeg
        self._model_name = model_name

    def separate(self, audio: Path, workspace: Path) -> Path:
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
        with torch.no_grad():
            sources = apply_model(model, ((wav - mean) / std)[None], device=device, shifts=1,
                                  split=True, overlap=0.25, progress=False)[0]
        vocals = sources[model.sources.index("vocals")] * std + mean
        sf.write(vocals_path, vocals.cpu().numpy().T.astype(np.float32), rate, subtype="PCM_16")

        del model, sources, vocals, wav
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        mix_path.unlink(missing_ok=True)
        return vocals_path
