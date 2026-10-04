from abc import ABC, abstractmethod
from pathlib import Path

from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery
from autolyrics.domain.lyrics import Lyrics


class ILyricsProvider(ABC):
    """A lyrics source. Implementations swallow their own failures and return no results."""

    name: str

    @abstractmethod
    async def search(self, query: LyricsQuery) -> list[LyricsCandidate]: ...


class ILyricsFormats(ABC):
    """Reads lyrics documents (TTML, LRC, QRC, plain text)."""

    @abstractmethod
    def parse(self, format: str, content: str, duration: float | None = None) -> Lyrics: ...

    @abstractmethod
    def candidate_from_file(self, path: Path) -> LyricsCandidate:
        """A user-supplied lyrics file as a candidate, its format detected."""


class ILyricsExporter(ABC):
    """Writes lyrics in every output format."""

    @abstractmethod
    def export(self, lyrics: Lyrics, directory: Path) -> dict[str, Path]: ...

    @abstractmethod
    def render_ttml(self, lyrics: Lyrics) -> str: ...
