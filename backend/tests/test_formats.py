from pathlib import Path

import pytest

from autolyrics.formats.lrc import detect_lrc_sync_type, parse_lrc, write_lrc
from autolyrics.formats.plain import parse_plain
from autolyrics.formats.qrc import detect_qrc_sync_type, parse_qrc, write_qrc
from autolyrics.formats.srt import write_srt
from autolyrics.formats.timefmt import (
    format_lrc_time,
    format_srt_time,
    format_time,
    parse_ttml_time,
)
from autolyrics.formats.ttml import detect_ttml_sync_type, parse_ttml, write_ttml
from autolyrics.model import Line, Lyrics, SyncType, Word

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# -- time ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("18.893", 18.893), ("1:02.5", 62.5), ("1:02:03.250", 3723.25), ("3:33.107", 213.107),
     ("12.5s", 12.5), ("1500ms", 1.5), ("", None), ("abc", None)],
)
def test_parse_ttml_time(value, expected):
    assert parse_ttml_time(value) == expected


def test_format_times():
    assert format_time(62.5) == "1:02.500"
    assert format_time(3723.25) == "62:03.250"
    assert format_lrc_time(62.505) == "01:02.50" or format_lrc_time(62.505) == "01:02.51"
    assert format_srt_time(3723.25) == "01:02:03,250"


# -- TTML ---------------------------------------------------------------------


def test_parse_apple_ttml_fixture():
    lyrics = parse_ttml(read("rick.ttml"))
    assert detect_ttml_sync_type(read("rick.ttml")) == SyncType.SYLLABLE
    assert lyrics.sync_type.is_word_level
    assert lyrics.lines[0].text == "We're no strangers to love"
    assert lyrics.lines[0].words[0].begin == pytest.approx(18.893)
    assert lyrics.metadata.language == "en"
    assert lyrics.agents[0].name == "Rick Astley"
    assert "Mike Stock" in lyrics.metadata.songwriters
    assert lyrics.metadata.duration == pytest.approx(213.107)


def test_ttml_round_trip_keeps_words_and_times():
    original = parse_ttml(read("rick.ttml"))
    again = parse_ttml(write_ttml(original))
    assert [line.text for line in again.lines] == [line.text for line in original.lines]
    for a, b in zip(again.lines, original.lines, strict=True):
        assert [(w.text, w.begin, w.end) for w in a.words] == [
            (w.text, round(w.begin, 3), round(w.end, 3)) for w in b.words
        ]


def test_ttml_background_and_syllables():
    xml = (
        '<tt xmlns="http://www.w3.org/ns/ttml" xmlns:ttm="http://www.w3.org/ns/ttml#metadata">'
        "<body><div>"
        '<p begin="1.0" end="3.0" ttm:agent="v2">'
        '<span begin="1.0" end="1.4">Wel</span><span begin="1.4" end="1.8">come</span> '
        '<span begin="1.8" end="2.2">home</span>'
        '<span ttm:role="x-bg"><span begin="2.2" end="2.6">(oh</span> '
        '<span begin="2.6" end="3.0">yeah)</span></span></p>'
        "</div></body></tt>"
    )
    lyrics = parse_ttml(xml)
    line = lyrics.lines[0]
    assert line.agent == "v2"
    assert [w.text for w in line.words] == ["Wel", "come ", "home"]
    assert line.text == "Welcome home"
    assert line.background_text == "(oh yeah)"
    assert lyrics.sync_type == SyncType.SYLLABLE
    out = write_ttml(lyrics)
    assert '<span begin="0:01.000" end="0:01.400">Wel</span><span begin="0:01.400"' in out
    assert '<span ttm:role="x-bg">' in out
    assert parse_ttml(out).lines[0].background_text == "(oh yeah)"


