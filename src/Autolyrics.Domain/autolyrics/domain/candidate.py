from dataclasses import dataclass, field
from typing import ClassVar

from autolyrics.domain.lyrics import Lyrics, SyncType


@dataclass
class LyricsQuery:
    track: str
    artist: str
    album: str | None = None
    duration: float | None = None
    video_id: str | None = None


@dataclass
class LyricsCandidate:
    """One lyrics document a source returned, before and after validation."""

    source: str
    label: str
    format: str  # "ttml" | "lrc" | "qrc" | "plain"
    content: str
    declared_sync: SyncType
    track: str | None = None
    artist: str | None = None
    duration: float | None = None
    source_id: str | None = None
    lyrics: Lyrics | None = None
    rejected: str | None = None
    # The text is right but the timing belongs to another cut of the song (album vs. video).
    text_only: bool = False
    notes: list[str] = field(default_factory=list)

    FILE_EXTENSIONS: ClassVar = {"ttml": "ttml", "lrc": "lrc", "qrc": "qrc", "plain": "txt"}

    @property
    def sync(self) -> SyncType:
        if self.text_only:
            return SyncType.UNSYNCED
        return self.lyrics.sync_type if self.lyrics else self.declared_sync

    @property
    def usable(self) -> bool:
        return self.rejected is None and self.lyrics is not None

    @property
    def file_extension(self) -> str:
        return self.FILE_EXTENSIONS[self.format]

    def summary(self) -> dict:
        return {
            "source": self.source, "label": self.label, "format": self.format,
            "sync": self.sync.value, "track": self.track, "artist": self.artist,
            "duration": self.duration, "id": self.source_id, "rejected": self.rejected,
            "text_only": self.text_only,
            "lines": len(self.lyrics.lines) if self.lyrics else None, "notes": self.notes,
        }
