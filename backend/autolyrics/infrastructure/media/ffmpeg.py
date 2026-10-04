import shutil
import subprocess
from pathlib import Path

from autolyrics.application.interfaces.audio import IAudioTools


class Ffmpeg(IAudioTools):
    """ffprobe for lengths, ffmpeg for decoding to PCM WAV."""

    def _tool(self, name: str) -> str:
        path = shutil.which(name)
        if not path:
            raise RuntimeError(f"{name} not found on PATH; install ffmpeg")
        return path

    def duration(self, path: Path) -> float:
        out = subprocess.run(
            [self._tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True)
        return float(out.stdout.strip())

    def to_wav(self, src: Path, dest: Path, sample_rate: int = 44100, mono: bool = False) -> Path:
        """Demucs wants 44.1 kHz stereo, the aligner 16 kHz mono."""
        subprocess.run(
            [self._tool("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-vn",
             "-ar", str(sample_rate), "-ac", "1" if mono else "2", "-c:a", "pcm_s16le", str(dest)],
            check=True, capture_output=True)
        return dest