def test_ttml_line_synced_and_undeclared_prefix():
    xml = (
        '<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
        '<p begin="00:01.000" end="00:02.000" itunes:key="L1">Hello there</p>'
        "</div></body></tt>"
    )
    lyrics = parse_ttml(xml)
    assert lyrics.sync_type == SyncType.LINE
    assert lyrics.lines[0].bounds() == (1.0, 2.0)
    assert "Hello there</p>" in write_ttml(lyrics)


# -- LRC ----------------------------------------------------------------------


def test_parse_lrc_fixture():
    content = read("rick.lrc")
    assert detect_lrc_sync_type(content) == SyncType.LINE
    lyrics = parse_lrc(content, duration=212.0)
    assert lyrics.sync_type == SyncType.LINE
    assert lyrics.lines[0].text == "We're no strangers to love"
    assert lyrics.lines[0].bounds() == pytest.approx((19.32, 23.21))
    # The LRC closes with an empty [03:30.50] marker, which ends the last line.
    assert lyrics.lines[-1].end == pytest.approx(210.5)


def test_lrc_enhanced_words_and_repeats():
    content = "[ti:Song]\n[00:01.00]<00:01.00>Hi <00:01.50>there<00:02.00>\n[00:03.00][00:05.00]Echo\n"
    assert detect_lrc_sync_type(content) == SyncType.WORD
    lyrics = parse_lrc(content, duration=7.0)
    assert lyrics.metadata.title == "Song"
    assert [(w.text, w.begin, w.end) for w in lyrics.lines[0].words] == [
        ("Hi ", 1.0, 1.5), ("there", 1.5, 2.0)]
    assert [line.bounds() for line in lyrics.lines[1:]] == [(3.0, 5.0), (5.0, 7.0)]


def test_lrc_writer_word_level():
    lyrics = Lyrics(lines=[Line(words=[Word(text="Hi ", begin=1, end=1.5),
                                       Word(text="there", begin=1.5, end=2)])])
    assert write_lrc(lyrics) == "[00:01.00]Hi there\n"
    assert write_lrc(lyrics, word_level=True) == "[00:01.00]<00:01.00>Hi <00:01.50>there<00:02.00>\n"


# -- QRC ----------------------------------------------------------------------


def test_parse_qrc_fixture_drops_title_and_credits():
    content = read("rick.qrc.xml")
    assert detect_qrc_sync_type(content) == SyncType.WORD
    lyrics = parse_qrc(content, duration=213.0)
    texts = [line.text for line in lyrics.lines]
    assert not any("Lyrics by" in t or "Composed by" in t for t in texts)
    assert not texts[0].startswith("Never Gonna Give You Up - Rick")
    assert "We're no strangers to love" in texts
    first = lyrics.lines[texts.index("We're no strangers to love")]
    assert first.word_timed
    assert first.words[0].text == "We're "


def test_qrc_round_trip():
    lyrics = Lyrics(lines=[Line(words=[Word(text="Hi ", begin=1, end=1.5),
                                       Word(text="there", begin=1.5, end=2)])])
    out = write_qrc(lyrics)
    assert out == "[1000,1000]Hi (1000,500)there(1500,500)\n"
    again = parse_qrc(out)
    assert [(w.text, w.begin, w.end) for w in again.lines[0].words] == [
        ("Hi ", 1.0, 1.5), ("there", 1.5, 2.0)]


# -- plain / SRT --------------------------------------------------------------


def test_plain_text_background_and_sections():
    lyrics = parse_plain("[Chorus]\nIch bin raus (Ciao, ciao)\n\n(Yeah)\nDas ist der Song")
    assert [line.text for line in lyrics.lines] == ["Ich bin raus", "", "Das ist der Song"]
    assert lyrics.lines[0].background_text == "Ciao, ciao"
    assert lyrics.lines[1].background_text == "Yeah"
    assert lyrics.sync_type == SyncType.UNSYNCED


def test_srt_writer():
    lyrics = Lyrics(lines=[Line(words=[Word(text="Hi")], begin=1.0, end=2.5)])
    assert write_srt(lyrics) == "1\n00:00:01,000 --> 00:00:02,500\nHi\n"
