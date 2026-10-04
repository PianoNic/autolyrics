"""Pure alignment logic; the model itself is exercised by scripts/benchmark_align.py."""

import string

import pytest

from autolyrics.align import (
    _local_offsets,
    fill_gaps,
    guess_language,
    normalize,
    polish_line,
    reanchor_detached,
    shift_lyrics,
)
from autolyrics.formats.plain import parse_plain
from autolyrics.model import Line, Lyrics, Word

ALPHABET = set(string.ascii_lowercase) | {"'"}


@pytest.mark.parametrize(
    ("word", "language", "expected"),
    [
        ("Größe,", "de", "grosse"),
        ("Wellensteyn-Jacken", "de", "wellensteynjacken"),
        ("187", "de", "hundertsiebenundachtzig"),
        ("I'm", "en", "i'm"),
        ("don’t", "en", "don't"),
        ("&", "de", "und"),
        ("—", "de", ""),
        ("Çok", "tr", "cok"),
    ],
)
def test_normalize(word, language, expected):
    assert normalize(word, language, ALPHABET) == expected


def test_guess_language():
    assert guess_language(parse_plain("Ich bin raus und das ist der Song")) == "de"
    assert guess_language(parse_plain("You know the rules and so do I")) == "en"
    lyrics = parse_plain("Hola")
    lyrics.metadata.language = "es"
    assert guess_language(lyrics) == "es"


def w(text, begin=None, end=None, confidence=None):
    return Word(text=text, begin=begin, end=end, confidence=confidence)


def test_fill_gaps_spreads_by_length():
    words = [w("a ", 1.0, 1.2), w("bbb "), w("c ", 2.2, 2.4)]
    fill_gaps(words, Line(words=words))
    assert words[1].begin == pytest.approx(1.2)
    assert words[1].end == pytest.approx(2.2)
    assert words[1].flags == ["interpolated"]


def test_fill_gaps_at_line_edges_and_without_neighbours():
    words = [w("x "), w("y ", 5.0, 5.5), w("z")]
    fill_gaps(words, Line(words=words))
    assert words[0].end == pytest.approx(5.0)
    assert words[2].begin == pytest.approx(5.5)
    untimed = [w("only")]
    fill_gaps(untimed, Line(words=untimed, begin=3.0, end=4.0))
    assert (untimed[0].begin, untimed[0].end) == (3.0, 4.0)


def test_polish_closes_small_gaps_orders_and_flags():
    words = [w("a ", 1.0, 1.2, 0.5), w("b ", 1.1, 1.5, 0.01), w("c", 1.7, 1.7, 0.4)]
    polish_line(words)
    assert words[1].begin == pytest.approx(1.2)  # no overlap with the previous word
    assert words[1].end == pytest.approx(1.7)  # 0.2 s gap closed
    assert words[2].end == pytest.approx(1.75)  # minimum length
    assert words[1].flags == ["low-confidence"]


def test_reanchor_detached_first_and_last_words():
    words = [w("Never ", 10.0, 10.3, 0.01), w("gonna ", 11.5, 11.8, 0.6), w("up", 14.0, 14.2, 0.0)]
    reanchor_detached(words)
    assert words[0].end == pytest.approx(11.5)
    assert words[0].begin == pytest.approx(11.2)
    assert words[2].begin == pytest.approx(11.8)
    assert words[1].flags == []


def test_local_offsets_follow_a_mid_song_shift():
    lines = []
    for i in range(12):
        shift = 3.0 if i < 6 else 7.0  # a skit after line 6 adds four seconds
        lines.append(Line(words=[w("x", 10 * i + shift, 10 * i + shift + 1, 0.9)], begin=10 * i))
    offsets = _local_offsets(lines)
    assert offsets[0] == pytest.approx(3.0)
    assert offsets[-1] == pytest.approx(7.0)


def test_shift_lyrics_clamps_at_zero():
    lyrics = Lyrics(lines=[Line(words=[w("a", 0.1, 0.5)])])
    shift_lyrics(lyrics, -0.3)
    assert (lyrics.lines[0].words[0].begin, lyrics.lines[0].words[0].end) == (0.0, 0.2)
