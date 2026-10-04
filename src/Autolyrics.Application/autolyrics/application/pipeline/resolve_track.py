from dataclasses import dataclass

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.interfaces.media import IMediaResolver
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.domain.job import Stage


@dataclass
class ResolveTrackCommand(ICommand[Unit]):
    context: PipelineContext


class ResolveTrackHandler(ICommandHandler[ResolveTrackCommand, Unit]):
    def __init__(self, resolver: IMediaResolver):
        self._resolver = resolver

    async def handle(self, command: ResolveTrackCommand) -> Unit:
        ctx = command.context
        options = ctx.job.options
        await ctx.reporter.running(Stage.RESOLVE, f"Resolving {options.url}")
        try:
            track = await self._resolver.resolve(options.url)
        except Exception as error:  # whatever the adapter's transport raises
            raise await ctx.reporter.fail(Stage.RESOLVE, str(error)) from error
        if options.title:
            track.title = options.title
        if options.artist:
            track.artists = [options.artist]
        if not track.title:
            raise await ctx.reporter.fail(Stage.RESOLVE,
                                          "Could not determine the song title; pass a title")
        ctx.track = track
        ctx.report["track"] = track.summary()
        ctx.job.title, ctx.job.artists, ctx.job.cover_url = track.title, track.artists, track.cover_url
        await ctx.reporter.done(Stage.RESOLVE, f"{', '.join(track.artists)} – {track.title}",
                                **track.summary())
        return UNIT
