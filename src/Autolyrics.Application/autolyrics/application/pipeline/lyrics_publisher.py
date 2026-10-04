import time

from autolyrics.application.interfaces.jobs import IJobRepository
from autolyrics.application.interfaces.lyrics import ILyricsExporter
from autolyrics.domain.job import Job
from autolyrics.domain.lyrics import Lyrics
from autolyrics.domain.services.lyrics_validator import LyricsValidator


class LyricsPublisher:
    """Validates lyrics and makes them a job's result: every output format, the lyrics JSON,
    the report and the job's summary. Used by the pipeline and by every later edit."""

    def __init__(self, repository: IJobRepository, exporter: ILyricsExporter,
                 validator: LyricsValidator):
        self._repository = repository
        self._exporter = exporter
        self._validator = validator

    def publish(self, job: Job, lyrics: Lyrics, duration: float | None,
                report: dict | None = None) -> dict:
        report = report if report is not None else self._repository.read_report(job.id)
        duration = duration or lyrics.metadata.duration or (report.get("audio") or {}).get(
            "duration")
        validation = self._validator.check(lyrics, duration)
        written = self._exporter.export(lyrics, self._repository.output_directory(job.id))
        self._repository.save_lyrics(job.id, lyrics)

        files = {key: path.name for key, path in written.items()}
        report.update({"validation": validation, "sync": lyrics.sync_type.value,
                       "output": files, "published": time.time()})
        self._repository.write_report(job.id, report)

        job.sync = lyrics.sync_type.value
        job.flagged_words = validation["flagged_words"]
        job.total_words = validation["total_words"]
        self._repository.save(job)
        return {"validation": validation, "sync": job.sync, "files": files}
