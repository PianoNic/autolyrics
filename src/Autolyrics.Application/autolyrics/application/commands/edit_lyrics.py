import asyncio
from dataclasses import dataclass

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.dtos.job_dtos import RealignResult, SaveResult
from autolyrics.application.interfaces.audio import ILyricsAligner, IVocalSeparator
from autolyrics.application.interfaces.jobs import IJobRepository
from autolyrics.application.interfaces.lyrics import ILyricsFormats
from autolyrics.application.pipeline.lyrics_publisher import LyricsPublisher
from autolyrics.domain.errors import InvalidInputError, JobStateError, NotFoundError
from autolyrics.domain.job import Job, JobStatus
from autolyrics.domain.lyrics import Lyrics, Word
from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.domain.services.language_guesser import LanguageGuesser


class FinishedJobs:
    """Loads a job that may be edited: it must exist and have finished."""

    def __init__(self, repository: IJobRepository):
        self._repository = repository

    def get(self, job_id: str) -> Job:
        job = self._repository.get(job_id)
        if job.status != JobStatus.DONE:
            raise JobStateError("the job has not finished")
        return job


@dataclass
class SaveLyricsCommand(ICommand[SaveResult]):
    job_id: str
    lyrics: Lyrics


class SaveLyricsHandler(ICommandHandler[SaveLyricsCommand, SaveResult]):
    """Edits from the review screen replace the job's lyrics and every output file."""

    def __init__(self, jobs: FinishedJobs, publisher: LyricsPublisher):
        self._jobs = jobs
        self._publisher = publisher

    async def handle(self, command: SaveLyricsCommand) -> SaveResult:
        job = self._jobs.get(command.job_id)
        return SaveResult(**self._publisher.publish(job, command.lyrics, None))


@dataclass
class ImportTtmlCommand(ICommand[SaveResult]):
    job_id: str
    ttml: str


class ImportTtmlHandler(ICommandHandler[ImportTtmlCommand, SaveResult]):
    """Saves from the Composer editor: its TTML replaces the job's lyrics."""

    def __init__(self, jobs: FinishedJobs, repository: IJobRepository, formats: ILyricsFormats,
                 publisher: LyricsPublisher):
        self._jobs = jobs
        self._repository = repository
        self._formats = formats
        self._publisher = publisher

    async def handle(self, command: ImportTtmlCommand) -> SaveResult:
        job = self._jobs.get(command.job_id)
        try:
            lyrics = self._formats.parse("ttml", command.ttml)
        except Exception as error:
            raise InvalidInputError(f"invalid TTML: {error}") from error
        previous = self._repository.load_lyrics(job.id)
        if previous is not None:
            lyrics.metadata.duration = lyrics.metadata.duration or previous.metadata.duration
        return SaveResult(**self._publisher.publish(job, lyrics, None))


@dataclass
class RealignLineCommand(ICommand[RealignResult]):
    job_id: str
    index: int
    text: str | None = None
    start: float | None = None
    end: float | None = None


class RealignLineHandler(ICommandHandler[RealignLineCommand, RealignResult]):
    """Re-times one line against the vocals, optionally with new text: the fix for a line the
    reviewer corrected or the aligner got wrong."""

    def __init__(self, jobs: FinishedJobs, repository: IJobRepository,
                 separator: IVocalSeparator, aligner: ILyricsAligner,
                 splitter: BackgroundSplitter, languages: LanguageGuesser,
                 publisher: LyricsPublisher):
        self._jobs = jobs
        self._repository = repository
        self._separator = separator
        self._aligner = aligner
        self._splitter = splitter
        self._languages = languages
        self._publisher = publisher

    async def handle(self, command: RealignLineCommand) -> RealignResult:
        job = self._jobs.get(command.job_id)
        lyrics = self._repository.load_lyrics(job.id)
        if lyrics is None or not 0 <= command.index < len(lyrics.lines):
            raise NotFoundError("no such line")
        line = lyrics.lines[command.index]
        if command.text is not None:
            if not command.text.strip():
                raise InvalidInputError("a line needs text")
            main, background = self._splitter.split(command.text)
            line.words, line.background = main or Word.tokenize(command.text), background
        start, end = self._window(lyrics, command.index)
        start = command.start if command.start is not None else start
        end = command.end if command.end is not None else end
        audio = self._repository.audio_file(job.id)
        if audio is None:
            raise NotFoundError("this job has no audio")
        workspace = self._repository.workspace(job.id)
        language = self._languages.guess(lyrics)
        aligned = await asyncio.to_thread(self._realign, line, audio, workspace, language,
                                          start, end)
        result = self._publisher.publish(job, lyrics, None)
        return RealignResult(**result, aligned=aligned, line=line.model_dump())

    def _realign(self, line, audio, workspace, language, start, end) -> bool:
        stems = self._separator.stems(audio, workspace)
        return self._aligner.realign_line(line, stems, workspace, language, start, end)

    @staticmethod
    def _window(lyrics: Lyrics, index: int) -> tuple[float, float]:
        """The line's own span, widened up to its neighbours, so an edited line can move."""
        bounds = lyrics.lines[index].bounds()
        prev_end = next((b[1] for line in reversed(lyrics.lines[:index]) if (b := line.bounds())),
                        None)
        next_begin = next((b[0] for line in lyrics.lines[index + 1:] if (b := line.bounds())),
                          None)
        if bounds is None:
            start = prev_end if prev_end is not None else 0.0
            return start, next_begin if next_begin is not None else start + 6.0
        start = max(bounds[0] - 1.0, prev_end if prev_end is not None else 0.0)
        end = min(bounds[1] + 1.0, next_begin if next_begin is not None else bounds[1] + 1.0)
        return min(start, bounds[0]), max(end, bounds[1])


@dataclass
class DeleteJobCommand(ICommand[Unit]):
    job_id: str


class DeleteJobHandler(ICommandHandler[DeleteJobCommand, Unit]):
    def __init__(self, repository: IJobRepository):
        self._repository = repository

    async def handle(self, command: DeleteJobCommand) -> Unit:
        job = self._repository.get(command.job_id)
        if job.status.active:
            raise JobStateError("the job is still running")
        self._repository.delete(job.id)
        return UNIT
