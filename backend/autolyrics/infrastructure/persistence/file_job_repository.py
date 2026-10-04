import json
import secrets
import shutil
import threading
import time
from pathlib import Path

from autolyrics.application.interfaces.jobs import IJobRepository
from autolyrics.domain.candidate import LyricsCandidate
from autolyrics.domain.errors import JobNotFoundError
from autolyrics.domain.job import Job, JobOptions, JobStatus
from autolyrics.domain.lyrics import Lyrics


class FileJobRepository(IJobRepository):
    """One directory per job under `root`:

        job.json          the Job (status, options, events, summary)
        report.json       what each stage found
        source.*          downloaded audio; vocals.wav, vocals16k.wav made from it
        candidates/       every lyrics document the sources returned
        output/           lyrics.json plus every export format

    An identity map: `get` hands out one Job instance per id, so the pipeline and the event
    handlers update the same object instead of overwriting each other's copies.
    """

    JOB_FILE = "job.json"
    REPORT_FILE = "report.json"
    OUTPUT_DIR = "output"
    LYRICS_FILE = "lyrics.json"

    def __init__(self, root: Path):
        self._root = root
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def create(self, options: JobOptions, job_id: str | None = None) -> Job:
        with self._lock:
            job_id = job_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
            existing = self._load(job_id)
            if existing is not None:
                # Re-running into an existing directory keeps its downloads.
                existing.options = options
                existing.status, existing.error = JobStatus.QUEUED, None
                self.save(existing)
                return existing
            job = Job(id=job_id, options=options)
            self.workspace(job_id).mkdir(parents=True, exist_ok=True)
            self._jobs[job_id] = job
            self.save(job)
            return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id) or self._load(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            return job

    def list(self) -> list[Job]:
        with self._lock:
            if self._root.exists():
                for directory in self._root.iterdir():
                    if directory.name not in self._jobs:
                        self._load(directory.name)
            return sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)

    def save(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job
            self._write(self.workspace(job.id) / self.JOB_FILE, job.model_dump_json(indent=2))

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            shutil.rmtree(self.workspace(job_id), ignore_errors=True)

    def workspace(self, job_id: str) -> Path:
        if not job_id or "/" in job_id or "\\" in job_id or job_id in (".", ".."):
            raise JobNotFoundError(job_id)
        return self._root / job_id

    def read_report(self, job_id: str) -> dict:
        path = self.workspace(job_id) / self.REPORT_FILE
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            return {}

    def write_report(self, job_id: str, report: dict) -> None:
        self._write(self.workspace(job_id) / self.REPORT_FILE,
                    json.dumps(report, indent=2, ensure_ascii=False, default=str))

    def save_candidate(self, job_id: str, index: int, candidate: LyricsCandidate) -> None:
        directory = self.workspace(job_id) / "candidates"
        directory.mkdir(exist_ok=True)
        path = directory / f"{index:02d}-{candidate.source}.{candidate.file_extension}"
        path.write_text(candidate.content, encoding="utf-8", newline="")

    def save_artifact(self, job_id: str, name: str, content: str) -> None:
        self._write(self.workspace(job_id) / Path(name).name, content)

    def load_lyrics(self, job_id: str) -> Lyrics | None:
        path = self.output_directory(job_id) / self.LYRICS_FILE
        if not path.exists():
            return None
        return Lyrics.model_validate_json(path.read_text(encoding="utf-8"))

    def save_lyrics(self, job_id: str, lyrics: Lyrics) -> None:
        directory = self.output_directory(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        self._write(directory / self.LYRICS_FILE, lyrics.model_dump_json(indent=2))

    def output_directory(self, job_id: str) -> Path:
        return self.workspace(job_id) / self.OUTPUT_DIR

    def output_file(self, job_id: str, name: str) -> Path | None:
        path = self.output_directory(job_id) / Path(name).name
        return path if path.is_file() else None

    def audio_file(self, job_id: str) -> Path | None:
        directory = self.workspace(job_id)
        if not directory.exists():
            return None
        return next((p for p in directory.iterdir()
                     if p.stem == "source" and p.suffix != ".part" and p.is_file()), None)

    def _load(self, job_id: str) -> Job | None:
        try:
            path = self.workspace(job_id) / self.JOB_FILE
        except JobNotFoundError:
            return None
        if not path.exists():
            return None
        try:
            job = Job.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None
        if job.status.active:
            # Nothing runs across restarts; a job caught mid-run did not finish.
            job.fail("interrupted")
        self._jobs[job.id] = job
        return job

    @staticmethod
    def _write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
