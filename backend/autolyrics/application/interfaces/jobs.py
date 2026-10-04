from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path

from autolyrics.domain.candidate import LyricsCandidate
from autolyrics.domain.job import Job, JobOptions
from autolyrics.domain.lyrics import Lyrics


class IJobRepository(ABC):
    """Jobs and everything they produce: metadata, report, candidates, audio, output."""

    @abstractmethod
    def create(self, options: JobOptions, job_id: str | None = None) -> Job: ...

    @abstractmethod
    def get(self, job_id: str) -> Job:
        """Raises JobNotFoundError."""

    @abstractmethod
    def list(self) -> list[Job]:
        """Newest first."""

    @abstractmethod
    def save(self, job: Job) -> None: ...

    @abstractmethod
    def delete(self, job_id: str) -> None: ...

    @abstractmethod
    def workspace(self, job_id: str) -> Path:
        """Directory for downloads and intermediate files (vocals, model inputs)."""

    @abstractmethod
    def read_report(self, job_id: str) -> dict: ...

    @abstractmethod
    def write_report(self, job_id: str, report: dict) -> None: ...

    @abstractmethod
    def save_candidate(self, job_id: str, index: int, candidate: LyricsCandidate) -> None: ...

    @abstractmethod
    def save_artifact(self, job_id: str, name: str, content: str) -> None:
        """Small text files worth keeping, such as the LLM prompt and answer."""

    @abstractmethod
    def load_lyrics(self, job_id: str) -> Lyrics | None: ...

    @abstractmethod
    def save_lyrics(self, job_id: str, lyrics: Lyrics) -> None: ...

    @abstractmethod
    def output_directory(self, job_id: str) -> Path: ...

    @abstractmethod
    def output_file(self, job_id: str, name: str) -> Path | None: ...

    @abstractmethod
    def audio_file(self, job_id: str) -> Path | None: ...


class IJobSubscription(ABC):
    """Payloads published for one job from the moment of subscribing. Iterating yields each
    payload, or None as a keep-alive tick, and ends when the job reaches a final status."""

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[dict | None]: ...

    @abstractmethod
    def close(self) -> None: ...


class IJobEventBroadcaster(ABC):
    """Live fan-out of job progress to whoever is watching (the browser's event stream)."""

    @abstractmethod
    def publish(self, job_id: str, payload: dict) -> None: ...

    @abstractmethod
    def subscribe(self, job_id: str) -> IJobSubscription: ...


class IJobQueue(ABC):
    """Runs queued jobs one at a time in the background (they share the GPU)."""

    @abstractmethod
    def enqueue(self, job_id: str) -> None: ...
