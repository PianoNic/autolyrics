import asyncio
import threading
import time

from mediatorx import IPublisher

from autolyrics.application.interfaces.progress import IProgress
from autolyrics.application.jobs.notifications import JobEventRaised, JobProgressed
from autolyrics.domain.errors import StageFailedError
from autolyrics.domain.job import JobEvent, Stage, StageStatus


class StageProgress(IProgress):
    """Progress of one step of a stage, published as JobProgressed. Worker threads call it, so
    it hands each update to the event loop; it publishes at most a few times a second."""

    INTERVAL = 0.25  # seconds between updates

    def __init__(self, publisher: IPublisher, job_id: str, stage: Stage, label: str,
                 loop: asyncio.AbstractEventLoop):
        self._publisher = publisher
        self._job_id = job_id
        self._stage = stage
        self._label = label
        self._loop = loop
        self._lock = threading.Lock()
        self._last = 0.0

    def update(self, fraction: float | None, detail: str = "") -> None:
        if fraction is not None:
            fraction = min(1.0, max(0.0, fraction))
        now = time.monotonic()
        with self._lock:
            if now - self._last < self.INTERVAL and fraction != 1.0:
                return
            self._last = now
        notification = JobProgressed(self._job_id, self._stage, self._label, fraction, detail)
        try:
            asyncio.run_coroutine_threadsafe(self._publisher.publish(notification), self._loop)
        except RuntimeError:
            pass  # the loop has closed: the job is over and nobody is listening


class StageReporter:
    """Publishes a job's progress as notifications; recording and broadcasting are handlers."""

    def __init__(self, publisher: IPublisher, job_id: str):
        self._publisher = publisher
        self._job_id = job_id

    def progress(self, stage: Stage, label: str) -> StageProgress:
        """A progress bar for one step; create it on the event loop, update it from anywhere.
        It appears with its first update, so steps can be prepared before they start."""
        return StageProgress(self._publisher, self._job_id, stage, label,
                             asyncio.get_running_loop())

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
