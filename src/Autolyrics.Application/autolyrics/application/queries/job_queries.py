from dataclasses import dataclass
from typing import ClassVar

from mediatorx import IQuery, IQueryHandler

from autolyrics.application.dtos.job_dtos import JobDetail, JobFile, JobSummary
from autolyrics.application.interfaces.jobs import IJobRepository
from autolyrics.domain.errors import NotFoundError
from autolyrics.domain.lyrics import Lyrics


@dataclass
class ListJobsQuery(IQuery[list[JobSummary]]):
    pass


class ListJobsHandler(IQueryHandler[ListJobsQuery, list[JobSummary]]):
    def __init__(self, repository: IJobRepository):
        self._repository = repository

    async def handle(self, query: ListJobsQuery) -> list[JobSummary]:
        return [JobSummary.of(job) for job in self._repository.list()]


@dataclass
class GetJobQuery(IQuery[JobDetail]):
    job_id: str


class GetJobHandler(IQueryHandler[GetJobQuery, JobDetail]):
    def __init__(self, repository: IJobRepository):
        self._repository = repository

    async def handle(self, query: GetJobQuery) -> JobDetail:
        job = self._repository.get(query.job_id)
        return JobDetail(**JobSummary.of(job).model_dump(), events=job.events,
                         report=self._repository.read_report(job.id))


@dataclass
class GetLyricsQuery(IQuery[Lyrics]):
    job_id: str


class GetLyricsHandler(IQueryHandler[GetLyricsQuery, Lyrics]):
    def __init__(self, repository: IJobRepository):
        self._repository = repository

    async def handle(self, query: GetLyricsQuery) -> Lyrics:
        self._repository.get(query.job_id)
        lyrics = self._repository.load_lyrics(query.job_id)
        if lyrics is None:
            raise NotFoundError("this job has no lyrics yet")
        return lyrics


@dataclass
class GetJobFileQuery(IQuery[JobFile]):
    job_id: str
    name: str


class GetJobFileHandler(IQueryHandler[GetJobFileQuery, JobFile]):
    MEDIA_TYPES: ClassVar = {
        "lyrics.ttml": "application/ttml+xml",
        "lyrics.lrc": "text/plain",
        "lyrics.word.lrc": "text/plain",
        "lyrics.srt": "text/plain",
        "lyrics.qrc": "text/plain",
        "lyrics.json": "application/json",
    }

    def __init__(self, repository: IJobRepository):
        self._repository = repository

    async def handle(self, query: GetJobFileQuery) -> JobFile:
        job = self._repository.get(query.job_id)
        if query.name not in self.MEDIA_TYPES:
            raise NotFoundError(f"unknown file {query.name}")
        path = self._repository.output_file(job.id, query.name)
        if path is None:
            raise NotFoundError(f"{query.name} has not been written")
        stem = " - ".join(x for x in (", ".join(job.artists), job.title) if x) or "lyrics"
        return JobFile(path=path, media_type=self.MEDIA_TYPES[query.name],
                       download_name=f"{stem}{query.name.removeprefix('lyrics')}")


@dataclass
class GetJobAudioQuery(IQuery[JobFile]):
    job_id: str


class GetJobAudioHandler(IQueryHandler[GetJobAudioQuery, JobFile]):
    def __init__(self, repository: IJobRepository):
        self._repository = repository

    async def handle(self, query: GetJobAudioQuery) -> JobFile:
        job = self._repository.get(query.job_id)
        path = self._repository.audio_file(job.id)
        if path is None:
            raise NotFoundError("this job has no audio yet")
        media = {".m4a": "audio/mp4", ".webm": "audio/webm", ".mp3": "audio/mpeg"}
        return JobFile(path=path, media_type=media.get(path.suffix, "application/octet-stream"),
                       download_name=path.name)
