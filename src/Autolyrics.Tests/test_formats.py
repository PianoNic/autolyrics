import pytest

from autolyrics.domain.lyrics import Line, Lyrics, SyncType, Word
from autolyrics.infrastructure.services.formats.srt_format import SrtFormat
from autolyrics.infrastructure.services.formats.time_format import TimeFormat


class TestTimeFormat:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("18.893", 18.893), ("1:02.5", 62.5), ("1:02:03.250", 3723.25), ("3:33.107", 213.107),
         ("12.5s", 12.5), ("1500ms", 1.5), ("", None), ("abc", None)],
    )
    def test_parse_ttml(self, value, expected):
        assert TimeFormat.parse_ttml(value) == expected

    def test_spellings(self):
        assert TimeFormat.apple(62.5) == "1:02.500"
        assert TimeFormat.apple(3723.25) == "62:03.250"
        assert TimeFormat.lrc(62.5) == "01:02.50"
        assert TimeFormat.srt(3723.25) == "01:02:03,250"


class TestTtmlFormat:
    def test_parse_apple_fixture(self, ttml, fixtures):
        content = fixtures.read("rick.ttml")
        lyrics = ttml.parse(content)
        assert ttml.detect(content) == SyncType.SYLLABLE
        assert lyrics.sync_type.is_word_level
        assert lyrics.lines[0].text == "We're no strangers to love"
        assert lyrics.lines[0].words[0].begin == pytest.approx(18.893)
        assert lyrics.metadata.language == "en"
        assert lyrics.agents[0].name == "Rick Astley"
        assert "Mike Stock" in lyrics.metadata.songwriters
        assert lyrics.metadata.duration == pytest.approx(213.107)

    def test_round_trip_keeps_words_and_times(self, ttml, fixtures):
        original = ttml.parse(fixtures.read("rick.ttml"))
        again = ttml.parse(ttml.write(original))
        assert [line.text for line in again.lines] == [line.text for line in original.lines]
        for a, b in zip(again.lines, original.lines, strict=True):
            assert [(w.text, w.begin, w.end) for w in a.words] == [
                (w.text, round(w.begin, 3), round(w.end, 3)) for w in b.words]

    def test_golden_output_matches_composer(self, ttml, fixtures):
        """The editor test in frontend/ checks Composer reads this file back identically."""
        golden = fixtures.read("golden-rick-output.ttml")
        assert ttml.write(ttml.parse(golden)) == golden

    def test_background_and_syllables(self, ttml):
        xml = (
            '<tt xmlns="http://www.w3.org/ns/ttml" xmlns:ttm="http://www.w3.org/ns/ttml#metadata">'
            "<body><div>"
            '<p begin="1.0" end="3.0" ttm:agent="v2">'
            '<span begin="1.0" end="1.4">Wel</span><span begin="1.4" end="1.8">come</span> '
            '<span begin="1.8" end="2.2">home</span>'
            '<span ttm:role="x-bg"><span begin="2.2" end="2.6">(oh</span> '
            '<span begin="2.6" end="3.0">yeah)</span></span></p>'
            "</div></body></tt>")
        lyrics = ttml.parse(xml)
        line = lyrics.lines[0]
        assert line.agent == "v2"
        assert [w.text for w in line.words] == ["Wel", "come ", "home"]
        assert line.text == "Welcome home"
        assert line.background_text == "(oh yeah)"
        assert line.display == "Welcome home (oh yeah)"
        assert lyrics.sync_type == SyncType.SYLLABLE
        out = ttml.write(lyrics)
        assert '<span begin="0:01.000" end="0:01.400">Wel</span><span begin="0:01.400"' in out
        assert '<span ttm:role="x-bg">' in out
        assert ttml.parse(out).lines[0].background_text == "(oh yeah)"

    def test_line_synced_and_undeclared_prefix(self, ttml):
        xml = ('<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
               '<p begin="00:01.000" end="00:02.000" itunes:key="L1">Hello there (ooh)</p>'
               "</div></body></tt>")
        lyrics = ttml.parse(xml)
        assert lyrics.sync_type == SyncType.LINE
        assert lyrics.lines[0].bounds() == (1.0, 2.0)
        assert lyrics.lines[0].background_text == "ooh"
        assert "Hello there<span" in ttml.write(lyrics)


