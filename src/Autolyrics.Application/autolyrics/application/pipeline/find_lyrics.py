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
from autolyrics.domain.lyrics import SyncType
from autolyrics.domain.services.candidate_selector import CandidateSelector
from autolyrics.domain.services.lyrics_tidier import LyricsTidier

log = logging.getLogger(__name__)


@dataclass
class FindLyricsCommand(ICommand[Unit]):
    context: PipelineContext


class FindLyricsHandler(ICommandHandler[FindLyricsCommand, Unit]):
    """Searches every provider, parses and judges what they return, and picks the lyrics to
    start from: the best usable candidate, without its timing when that belongs to another cut."""

    USER_SOURCES = ("user", "file")

    def __init__(self, providers: list[ILyricsProvider], formats: ILyricsFormats,
                 selector: CandidateSelector, repository: IJobRepository, tidier: LyricsTidier):
        self._tidier = tidier
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
            self._examine(candidate, ctx.duration)
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
        # Text the user gave us (pasted, or a file) is theirs to style; only source text is tidied.
        if ctx.lyrics is not None and ctx.chosen.source not in self.USER_SOURCES:
            ctx.report["tidied"] = self._tidier.tidy(ctx.lyrics)
        return UNIT

    async def _collect(self, ctx: PipelineContext) -> list[LyricsCandidate]:
        options = ctx.job.options
        if options.lyrics_text and options.lyrics_text.strip():
            return [LyricsCandidate("user", "Your lyrics", "plain", options.lyrics_text,
                                    SyncType.UNSYNCED)]
        if options.lyrics_file:
            return [self._formats.candidate_from_file(Path(options.lyrics_file))]
        track = ctx.track
        query = LyricsQuery(track=track.title, artist=", ".join(track.artists),
                            album=options.album, duration=ctx.duration, video_id=track.video_id)
        candidates = await self._search(query, ctx.duration)
        # Some sources only know the main artist; retry with it when the full list finds nothing.
        if not candidates and len(track.artists) > 1:
            query.artist = track.artists[0]
            candidates = await self._search(query, ctx.duration)
        return candidates

    async def _search(self, query: LyricsQuery, duration: float | None) -> list[LyricsCandidate]:
        """Every provider at once. The first word-synced result that fits this recording ends
        the search: nothing a slower source could send would be better, and its text is what
        word-synced files are made from."""
        tasks = {asyncio.create_task(p.search(query)): p for p in self._providers}
        found: list[LyricsCandidate] = []
        try:
            for done in asyncio.as_completed(tasks):
                try:
                    result = await done
                except Exception as error:  # noqa: BLE001 - one broken source must not sink the search
                    log.warning("[lyrics] a provider crashed: %s", error)
                    continue
                for candidate in result:
                    self._examine(candidate, duration)
                found.extend(result)
                if any(self._fits_word_synced(c) for c in result):
                    break
        finally:
            for task in tasks:
                task.cancel()
        return found

    def _examine(self, candidate: LyricsCandidate, duration: float | None) -> None:
        """Parse and judge a candidate once."""
        if candidate.lyrics is None and candidate.rejected is None:
            self._parse(candidate, duration)
            self._selector.judge(candidate, duration)

    @staticmethod
    def _fits_word_synced(candidate: LyricsCandidate) -> bool:
        return (candidate.rejected is None and not candidate.text_only
                and candidate.lyrics is not None and candidate.lyrics.sync_type.is_word_level)

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
