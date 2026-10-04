"""Composition root: the one place that knows every concrete class and wires them together."""

from collections.abc import Callable

import httpx
from mediatorx import DictResolver, Mediator

from autolyrics import __version__
from autolyrics.application.behaviors import LoggingBehavior
from autolyrics.application.jobs.create_job import CreateJobCommand, CreateJobHandler
from autolyrics.application.jobs.edit_commands import (
    DeleteJobCommand,
    DeleteJobHandler,
    FinishedJobs,
    ImportTtmlCommand,
    ImportTtmlHandler,
    RealignLineCommand,
    RealignLineHandler,
    SaveLyricsCommand,
    SaveLyricsHandler,
)
from autolyrics.application.jobs.lyrics_publisher import LyricsPublisher
from autolyrics.application.jobs.notifications import (
    BroadcastJobEventHandler,
    BroadcastJobStatusHandler,
    JobEventRaised,
    JobStatusChanged,
    RecordJobEventHandler,
)
from autolyrics.application.jobs.queries import (
    GetJobAudioHandler,
    GetJobAudioQuery,
    GetJobFileHandler,
    GetJobFileQuery,
    GetJobHandler,
    GetJobQuery,
    GetLyricsHandler,
    GetLyricsQuery,
    ListJobsHandler,
    ListJobsQuery,
)
from autolyrics.application.jobs.run_job import RunJobCommand, RunJobHandler
from autolyrics.application.pipeline.align_lyrics import AlignLyricsCommand, AlignLyricsHandler
from autolyrics.application.pipeline.fetch_audio import FetchAudioCommand, FetchAudioHandler
from autolyrics.application.pipeline.finalize_lyrics import (
    FinalizeLyricsCommand,
    FinalizeLyricsHandler,
)
from autolyrics.application.pipeline.find_lyrics import FindLyricsCommand, FindLyricsHandler
from autolyrics.application.pipeline.polish_lyrics import PolishLyricsCommand, PolishLyricsHandler
from autolyrics.application.pipeline.resolve_track import ResolveTrackCommand, ResolveTrackHandler
from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.domain.services.candidate_selector import CandidateSelector
from autolyrics.domain.services.decision_applier import DecisionApplier
from autolyrics.domain.services.language_guesser import LanguageGuesser
from autolyrics.domain.services.lyrics_validator import LyricsValidator
from autolyrics.domain.services.offset_estimator import OffsetEstimator
from autolyrics.domain.services.song_title_parser import SongTitleParser
from autolyrics.domain.services.source_comparer import SourceComparer
from autolyrics.domain.services.timing_repairer import TimingRepairer
from autolyrics.infrastructure.config import Settings
from autolyrics.infrastructure.formats.lrc_format import LrcFormat
from autolyrics.infrastructure.formats.lyrics_formats import FileLyricsExporter, LyricsFormats
from autolyrics.infrastructure.formats.plain_format import PlainTextFormat
from autolyrics.infrastructure.formats.qrc_format import QrcFormat
from autolyrics.infrastructure.formats.srt_format import SrtFormat
from autolyrics.infrastructure.formats.ttml_format import TtmlFormat
from autolyrics.infrastructure.llm.openai_compatible_client import OpenAiCompatibleLlmClient
from autolyrics.infrastructure.media.argonfetch import ArgonFetchMediaResolver, RetryPolicy
from autolyrics.infrastructure.media.ffmpeg import Ffmpeg
from autolyrics.infrastructure.ml.demucs_separator import DemucsVocalSeparator
from autolyrics.infrastructure.ml.mms_lyrics_aligner import MmsLyricsAligner
from autolyrics.infrastructure.persistence.file_job_repository import FileJobRepository
from autolyrics.infrastructure.providers.binimum import BinimumProvider
from autolyrics.infrastructure.providers.boidu import BetterLyricsProvider, PortatoProvider
from autolyrics.infrastructure.providers.lrclib import LrclibProvider
from autolyrics.infrastructure.runtime.async_job_queue import AsyncJobQueue
from autolyrics.infrastructure.runtime.event_broadcaster import InMemoryJobEventBroadcaster


