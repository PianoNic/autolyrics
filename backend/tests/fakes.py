"""Test doubles for every port that touches the network, the GPU or ffmpeg."""

from pathlib import Path

from autolyrics.application.interfaces.audio import (
    IAudioTools,
    ILyricsAligner,
    ITranscriber,
    IVocalSeparator,
)
from autolyrics.application.interfaces.llm import ILlmClient
from autolyrics.application.interfaces.lyrics import ILyricsProvider
from autolyrics.application.interfaces.media import IMediaResolver
from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
from autolyrics.composition.container import Container
from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery
from autolyrics.domain.lyrics import Line, Lyrics, SyncType, Word
from autolyrics.domain.track import AudioRendition, Track
from autolyrics.infrastructure.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


class FakeMedia(IMediaResolver):
    def __init__(self, fail: bool = False):
        self.fail = fail

    async def resolve(self, url: str) -> Track:
        if self.fail:
            raise ConnectionError("ArgonFetch is down")
        return Track(url, "Never Gonna Give You Up", ["Rick Astley"], video_id="lYBUbBu4W08",
                     audio=[AudioRendition("k", "media", ".m4a", 129.0, None)])

    async def download_audio(self, track: Track, directory: Path,
                             progress: IProgress = NO_PROGRESS) -> Path:
        progress.update(1.0, "fake")
        path = directory / "source.m4a"
        path.write_bytes(b"audio")
        return path


class FakeAudioTools(IAudioTools):
    def duration(self, path: Path) -> float:
        return 213.6


class FixtureProvider(ILyricsProvider):
    def __init__(self, name: str, fmt: str, fixture: str, sync: SyncType,
                 duration: float | None = None):
        self.name = name
        self._candidate = (fmt, fixture, sync, duration)

    async def search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        fmt, fixture, sync, duration = self._candidate
        content = (FIXTURES / fixture).read_text(encoding="utf-8")
        return [LyricsCandidate(self.name, self.name.upper(), fmt, content, sync,
                                query.track, query.artist, duration)]


class CrashingProvider(ILyricsProvider):
    name = "crashing"

    async def search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        raise RuntimeError("boom")


class FakeSeparator(IVocalSeparator):
    def separate(self, audio: Path, workspace: Path,
                 progress: IProgress = NO_PROGRESS) -> Path:
        path = workspace / "vocals.wav"
        path.write_bytes(b"vocals")
        return path


class FakeAligner(ILyricsAligner):
    """Lays words out half a second apart, line after line."""

    def __init__(self, offset: float = 0.0):
        self.offset = offset
        self.released = 0
        self.realigned: list[tuple[float, float]] = []

    def align(self, lyrics: Lyrics, vocals: Path, workspace: Path,
              progress: IProgress = NO_PROGRESS) -> dict:
        t = 10.0
        for line in lyrics.content_lines:
            for w in line.all_words:
                w.begin, w.end, w.confidence = t, t + 0.4, 0.5
                t += 0.5
            line.begin = line.end = None
            t += 1.0
        return {"language": "en", "mode": "global", "line_offset": 0.0,
                "words": len(lyrics.all_words), "low_confidence": 0, "interpolated": 0,
                "reanchored": 0, "mean_confidence": 0.5, "failed_lines": 0}

    def measure_offset(self, lyrics: Lyrics, vocals: Path, workspace: Path) -> dict:
        return {"offset": self.offset, "spread": 0.02, "words": 300}

    def realign_line(self, line: Line, vocals: Path, workspace: Path, language: str,
                     start: float, end: float) -> bool:
        self.realigned.append((start, end))
        step = (end - start) / max(1, len(line.all_words))
        for i, w in enumerate(line.all_words):
            w.begin, w.end = round(start + i * step, 3), round(start + (i + 1) * step, 3)
        return True

    def release(self) -> None:
        self.released += 1


class FakeTranscriber(ITranscriber):
    def __init__(self, text: str = "Hello from Whisper\nSecond line here"):
        self.text = text
        self.released = 0

    def transcribe(self, vocals: Path, workspace: Path, language: str | None = None,
                   progress: IProgress = NO_PROGRESS) -> Lyrics:
        lines = [Line(words=Word.tokenize(t), begin=10.0 * i, end=10.0 * i + 4)
                 for i, t in enumerate(self.text.splitlines()) if t.strip()]
        lyrics = Lyrics(lines=lines)
        lyrics.metadata.language = "en"
        return lyrics

    def release(self) -> None:
        self.released += 1


class FakeLlm(ILlmClient):
    def __init__(self, answer: dict | None = None, configured: bool = True):
        self.answer = answer or {"language": "en"}
        self._configured = configured
        self.prompts: list[str] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def complete_json(self, system: str, prompt: str) -> dict:
        self.prompts.append(prompt)
        return self.answer


class FakeContainer:
    """The real container with every outside-world port replaced by a fake."""

    @staticmethod
    def build(jobs_dir: Path, providers: list[ILyricsProvider] | None = None,
              **overrides) -> Container:
        container = Container(Settings(jobs_dir=jobs_dir, llm_api_key=None, boidu_api_key=None))
        container.media = overrides.get("media", FakeMedia())
        container.ffmpeg = FakeAudioTools()
        container.providers = providers if providers is not None else [
            FixtureProvider("lrclib", "lrc", "rick.lrc", SyncType.LINE, 212.0)]
        container.separator = overrides.get("separator", FakeSeparator())
        container.aligner = overrides.get("aligner", FakeAligner())
        container.llm = overrides.get("llm", FakeLlm(configured=False))
        container.transcriber = overrides.get("transcriber", FakeTranscriber())
        return container
