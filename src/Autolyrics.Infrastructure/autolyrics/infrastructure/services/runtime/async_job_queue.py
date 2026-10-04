import asyncio
import logging

from mediatorx import ISender

from autolyrics.application.commands.run_job import RunJobCommand
from autolyrics.application.interfaces.jobs import IJobQueue

log = logging.getLogger(__name__)


class AsyncJobQueue(IJobQueue):
    """A single background worker running queued jobs in order: they share one GPU."""

    def __init__(self):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._sender: ISender | None = None

    def enqueue(self, job_id: str) -> None:
        self._queue.put_nowait(job_id)

    def start(self, sender: ISender) -> None:
        self._sender = sender
        if self._worker is None:
            self._worker = asyncio.create_task(self._work(), name="autolyrics-job-worker")

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def _work(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._sender.send(RunJobCommand(job_id))
            except Exception:  # the worker must survive any one job
                log.exception("job %s could not run", job_id)
            finally:
                self._queue.task_done()
