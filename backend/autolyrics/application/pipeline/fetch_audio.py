from dataclasses import dataclass

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.interfaces.audio import IAudioTools
from autolyrics.application.interfaces.media import IMediaResolver
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.domain.job import Stage


@dataclass
class FetchAudioCommand(ICommand[Unit]):
    context: PipelineContext


class FetchAudioHandler(ICommandHandler[FetchAudioCommand, Unit]):
    def __init__(self, resolver: IMediaResolver, audio_tools: IAudioTools):
        self._resolver = resolver
        self._audio_tools = audio_tools

    async def handle(self, command: FetchAudioCommand) -> Unit:
        ctx = command.context
        await ctx.reporter.running(Stage.AUDIO, "Downloading audio via ArgonFetch")
        try:
            path = await self._resolver.download_audio(ctx.track, ctx.workspace)
            duration = self._audio_tools.duration(path)
        except Exception as error:  # network, decoder and disk errors alike
            raise await ctx.reporter.fail(Stage.AUDIO, str(error)) from error
        ctx.audio, ctx.duration = path, duration
        ctx.report["audio"] = {"file": path.name, "duration": round(duration, 3)}
        await ctx.reporter.done(Stage.AUDIO,
                                f"{duration:.1f}s, {path.stat().st_size / 1e6:.1f} MB",
                                **ctx.report["audio"])
        return UNIT
