import json

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from mediatorx import Mediator

from autolyrics.api.controller import controller
from autolyrics.api.dependencies import ApiDependencies
from autolyrics.application.interfaces.jobs import IJobEventBroadcaster
from autolyrics.application.queries.job_queries import (
    GetJobAudioQuery,
    GetJobFileQuery,
    GetJobQuery,
)

router = APIRouter(prefix="/api", tags=["Job media"])


class ServerSentEvents:
    """A job's history followed by its live progress, as a text/event-stream."""

    def __init__(self, mediator: Mediator, broadcaster: IJobEventBroadcaster, job_id: str):
        self._mediator = mediator
        self._broadcaster = broadcaster
        self._job_id = job_id

    async def stream(self):
        # Subscribe before reading the history, so nothing falls between the two.
        subscription = self._broadcaster.subscribe(self._job_id)
        try:
            job = await self._mediator.send(GetJobQuery(self._job_id))
            yield self._frame({"type": "status", "status": job.status.value, "error": job.error})
            for event in job.events:
                yield self._frame({"type": "event", "event": event.model_dump(mode="json")})
            if not job.status.active:
                return
            async for payload in subscription:
                yield ": keep-alive\n\n" if payload is None else self._frame(payload)
        finally:
            subscription.close()

    @staticmethod
    def _frame(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@controller(router)
class JobMediaController:
    mediator: Mediator = Depends(ApiDependencies.mediator)
    broadcaster: IJobEventBroadcaster = Depends(ApiDependencies.broadcaster)

    @router.get("/jobs/{job_id}/events")
    async def events(self, job_id: str) -> StreamingResponse:
        await self.mediator.send(GetJobQuery(job_id))  # 404 before the stream starts
        stream = ServerSentEvents(self.mediator, self.broadcaster, job_id).stream()
        return StreamingResponse(stream, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.get("/jobs/{job_id}/audio")
    async def audio(self, job_id: str) -> FileResponse:
        file = await self.mediator.send(GetJobAudioQuery(job_id))
        return FileResponse(file.path, media_type=file.media_type)

    @router.get("/jobs/{job_id}/files/{name}")
    async def file(self, job_id: str, name: str) -> FileResponse:
        file = await self.mediator.send(GetJobFileQuery(job_id, name))
        return FileResponse(file.path, media_type=file.media_type, filename=file.download_name)
