import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from autolyrics.application.interfaces.audio import IVocalSeparator, VocalStems
from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
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
    # Vocal separation, started as soon as the audio is in so it runs while the lyrics are
    # searched and cleaned up; every stage that needs the vocals awaits the same task.
    separation: asyncio.Task | None = None

    def start_separation(self, separator: IVocalSeparator,
                         progress: IProgress = NO_PROGRESS) -> None:
        if self.separation is None and self.audio is not None:
            self.separation = asyncio.create_task(
                asyncio.to_thread(separator.stems, self.audio, self.workspace, progress))

    async def stems(self, separator: IVocalSeparator,
                    progress: IProgress = NO_PROGRESS) -> VocalStems:
        self.start_separation(separator, progress)
        return await self.separation

    @property
    def chosen(self) -> LyricsCandidate | None:
        return self.candidates[0] if self.candidates else None