class Container:
    """Builds the object graph once and registers every handler with the mediator."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        s = self.settings
        self.http = httpx.AsyncClient(follow_redirects=True,
                                      headers={"User-Agent": f"autolyrics/{__version__}"})

        # domain services
        self.splitter = BackgroundSplitter()
        self.languages = LanguageGuesser()
        self.selector = CandidateSelector(duration_tolerance=s.duration_tolerance)
        self.comparer = SourceComparer()
        self.applier = DecisionApplier(self.splitter)
        self.validator = LyricsValidator()
        self.repairer = TimingRepairer()
        self.offsets = OffsetEstimator()

        # infrastructure
        self.ttml = TtmlFormat(self.splitter)
        self.lrc = LrcFormat(self.splitter)
        self.qrc = QrcFormat()
        self.formats = LyricsFormats(self.ttml, self.lrc, self.qrc, PlainTextFormat(self.splitter))
        self.exporter = FileLyricsExporter(self.ttml, self.lrc, self.qrc, SrtFormat())
        self.ffmpeg = Ffmpeg()
        self.media = ArgonFetchMediaResolver(self.http, s.argonfetch_base_url, SongTitleParser(),
                                             RetryPolicy())
        self.providers = [
            BetterLyricsProvider(self.http, s.boidu_api_key),
            BinimumProvider(self.http),
            PortatoProvider(self.http, s.boidu_api_key, self.qrc),
            LrclibProvider(self.http, self.lrc),
        ]
        self.separator = DemucsVocalSeparator(self.ffmpeg, s.demucs_model)
        self.aligner = MmsLyricsAligner(self.ffmpeg, self.repairer, self.offsets, self.languages)
        self.llm = OpenAiCompatibleLlmClient(self.http, s.llm_base_url, s.llm_api_key, s.llm_model)
        self.repository = FileJobRepository(s.jobs_dir)
        self.broadcaster = InMemoryJobEventBroadcaster()
        self.queue = AsyncJobQueue()

        # application services
        self.publisher = LyricsPublisher(self.repository, self.exporter, self.validator)
        self.finished_jobs = FinishedJobs(self.repository)

        self.resolver = DictResolver()
        self.mediator = Mediator(resolver=self.resolver)
        self._register()

    def handle(self, message: type, handler: type, factory: Callable[[], object]) -> None:
        self.resolver.add_factory(handler, factory)
        self.mediator.register(message, handler)

    def on(self, notification: type, handler: type, factory: Callable[[], object]) -> None:
        self.resolver.add_factory(handler, factory)
        self.mediator.register_notification(notification, handler)

    def _register(self) -> None:
        repo = self.repository

        # pipeline stages
        self.handle(ResolveTrackCommand, ResolveTrackHandler,
                    lambda: ResolveTrackHandler(self.media))
        self.handle(FetchAudioCommand, FetchAudioHandler,
                    lambda: FetchAudioHandler(self.media, self.ffmpeg))
        self.handle(FindLyricsCommand, FindLyricsHandler,
                    lambda: FindLyricsHandler(self.providers, self.formats, self.selector, repo))
        self.handle(PolishLyricsCommand, PolishLyricsHandler,
                    lambda: PolishLyricsHandler(self.llm, self.comparer, self.applier, repo))
        self.handle(AlignLyricsCommand, AlignLyricsHandler,
                    lambda: AlignLyricsHandler(self.separator, self.aligner))
        self.handle(FinalizeLyricsCommand, FinalizeLyricsHandler,
                    lambda: FinalizeLyricsHandler(self.publisher))

        # jobs
        self.handle(CreateJobCommand, CreateJobHandler, lambda: CreateJobHandler(repo, self.queue))
        self.handle(RunJobCommand, RunJobHandler, lambda: RunJobHandler(self.mediator, repo))
        self.handle(DeleteJobCommand, DeleteJobHandler, lambda: DeleteJobHandler(repo))
        self.handle(ListJobsQuery, ListJobsHandler, lambda: ListJobsHandler(repo))
        self.handle(GetJobQuery, GetJobHandler, lambda: GetJobHandler(repo))
        self.handle(GetLyricsQuery, GetLyricsHandler, lambda: GetLyricsHandler(repo))
        self.handle(GetJobFileQuery, GetJobFileHandler, lambda: GetJobFileHandler(repo))
        self.handle(GetJobAudioQuery, GetJobAudioHandler, lambda: GetJobAudioHandler(repo))
        self.handle(SaveLyricsCommand, SaveLyricsHandler,
                    lambda: SaveLyricsHandler(self.finished_jobs, self.publisher))
        self.handle(ImportTtmlCommand, ImportTtmlHandler,
                    lambda: ImportTtmlHandler(self.finished_jobs, repo, self.formats,
                                              self.publisher))
        self.handle(RealignLineCommand, RealignLineHandler,
                    lambda: RealignLineHandler(self.finished_jobs, repo, self.separator,
                                               self.aligner, self.splitter, self.languages,
                                               self.publisher))

        # notifications
        self.on(JobEventRaised, RecordJobEventHandler, lambda: RecordJobEventHandler(repo))
        self.on(JobEventRaised, BroadcastJobEventHandler,
                lambda: BroadcastJobEventHandler(self.broadcaster))
        self.on(JobStatusChanged, BroadcastJobStatusHandler,
                lambda: BroadcastJobStatusHandler(self.broadcaster))

        # behaviors
        self.resolver.add_instance(LoggingBehavior, LoggingBehavior())
        self.mediator.add_behavior(LoggingBehavior)

    async def aclose(self) -> None:
        await self.queue.stop()
        self.aligner.release()
        await self.http.aclose()
