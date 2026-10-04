from dataclasses import dataclass

from mediatorx import ICommand, ICommandHandler

from autolyrics.application.dtos.job_dtos import JobSummary
from autolyrics.application.interfaces.jobs import IJobQueue, IJobRepository
from autolyrics.domain.errors import InvalidInputError
from autolyrics.domain.job import JobOptions


@dataclass
class CreateJobCommand(ICommand[JobSummary]):
    options: JobOptions
    # The CLI runs the job itself instead of handing it to the background queue.
    enqueue: bool = True
    job_id: str | None = None


class CreateJobHandler(ICommandHandler[CreateJobCommand, JobSummary]):
    def __init__(self, repository: IJobRepository, queue: IJobQueue):
        self._repository = repository
        self._queue = queue

    async def handle(self, command: CreateJobCommand) -> JobSummary:
        if not command.options.url.strip():
            raise InvalidInputError("a song link is required")
        job = self._repository.create(command.options, command.job_id)
        if command.enqueue:
            self._queue.enqueue(job.id)
        return JobSummary.of(job)
