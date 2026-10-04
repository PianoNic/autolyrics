from fastapi import APIRouter, Body, Depends, Response
from mediatorx import Mediator

from autolyrics.application.jobs.create_job import CreateJobCommand
from autolyrics.application.jobs.dtos import JobDetail, JobSummary, RealignResult, SaveResult
from autolyrics.application.jobs.edit_commands import (
    DeleteJobCommand,
    ImportTtmlCommand,
    RealignLineCommand,
    SaveLyricsCommand,
)
from autolyrics.application.jobs.queries import GetJobQuery, GetLyricsQuery, ListJobsQuery
from autolyrics.domain.job import JobOptions
from autolyrics.domain.lyrics import Lyrics
from autolyrics.presentation.api.controller import controller
from autolyrics.presentation.api.dependencies import ApiDependencies
from autolyrics.presentation.api.schemas import CreateJobRequest, RealignLineRequest

router = APIRouter(prefix="/api", tags=["Jobs"])


@controller(router)
class JobsController:
    mediator: Mediator = Depends(ApiDependencies.mediator)

    @router.post("/jobs", status_code=201)
    async def create_job(self, body: CreateJobRequest) -> JobSummary:
        options = JobOptions(**body.model_dump())
        return await self.mediator.send(CreateJobCommand(options))

    @router.get("/jobs")
    async def list_jobs(self) -> list[JobSummary]:
        return await self.mediator.send(ListJobsQuery())

    @router.get("/jobs/{job_id}")
    async def get_job(self, job_id: str) -> JobDetail:
        return await self.mediator.send(GetJobQuery(job_id))

    @router.delete("/jobs/{job_id}", status_code=204)
    async def delete_job(self, job_id: str) -> Response:
        await self.mediator.send(DeleteJobCommand(job_id))
        return Response(status_code=204)

    @router.get("/jobs/{job_id}/lyrics")
    async def lyrics(self, job_id: str) -> Lyrics:
        return await self.mediator.send(GetLyricsQuery(job_id))

    @router.put("/jobs/{job_id}/lyrics")
    async def save_lyrics(self, job_id: str, lyrics: Lyrics) -> SaveResult:
        return await self.mediator.send(SaveLyricsCommand(job_id, lyrics))

    @router.put("/jobs/{job_id}/ttml")
    async def import_ttml(self, job_id: str,
                          ttml: str = Body(..., media_type="application/ttml+xml")) -> SaveResult:
        """Save from the Composer editor: its TTML replaces the job's lyrics."""
        return await self.mediator.send(ImportTtmlCommand(job_id, ttml))

    @router.post("/jobs/{job_id}/lines/{index}/realign")
    async def realign_line(self, job_id: str, index: int,
                           body: RealignLineRequest) -> RealignResult:
        return await self.mediator.send(RealignLineCommand(job_id, index, body.text, body.start,
                                                           body.end))
