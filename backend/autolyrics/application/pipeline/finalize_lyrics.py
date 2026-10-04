from dataclasses import dataclass

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.jobs.lyrics_publisher import LyricsPublisher
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.domain.job import Stage


@dataclass
class FinalizeLyricsCommand(ICommand[Unit]):
    context: PipelineContext


class FinalizeLyricsHandler(ICommandHandler[FinalizeLyricsCommand, Unit]):
    """Validates the result and writes every output format."""

    def __init__(self, publisher: LyricsPublisher):
        self._publisher = publisher

    async def handle(self, command: FinalizeLyricsCommand) -> Unit:
        ctx = command.context
        await ctx.reporter.running(Stage.EXPORT, "Checking and writing files")
        result = self._publisher.publish(ctx.job, ctx.lyrics, ctx.duration, ctx.report)
        await ctx.reporter.done(
            Stage.EXPORT, f"{len(result['files'])} files written, "
            f"{result['validation']['flagged_words']} words flagged for review",
            files=result["files"])
        return UNIT
