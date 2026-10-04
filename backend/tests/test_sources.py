from pathlib import Path

import pytest

from autolyrics.model import SyncType
from autolyrics.sources.argonfetch import (
    AudioRendition,
    ResolvedTrack,
    clean_youtube_title,
    youtube_video_id,
)
from autolyrics.sources.lyrics import Candidate, rank, validate

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc123&t=4", "abc123"),
        ("https://music.youtube.com/watch?v=lYBUbBu4W08", "lYBUbBu4W08"),
        ("https://youtu.be/xyz", "xyz"),
        ("https://www.youtube.com/shorts/s1", "s1"),
        ("https://open.spotify.com/track/4PTG3Z6ehGkBFwjybzWkR8", None),
        (None, None),
    ],
)
def test_youtube_video_id(url, expected):
    assert youtube_video_id(url) == expected


@pytest.mark.parametrize(
    ("title", "author", "expected"),
    [
        ("Rick Astley - Never Gonna Give You Up (Official Music Video)", "Rick Astley",
         ("Never Gonna Give You Up", ["Rick Astley"])),
        ("Never Gonna Give You Up", "Rick Astley - Topic", ("Never Gonna Give You Up", ["Rick Astley"])),
        ("Ufo361 & Gunna - Song [Official Video]", "Ufo361", ("Song", ["Ufo361", "Gunna"])),
        ("Artist - Track | A COLORS SHOW", "COLORS", ("Track", ["Artist"])),
    ],
)
def test_clean_youtube_title(title, author, expected):
    assert clean_youtube_title(title, author) == expected


def test_best_audio_prefers_native_high_bitrate():
    track = ResolvedTrack("u", "t", [], None, None, [
        AudioRendition("a", "media", ".webm", 129.0, None),
        AudioRendition("b", "media", ".m4a", 129.5, None),
        AudioRendition("c", "media", ".mp3", 192.0, "mp3"),
        AudioRendition("d", "media", ".webm", 48.0, None),
    ])
    assert track.best_audio().key == "b"


def _candidate(source, fmt, name, duration=None):
    content = (FIXTURES / name).read_text(encoding="utf-8")
    return Candidate(source, source, fmt, content, SyncType.LINE, duration=duration)


def test_validate_rejects_wrong_length_and_tiny_lyrics():
    long_version = _candidate("lrclib", "lrc", "rick.lrc", duration=346)
    validate(long_version, 213.6, 3.0)
    assert long_version.rejected.startswith("length")

    junk = Candidate("lrclib", "LRCLIB", "lrc", "[00:00.00]probe2", SyncType.LINE, duration=213)
    validate(junk, 213.6, 3.0)
    assert junk.rejected == "only 1 words"


def test_validate_rejects_timing_past_audio_end():
    c = _candidate("boidu", "ttml", "rick.ttml")
    validate(c, 120.0, 3.0)
    assert "past the end" in c.rejected


def test_rank_prefers_word_timing_then_source():
    lrc = _candidate("lrclib", "lrc", "rick.lrc", duration=212)
    qrc = _candidate("portato", "qrc", "rick.qrc.xml")
    ttml = _candidate("boidu", "ttml", "rick.ttml")
    for c in (lrc, qrc, ttml):
        validate(c, 213.6, 3.0)
    assert [c.source for c in rank([lrc, qrc, ttml], 213.6)] == ["boidu", "portato", "lrclib"]
