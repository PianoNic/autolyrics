import time
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

    @property
    def active(self) -> bool:
        return self in (JobStatus.QUEUED, JobStatus.RUNNING)


class Stage(StrEnum):
    RESOLVE = "resolve"
    AUDIO = "audio"
    LYRICS = "lyrics"
    POLISH = "polish"
    ALIGN = "align"
    EXPORT = "export"


class StageStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class JobEvent(BaseModel):
    stage: Stage
    status: StageStatus
    message: str = ""
    data: dict = Field(default_factory=dict)
    at: float = Field(default_factory=time.time)


class JobOptions(BaseModel):
    url: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    # Use this lyrics file instead of searching (the user's own TTML, LRC or text).
    lyrics_file: str | None = None
    # Lyrics pasted by the user (e.g. copied from a streaming app): used as they are, then timed.
    lyrics_text: str | None = None
    skip_llm: bool = False
    # Ignore the lyrics sources and transcribe the vocals (normally only the fallback).
    transcribe: bool = False


class Job(BaseModel):
    id: str
    options: JobOptions
    status: JobStatus = JobStatus.QUEUED
    created: float = Field(default_factory=time.time)
    error: str | None = None
    events: list[JobEvent] = Field(default_factory=list)
    # Filled as the pipeline learns about the song, so job lists need no report.
    title: str | None = None
    artists: list[str] = Field(default_factory=list)
    cover_url: str | None = None
    sync: str | None = None
    flagged_words: int | None = None
    total_words: int | None = None

    def start(self) -> None:
        self.status, self.error = JobStatus.RUNNING, None

    def finish(self) -> None:
        self.status = JobStatus.DONE

    def fail(self, error: str) -> None:
        self.status, self.error = JobStatus.FAILED, error
