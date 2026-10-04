from pathlib import Path

import pytest

from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.infrastructure.services.formats.lrc_format import LrcFormat
from autolyrics.infrastructure.services.formats.lyrics_formats import (
    FileLyricsExporter,
    LyricsFormats,
)
from autolyrics.infrastructure.services.formats.plain_format import PlainTextFormat
from autolyrics.infrastructure.services.formats.qrc_format import QrcFormat
from autolyrics.infrastructure.services.formats.srt_format import SrtFormat
from autolyrics.infrastructure.services.formats.ttml_format import TtmlFormat

FIXTURES = Path(__file__).parent / "fixtures"


class Fixtures:
    @staticmethod
    def read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixtures() -> Fixtures:
    return Fixtures()


@pytest.fixture
def splitter() -> BackgroundSplitter:
    return BackgroundSplitter()


@pytest.fixture
def ttml(splitter) -> TtmlFormat:
    return TtmlFormat(splitter)


@pytest.fixture
def lrc(splitter) -> LrcFormat:
    return LrcFormat(splitter)


@pytest.fixture
def qrc() -> QrcFormat:
    return QrcFormat()


@pytest.fixture
def plain(splitter) -> PlainTextFormat:
    return PlainTextFormat(splitter)


@pytest.fixture
def formats(ttml, lrc, qrc, plain) -> LyricsFormats:
    return LyricsFormats(ttml, lrc, qrc, plain)


@pytest.fixture
def exporter(ttml, lrc, qrc) -> FileLyricsExporter:
    return FileLyricsExporter(ttml, lrc, qrc, SrtFormat())
