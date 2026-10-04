from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
from autolyrics.domain.lyrics import Line, Lyrics


class IAudioTools(ABC):
    @abstractmethod
    def duration(self, path: Path) -> float: ...


@dataclass(frozen=True)
class VocalStems:
    """What separation gives the aligners: the lead vocal (dry, for timing the main lines), the
    backing vocals (for the background lines) and all vocals together (for transcription)."""

    lead: Path
    vocals: Path
    backing: Path | None = None


class IVocalSeparator(ABC):
    """Isolates the vocals of a song. Blocking; call it off the event loop."""

    @abstractmethod
    def stems(self, audio: Path, workspace: Path,
              progress: IProgress = NO_PROGRESS) -> VocalStems:
        """Separate the song, reusing stems already in `workspace`."""

    def separate(self, audio: Path, workspace: Path,
                 progress: IProgress = NO_PROGRESS) -> Path:
        """The lead vocal: what the words are timed against."""
        return self.stems(audio, workspace, progress).lead


class ILyricsAligner(ABC):
    """Times lyrics text against isolated vocals. Blocking; call it off the event loop."""

    @abstractmethod
    def align(self, lyrics: Lyrics, stems: VocalStems, workspace: Path,
              progress: IProgress = NO_PROGRESS) -> dict:
        """Give every word a time, in place. Returns statistics for the report."""

    @abstractmethod
    def measure_offset(self, lyrics: Lyrics, stems: VocalStems, workspace: Path) -> dict:
        """How far already-timed lyrics sit from this audio: {offset, spread, words}."""

    @abstractmethod
    def realign_line(self, line: Line, stems: VocalStems, workspace: Path, language: str,
                     start: float, end: float) -> bool:
        """Re-time one line inside [start, end], in place."""

    @abstractmethod
    def release(self) -> None:
        """Free the model (GPU memory) until it is needed again."""


class ITranscriber(ABC):
    """Hears lyrics in isolated vocals: the fallback when no lyrics source knows the song.
    Blocking; call it off the event loop."""

    @abstractmethod
    def transcribe(self, vocals: Path, workspace: Path, language: str | None = None,
                   progress: IProgress = NO_PROGRESS) -> Lyrics:
        """Lines with their approximate begin/end times; words are untimed (the aligner times
        them) and `metadata.language` is the detected language."""

    @abstractmethod
    def release(self) -> None:
        """Free the model (GPU memory) until it is needed again."""
