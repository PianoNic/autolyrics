from dataclasses import dataclass, field
from pathlib import Path

from autolyrics.application.pipeline.reporter import StageReporter
from autolyrics.domain.candidate import LyricsCandidate
from autolyrics.domain.job import Job
from autolyrics.domain.lyrics import Lyrics
from autolyrics.domain.track import Track


@dataclass
class PipelineContext:
    """What one run of the pipeline knows so far; each stage reads it and adds to it."""

    job: Job
    workspace: Path
    reporter: StageReporter
    report: dict = field(default_factory=dict)
    track: Track | None = None
    audio: Path | None = None
    duration: float | None = None
    # Usable candidates, best first.
    candidates: list[LyricsCandidate] = field(default_factory=list)
    lyrics: Lyrics | None = None

    @property
    def chosen(self) -> LyricsCandidate | None:
        return self.candidates[0] if self.candidates else None
