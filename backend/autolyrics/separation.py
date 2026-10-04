"""Vocal isolation with Demucs, so the aligner hears the voice and not the beat."""

import gc
import logging
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.audio import to_wav

log = logging.getLogger(__name__)

# The fine-tuned bag of models: about 4x slower than htdemucs but noticeably cleaner vocals.
MODEL_NAME = "htdemucs_ft"


def device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def separate_vocals(audio_path: Path, out_dir: Path, model_name: str = MODEL_NAME) -> Path:
    """Write `vocals.wav` (44.1 kHz stereo) next to the job's audio and return its path.

    Cached: an existing `vocals.wav` is reused.
    """
    vocals_path = out_dir / "vocals.wav"
    if vocals_path.exists():
        return vocals_path

    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    mix_path = to_wav(audio_path, out_dir / "mix.wav", sample_rate=44100)
    data, rate = sf.read(mix_path, dtype="float32", always_2d=True)
    wav = torch.from_numpy(data.T.copy())  # (channels, samples)

    model = get_model(model_name)
    model.eval()
    if rate != model.samplerate:
        raise RuntimeError(f"expected {model.samplerate} Hz audio, got {rate}")

    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        sources = apply_model(model, ((wav - mean) / std)[None], device=device(), shifts=1,
                              split=True, overlap=0.25, progress=False)[0]
    vocals = sources[model.sources.index("vocals")] * std + mean

    sf.write(vocals_path, vocals.cpu().numpy().T.astype(np.float32), rate, subtype="PCM_16")
    del model, sources, vocals, wav
    _free_gpu()
    mix_path.unlink(missing_ok=True)
    return vocals_path


def _free_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
