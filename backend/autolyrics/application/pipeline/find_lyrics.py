import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.interfaces.jobs import IJobRepository
from autolyrics.application.interfaces.lyrics import ILyricsFormats, ILyricsProvider
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery
from autolyrics.domain.job import Stage
from autolyrics.domain.services.candidate_selector import CandidateSelector

log = logging.getLogger(__name__)


@dataclass
class FindLyricsCommand(ICommand[Unit]):
    context: PipelineContext


class FindLyricsHandler(ICommandHandler[FindLyricsCommand, Unit]):
    """Searches every provider, parses and judges what they return, and picks the lyrics to
    start from: the best usable candidate, without its timing when that belongs to another cut."""

    def __init__(self, providers: list[ILyricsProvider], formats: ILyricsFormats,
                 selector: CandidateSelector, repository: IJobRepository):
        self._providers = providers
        self._formats = formats
        self._selector = selector
        self._repository = repository

    async def handle(self, command: FindLyricsCommand) -> Unit:
        ctx = command.context
        if ctx.job.options.transcribe:
            ctx.report["chosen"] = None
            await ctx.reporter.skipped(Stage.LYRICS, "Lyrics sources skipped; transcribing instead")
            return UNIT
        await ctx.reporter.running(Stage.LYRICS, "Searching lyrics sources")
        candidates = await self._collect(ctx)
        for i, candidate in enumerate(candidates):
            self._parse(candidate, ctx.duration)
            self._selector.judge(candidate, ctx.duration)
            self._repository.save_candidate(ctx.job.id, i, candidate)
        ctx.report["candidates"] = [c.summary() for c in candidates]
        ctx.candidates = self._selector.rank(candidates, ctx.duration)
        if ctx.candidates:
            await ctx.reporter.done(Stage.LYRICS,
                                    f"{len(ctx.candidates)} usable of {len(candidates)} found",
                                    candidates=ctx.report["candidates"])
        else:
            # Not a failure yet: the transcription stage takes over.
            await ctx.reporter.running(Stage.LYRICS, f"none usable of {len(candidates)} found",
                                       candidates=ctx.report["candidates"])
        ctx.lyrics = self._starting_lyrics(ctx)
        return UNIT

    async def _collect(self, ctx: PipelineContext) -> list[LyricsCandidate]:
        options = ctx.job.options
        if options.lyrics_file:
            return [self._formats.candidate_from_file(Path(options.lyrics_file))]
        track = ctx.track
        query = LyricsQuery(track=track.title, artist=", ".join(track.artists),
                            album=options.album, duration=ctx.duration, video_id=track.video_id)
        candidates = await self._search(query)
        # Some sources only know the main artist; retry with it when the full list finds nothing.
        if not candidates and len(track.artists) > 1:
            query.artist = track.artists[0]
            candidates = await self._search(query)
        return candidates

    async def _search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        results = await asyncio.gather(*(p.search(query) for p in self._providers),
                                       return_exceptions=True)
        found: list[LyricsCandidate] = []
        for provider, result in zip(self._providers, results, strict=True):
            if isinstance(result, BaseException):
                log.warning("[%s] crashed: %s", provider.name, result)
                continue
            found.extend(result)
        return found

    def _parse(self, candidate: LyricsCandidate, duration: float | None) -> None:
        try:
            candidate.lyrics = self._formats.parse(candidate.format, candidate.content, duration)
        except Exception as error:  # noqa: BLE001 - any malformed document from an untrusted source
            candidate.rejected = f"unparseable: {error}"

    @staticmethod
    def _starting_lyrics(ctx: PipelineContext):
        best = ctx.chosen
        if best is None:
            ctx.report["chosen"] = None
            return None
        lyrics = best.lyrics.model_copy(deep=True)
        if best.text_only:
            lyrics.strip_timing()
        lyrics.metadata.duration = ctx.duration
        lyrics.metadata.title = ctx.track.title
        lyrics.metadata.artists = list(ctx.track.artists)
        if ctx.job.options.album:
            lyrics.metadata.album = ctx.job.options.album
        ctx.report["chosen"] = best.summary()
        return lyrics
