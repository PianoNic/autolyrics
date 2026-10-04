import asyncio
from collections.abc import AsyncIterator

from autolyrics.application.interfaces.jobs import IJobEventBroadcaster, IJobSubscription


class JobSubscription(IJobSubscription):
    """Registered the moment it is created, so nothing published after that is missed."""

    FINAL_STATUSES = ("done", "failed")

    def __init__(self, broadcaster: "InMemoryJobEventBroadcaster", job_id: str, keep_alive: float):
        self._broadcaster = broadcaster
        self._job_id = job_id
        self._keep_alive = keep_alive
        self.queue: asyncio.Queue = asyncio.Queue()

    async def __aiter__(self) -> AsyncIterator[dict | None]:
        """Payloads as they come, `None` as a keep-alive tick; ends on a final status."""
        while True:
            try:
                payload = await asyncio.wait_for(self.queue.get(), timeout=self._keep_alive)
            except TimeoutError:
                yield None
                continue
            yield payload
            if payload.get("type") == "status" and payload.get("status") in self.FINAL_STATUSES:
                return

    def close(self) -> None:
        self._broadcaster.remove(self._job_id, self)


class InMemoryJobEventBroadcaster(IJobEventBroadcaster):
    """Fans job payloads out to every open event stream for that job."""

    def __init__(self, keep_alive: float = 15.0):
        self._subscriptions: dict[str, list[JobSubscription]] = {}
        self._keep_alive = keep_alive

    def publish(self, job_id: str, payload: dict) -> None:
        for subscription in list(self._subscriptions.get(job_id, [])):
            subscription.queue.put_nowait(payload)

    def subscribe(self, job_id: str) -> JobSubscription:
        subscription = JobSubscription(self, job_id, self._keep_alive)
        self._subscriptions.setdefault(job_id, []).append(subscription)
        return subscription

    def remove(self, job_id: str, subscription: JobSubscription) -> None:
        subscriptions = self._subscriptions.get(job_id, [])
        if subscription in subscriptions:
            subscriptions.remove(subscription)
        if not subscriptions:
            self._subscriptions.pop(job_id, None)
