"""ffmpeg / ffprobe helpers."""

import shutil
import subprocess
from pathlib import Path


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(f"{tool} not found on PATH; install ffmpeg")
    return path


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [_require("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def to_wav(src: Path, dest: Path, sample_rate: int = 44100, mono: bool = False) -> Path:
    """Decode to PCM WAV. Demucs wants 44.1 kHz stereo, the aligner 16 kHz mono."""
    args = [_require("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-vn",
            "-ar", str(sample_rate), "-ac", "1" if mono else "2", "-c:a", "pcm_s16le", str(dest)]
    subprocess.run(args, check=True, capture_output=True)
    return dest
