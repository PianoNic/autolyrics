from pathlib import Path

from pydantic import BaseModel

from autolyrics.domain.job import Job, JobEvent, JobStatus


class JobSummary(BaseModel):
    id: str
    status: JobStatus
    created: float
    error: str | None
    url: str
    title: str | None
    artists: list[str]
    cover_url: str | None
    sync: str | None
    flagged: int | None
    words: int | None

    @classmethod
    def of(cls, job: Job) -> "JobSummary":
        return cls(id=job.id, status=job.status, created=job.created, error=job.error,
                   url=job.options.url, title=job.title, artists=job.artists,
                   cover_url=job.cover_url, sync=job.sync, flagged=job.flagged_words,
                   words=job.total_words)


class JobDetail(JobSummary):
    events: list[JobEvent]
    report: dict


class SaveResult(BaseModel):
    validation: dict
    sync: str
    files: dict[str, str]


class RealignResult(SaveResult):
    aligned: bool
    line: dict


class JobFile(BaseModel):
    path: Path
    media_type: str
    download_name: str
