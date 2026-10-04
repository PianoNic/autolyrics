from mediatorx import IPublisher

from autolyrics.application.jobs.notifications import JobEventRaised
from autolyrics.domain.errors import StageFailedError
from autolyrics.domain.job import JobEvent, Stage, StageStatus


class StageReporter:
    """Publishes a job's progress as notifications; recording and broadcasting are handlers."""

    def __init__(self, publisher: IPublisher, job_id: str):
        self._publisher = publisher
        self._job_id = job_id

    async def running(self, stage: Stage, message: str, **data) -> None:
        await self._emit(stage, StageStatus.RUNNING, message, data)

    async def done(self, stage: Stage, message: str, **data) -> None:
        await self._emit(stage, StageStatus.DONE, message, data)

    async def skipped(self, stage: Stage, message: str, **data) -> None:
        await self._emit(stage, StageStatus.SKIPPED, message, data)

    async def failed(self, stage: Stage, message: str, **data) -> None:
        await self._emit(stage, StageStatus.FAILED, message, data)

    async def fail(self, stage: Stage, message: str) -> StageFailedError:
        """Report the failure and hand back the error for the caller to raise."""
        await self.failed(stage, message)
        return StageFailedError(stage.value, message)

    async def _emit(self, stage: Stage, status: StageStatus, message: str, data: dict) -> None:
        event = JobEvent(stage=stage, status=status, message=message, data=data)
        await self._publisher.publish(JobEventRaised(self._job_id, event))
