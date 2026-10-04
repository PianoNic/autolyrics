from pathlib import Path

from autolyrics.application.interfaces.lyrics import ILyricsExporter, ILyricsFormats
from autolyrics.domain.candidate import LyricsCandidate
from autolyrics.domain.lyrics import Lyrics, SyncType
from autolyrics.infrastructure.services.formats.lrc_format import LrcFormat
from autolyrics.infrastructure.services.formats.plain_format import PlainTextFormat
from autolyrics.infrastructure.services.formats.qrc_format import QrcFormat
from autolyrics.infrastructure.services.formats.srt_format import SrtFormat
from autolyrics.infrastructure.services.formats.ttml_format import TtmlFormat


class LyricsFormats(ILyricsFormats):
    def __init__(self, ttml: TtmlFormat, lrc: LrcFormat, qrc: QrcFormat, plain: PlainTextFormat):
        self._ttml = ttml
        self._lrc = lrc
        self._qrc = qrc
        self._plain = plain

    def parse(self, format: str, content: str, duration: float | None = None) -> Lyrics:
        if format == "ttml":
            return self._ttml.parse(content)
        if format == "lrc":
            return self._lrc.parse(content, duration)
        if format == "qrc":
            return self._qrc.parse(content, duration)
        if format == "plain":
            return self._plain.parse(content)
        raise ValueError(f"unknown lyrics format {format!r}")

    def candidate_from_file(self, path: Path) -> LyricsCandidate:
        content = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        if suffix in (".ttml", ".xml") and "<tt" in content:
            return LyricsCandidate("file", path.name, "ttml", content, self._ttml.detect(content))
        if suffix == ".qrc":
            return LyricsCandidate("file", path.name, "qrc", content, self._qrc.detect(content))
        if suffix == ".lrc":
            return LyricsCandidate("file", path.name, "lrc", content, self._lrc.detect(content))
        return LyricsCandidate("file", path.name, "plain", content, SyncType.UNSYNCED)


class FileLyricsExporter(ILyricsExporter):
    """Writes every output format; word-level formats only when the lyrics are word-timed."""

    def __init__(self, ttml: TtmlFormat, lrc: LrcFormat, qrc: QrcFormat, srt: SrtFormat):
        self._ttml = ttml
        self._lrc = lrc
        self._qrc = qrc
        self._srt = srt

    def render_ttml(self, lyrics: Lyrics) -> str:
        return self._ttml.write(lyrics)

    def export(self, lyrics: Lyrics, directory: Path) -> dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        files = {
            "ttml": ("lyrics.ttml", self._ttml.write(lyrics)),
            "lrc": ("lyrics.lrc", self._lrc.write(lyrics)),
            "srt": ("lyrics.srt", self._srt.write(lyrics)),
        }
        if lyrics.sync_type.is_word_level:
            files["lrc_word"] = ("lyrics.word.lrc", self._lrc.write(lyrics, word_level=True))
            files["qrc"] = ("lyrics.qrc", self._qrc.write(lyrics))
        written = {}
        for key, (name, content) in files.items():
            path = directory / name
            # LF everywhere, so files match what Composer writes regardless of the OS.
            path.write_text(content, encoding="utf-8", newline="\n")
            written[key] = path
        for stale in ("lyrics.word.lrc", "lyrics.qrc"):
            if not lyrics.sync_type.is_word_level and (directory / stale).exists():
                (directory / stale).unlink()
        return written
