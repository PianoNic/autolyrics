import logging
from dataclasses import dataclass

from mediatorx import ICommand, ICommandHandler, IMediator

from autolyrics.application.dtos.job_dtos import JobSummary
from autolyrics.application.interfaces.jobs import IJobRepository
from autolyrics.application.notifications.job_notifications import JobStatusChanged
from autolyrics.application.pipeline.align_lyrics import AlignLyricsCommand
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.application.pipeline.fetch_audio import FetchAudioCommand
from autolyrics.application.pipeline.finalize_lyrics import FinalizeLyricsCommand
from autolyrics.application.pipeline.find_lyrics import FindLyricsCommand
from autolyrics.application.pipeline.polish_lyrics import PolishLyricsCommand
from autolyrics.application.pipeline.reporter import StageReporter
from autolyrics.application.pipeline.resolve_track import ResolveTrackCommand
from autolyrics.application.pipeline.transcribe_lyrics import TranscribeLyricsCommand
from autolyrics.domain.errors import StageFailedError

log = logging.getLogger(__name__)


@dataclass
class RunJobCommand(ICommand[JobSummary]):
    job_id: str


class RunJobHandler(ICommandHandler[RunJobCommand, JobSummary]):
    """Drives one job through every stage command. The repository hands out one Job instance
    per id, so the event handlers and the stages all update the same object."""

    STAGES = (ResolveTrackCommand, FetchAudioCommand, FindLyricsCommand, TranscribeLyricsCommand,
              PolishLyricsCommand, AlignLyricsCommand, FinalizeLyricsCommand)

    def __init__(self, mediator: IMediator, repository: IJobRepository):
        self._mediator = mediator
        self._repository = repository

    async def handle(self, command: RunJobCommand) -> JobSummary:
        job = self._repository.get(command.job_id)
        job.start()
        job.events = []
        self._repository.save(job)
        await self._mediator.publish(JobStatusChanged(job.id, job.status))

        ctx = PipelineContext(job=job, workspace=self._repository.workspace(job.id),
                              reporter=StageReporter(self._mediator, job.id),
                              report={"input": job.options.model_dump()})
        try:
            for stage in self.STAGES:
                await self._mediator.send(stage(ctx))
            job.finish()
        except StageFailedError as error:
            job.fail(str(error))
        except Exception as error:
            log.exception("job %s crashed", job.id)
            job.fail(f"unexpected error: {error}")
        finally:
            if job.status.active:
                job.fail("interrupted")
            report = self._repository.read_report(job.id)
            self._repository.write_report(job.id, {**report, **ctx.report})
            self._repository.save(job)
        await self._mediator.publish(JobStatusChanged(job.id, job.status, job.error))
        return JobSummary.of(job)
