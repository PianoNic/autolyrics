from abc import ABC, abstractmethod
from pathlib import Path

from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
from autolyrics.domain.track import Track


class IMediaResolver(ABC):
    """Turns a song link into a track and downloads its audio."""

    @abstractmethod
    async def resolve(self, url: str) -> Track: ...

    @abstractmethod
    async def download_audio(self, track: Track, directory: Path,
                             progress: IProgress = NO_PROGRESS) -> Path:
        """Download into `directory` and return the file; reuse an existing download."""
