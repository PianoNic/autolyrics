from dataclasses import dataclass

from mediatorx import INotification, INotificationHandler

from autolyrics.application.interfaces.jobs import IJobEventBroadcaster, IJobRepository
from autolyrics.domain.job import JobEvent, JobStatus, Stage


@dataclass
class JobEventRaised(INotification):
    job_id: str
    event: JobEvent


@dataclass
class JobProgressed(INotification):
    """How far a long step has got. Live only: it is broadcast, never stored on the job."""

    job_id: str
    stage: Stage
    label: str
    fraction: float | None
    detail: str = ""


@dataclass
class JobStatusChanged(INotification):
    job_id: str
    status: JobStatus
    error: str | None = None


class RecordJobEventHandler(INotificationHandler[JobEventRaised]):
    """Keeps the event history on the job, so a page opened later can replay it."""

    def __init__(self, repository: IJobRepository):
        self._repository = repository

    async def handle(self, notification: JobEventRaised) -> None:
        job = self._repository.get(notification.job_id)
        job.events.append(notification.event)
        self._repository.save(job)


class BroadcastJobEventHandler(INotificationHandler[JobEventRaised]):
    def __init__(self, broadcaster: IJobEventBroadcaster):
        self._broadcaster = broadcaster

    async def handle(self, notification: JobEventRaised) -> None:
        self._broadcaster.publish(notification.job_id, {
            "type": "event", "event": notification.event.model_dump(mode="json")})


class BroadcastJobStatusHandler(INotificationHandler[JobStatusChanged]):
    def __init__(self, broadcaster: IJobEventBroadcaster):
        self._broadcaster = broadcaster

    async def handle(self, notification: JobStatusChanged) -> None:
        self._broadcaster.publish(notification.job_id, {
            "type": "status", "status": notification.status.value, "error": notification.error})


class BroadcastJobProgressHandler(INotificationHandler[JobProgressed]):
    def __init__(self, broadcaster: IJobEventBroadcaster):
        self._broadcaster = broadcaster

    async def handle(self, notification: JobProgressed) -> None:
        fraction = notification.fraction
        self._broadcaster.publish(notification.job_id, {
            "type": "progress", "stage": notification.stage.value, "label": notification.label,
            "fraction": None if fraction is None else round(fraction, 4),
            "detail": notification.detail})