class TestLrcFormat:
    def test_parse_fixture(self, lrc, fixtures):
        content = fixtures.read("rick.lrc")
        assert lrc.detect(content) == SyncType.LINE
        lyrics = lrc.parse(content, duration=212.0)
        assert lyrics.sync_type == SyncType.LINE
        assert lyrics.lines[0].text == "We're no strangers to love"
        assert lyrics.lines[0].bounds() == pytest.approx((19.32, 23.21))
        # The LRC closes with an empty [03:30.50] marker, which ends the last line.
        assert lyrics.lines[-1].end == pytest.approx(210.5)

    def test_enhanced_words_and_repeats(self, lrc):
        content = "[ti:Song]\n[00:01.00]<00:01.00>Hi <00:01.50>there<00:02.00>\n[00:03.00][00:05.00]Echo\n"
        assert lrc.detect(content) == SyncType.WORD
        lyrics = lrc.parse(content, duration=7.0)
        assert lyrics.metadata.title == "Song"
        assert [(w.text, w.begin, w.end) for w in lyrics.lines[0].words] == [
            ("Hi ", 1.0, 1.5), ("there", 1.5, 2.0)]
        assert [line.bounds() for line in lyrics.lines[1:]] == [(3.0, 5.0), (5.0, 7.0)]

    def test_writer_word_level(self, lrc):
        lyrics = Lyrics(lines=[Line(words=[Word(text="Hi ", begin=1, end=1.5),
                                           Word(text="there", begin=1.5, end=2)])])
        assert lrc.write(lyrics) == "[00:01.00]Hi there\n"
        assert lrc.write(lyrics, word_level=True) == (
            "[00:01.00]<00:01.00>Hi <00:01.50>there<00:02.00>\n")


class TestQrcFormat:
    def test_fixture_drops_title_and_credits(self, qrc, fixtures):
        content = fixtures.read("rick.qrc.xml")
        assert qrc.detect(content) == SyncType.WORD
        lyrics = qrc.parse(content, duration=213.0)
        texts = [line.text for line in lyrics.lines]
        assert not any("Lyrics by" in t or "Composed by" in t for t in texts)
        assert not texts[0].startswith("Never Gonna Give You Up - Rick")
        first = lyrics.lines[texts.index("We're no strangers to love")]
        assert first.word_timed
        assert first.words[0].text == "We're "

    def test_round_trip(self, qrc):
        lyrics = Lyrics(lines=[Line(words=[Word(text="Hi ", begin=1, end=1.5),
                                           Word(text="there", begin=1.5, end=2)])])
        out = qrc.write(lyrics)
        assert out == "[1000,1000]Hi (1000,500)there(1500,500)\n"
        assert [(w.text, w.begin, w.end) for w in qrc.parse(out).lines[0].words] == [
            ("Hi ", 1.0, 1.5), ("there", 1.5, 2.0)]


class TestPlainAndSrt:
    def test_plain_background_and_sections(self, plain):
        lyrics = plain.parse("[Chorus]\nIch bin raus (Ciao, ciao)\n\n(Yeah)\nDas ist der Song")
        assert [line.text for line in lyrics.lines] == ["Ich bin raus", "", "Das ist der Song"]
        assert lyrics.lines[0].background_text == "Ciao, ciao"
        assert lyrics.lines[1].background_text == "Yeah"
        assert lyrics.sync_type == SyncType.UNSYNCED

    def test_srt(self):
        lyrics = Lyrics(lines=[Line(words=[Word(text="Hi")], begin=1.0, end=2.5)])
        assert SrtFormat.write(lyrics) == "1\n00:00:01,000 --> 00:00:02,500\nHi\n"


class TestExporter:
    def test_writes_lf_files_and_drops_stale_word_formats(self, exporter, ttml, fixtures, tmp_path):
        lyrics = ttml.parse(fixtures.read("rick.ttml"))
        written = exporter.export(lyrics, tmp_path)
        assert set(written) == {"ttml", "lrc", "srt", "lrc_word", "qrc"}
        assert b"\r\n" not in (tmp_path / "lyrics.ttml").read_bytes()
        lyrics.strip_timing()
        lyrics.lines[0].begin, lyrics.lines[0].end = 1.0, 2.0
        assert set(exporter.export(lyrics, tmp_path)) == {"ttml", "lrc", "srt"}
        assert not (tmp_path / "lyrics.qrc").exists()
