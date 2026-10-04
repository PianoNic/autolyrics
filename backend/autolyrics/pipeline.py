"""The automatic pipeline: song link in, synced lyrics out.

Each stage reports progress through `on_event`, which the CLI prints and the API server streams.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from autolyrics.audio import probe_duration
from autolyrics.config import settings
from autolyrics.export import export_all
from autolyrics.model import Lyrics
from autolyrics.sources import argonfetch
from autolyrics.sources.lyrics import Candidate, Query, rank, search_all, validate

STAGES = ("resolve", "audio", "lyrics", "align", "polish", "export")


@dataclass
class Event:
    stage: str
    status: str  # "running" | "done" | "skipped" | "failed"
    message: str = ""
    data: dict = field(default_factory=dict)
    at: float = field(default_factory=time.time)


@dataclass
class JobOptions:
    url: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    # Use a lyrics file instead of searching (the user's own TTML, LRC or text).
    lyrics_file: Path | None = None


class PipelineError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return slug[:60] or "song"


class Job:
    def __init__(self, options: JobOptions, on_event: Callable[[Event], None] | None = None,
                 job_dir: Path | None = None):
        self.options = options
        self.on_event = on_event or (lambda _e: None)
        self.job_dir = job_dir
        self.events: list[Event] = []
        self.report: dict = {"input": {k: str(v) if isinstance(v, Path) else v
                                       for k, v in asdict(options).items()}}
        self.lyrics: Lyrics | None = None

    def emit(self, stage: str, status: str, message: str = "", **data) -> None:
        event = Event(stage, status, message, data)
        self.events.append(event)
        self.on_event(event)

    async def run(self) -> Lyrics:
        async with httpx.AsyncClient(follow_redirects=True,
                                     headers={"User-Agent": "autolyrics/0.1"}) as client:
            track = await self._resolve(client)
            audio_path, duration = await self._audio(track, client)
            candidates = await self._lyrics(track, duration, client)
            lyrics = self._choose(candidates, duration)
            lyrics = await self._align(lyrics, candidates, audio_path, duration)
            lyrics = await self._polish(lyrics, candidates)
            self._export(lyrics)
            return lyrics

    # -- stages ---------------------------------------------------------------

    async def _resolve(self, client: httpx.AsyncClient) -> argonfetch.ResolvedTrack:
        self.emit("resolve", "running", f"Resolving {self.options.url}")
        try:
            track = await argonfetch.resolve(self.options.url, client)
        except (httpx.HTTPError, ValueError) as error:
            self.emit("resolve", "failed", str(error))
            raise PipelineError("resolve", str(error)) from error
        if self.options.title:
            track.title = self.options.title
        if self.options.artist:
            track.artists = [self.options.artist]
        if not track.title:
            self.emit("resolve", "failed", "Could not determine the song title; pass --title")
            raise PipelineError("resolve", "unknown title")

        if self.job_dir is None:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            name = slugify(f"{' '.join(track.artists)} {track.title}")
            self.job_dir = settings.jobs_dir / f"{stamp}-{name}"
        self.job_dir.mkdir(parents=True, exist_ok=True)

        self.report["track"] = {"title": track.title, "artists": track.artists,
                                "video_id": track.video_id, "cover_url": track.cover_url}
        self.emit("resolve", "done", f"{', '.join(track.artists)} – {track.title}",
                  **self.report["track"])
        return track

    async def _audio(self, track, client) -> tuple[Path, float]:
        self.emit("audio", "running", "Downloading audio via ArgonFetch")
        try:
            path = await argonfetch.download_audio(track, self.job_dir, client)
            duration = probe_duration(path)
        except Exception as error:
            self.emit("audio", "failed", str(error))
            raise PipelineError("audio", str(error)) from error
        self.report["audio"] = {"file": path.name, "duration": round(duration, 3)}
        self.emit("audio", "done", f"{duration:.1f}s, {path.stat().st_size / 1e6:.1f} MB",
                  **self.report["audio"])
        return path, duration

    async def _lyrics(self, track, duration: float, client) -> list[Candidate]:
        self.emit("lyrics", "running", "Searching lyrics sources")
        if self.options.lyrics_file:
            candidates = [_candidate_from_file(self.options.lyrics_file)]
        else:
            query = Query(track=track.title, artist=", ".join(track.artists),
                          album=self.options.album, duration=duration, video_id=track.video_id)
            candidates = await search_all(query, client)
            # Some sources only know the main artist; retry with it when the full list finds nothing.
            if not candidates and len(track.artists) > 1:
                query.artist = track.artists[0]
                candidates = await search_all(query, client)

        cand_dir = self.job_dir / "candidates"
        cand_dir.mkdir(exist_ok=True)
        for i, c in enumerate(candidates):
            validate(c, duration, settings.duration_tolerance)
            ext = {"ttml": "ttml", "lrc": "lrc", "qrc": "qrc", "plain": "txt"}[c.format]
            (cand_dir / f"{i:02d}-{c.source}.{ext}").write_text(c.content, encoding="utf-8", newline="")
        self.report["candidates"] = [c.summary() for c in candidates]
        usable = rank(candidates, duration)
        self.emit("lyrics", "done" if usable else "failed",
                  f"{len(usable)} usable of {len(candidates)} found",
                  candidates=self.report["candidates"])
        return usable

    def _choose(self, usable: list[Candidate], duration: float) -> Lyrics | None:
        if not usable:
            self.report["chosen"] = None
            return None
        best = usable[0]
        lyrics = best.lyrics.model_copy(deep=True)
        lyrics.metadata.duration = duration
        track = self.report["track"]
        lyrics.metadata.title = track["title"]
        lyrics.metadata.artists = track["artists"]
        if self.options.album:
            lyrics.metadata.album = self.options.album
        self.report["chosen"] = best.summary()
        return lyrics

    async def _align(self, lyrics: Lyrics | None, candidates, audio_path, duration) -> Lyrics:
        if lyrics is not None and lyrics.sync_type.is_word_level:
            self.emit("align", "skipped", f"{self.report['chosen']['label']} already has word timing")
            return lyrics
        self.emit("align", "failed", "Word alignment is not implemented yet")
        raise PipelineError("align", "no word-synced lyrics found and alignment is not available")

    async def _polish(self, lyrics: Lyrics, candidates) -> Lyrics:
        self.emit("polish", "skipped", "LLM clean-up is not implemented yet")
        return lyrics

    def _export(self, lyrics: Lyrics) -> None:
        self.emit("export", "running", "Writing files")
        written = export_all(lyrics, self.job_dir / "output")
        (self.job_dir / "output" / "lyrics.json").write_text(
            lyrics.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        self.report["output"] = {k: str(p.relative_to(self.job_dir)) for k, p in written.items()}
        self.report["sync"] = lyrics.sync_type.value
        self.lyrics = lyrics
        self.save_report()
        self.emit("export", "done", f"{len(written)} files in {self.job_dir / 'output'}",
                  files=self.report["output"])

    def save_report(self) -> None:
        if self.job_dir is None:
            return
        self.report["events"] = [asdict(e) for e in self.events]
        (self.job_dir / "report.json").write_text(
            json.dumps(self.report, indent=2, ensure_ascii=False), encoding="utf-8")


def _candidate_from_file(path: Path) -> Candidate:
    from autolyrics.formats.lrc import detect_lrc_sync_type
    from autolyrics.formats.qrc import detect_qrc_sync_type
    from autolyrics.formats.ttml import detect_ttml_sync_type
    from autolyrics.model import SyncType

    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".ttml", ".xml") and "<tt" in content:
        return Candidate("file", path.name, "ttml", content, detect_ttml_sync_type(content))
    if suffix == ".qrc":
        return Candidate("file", path.name, "qrc", content, detect_qrc_sync_type(content))
    if suffix == ".lrc":
        return Candidate("file", path.name, "lrc", content, detect_lrc_sync_type(content))
    return Candidate("file", path.name, "plain", content, SyncType.UNSYNCED)
