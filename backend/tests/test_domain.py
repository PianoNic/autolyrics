import pytest

from autolyrics.application.pipeline.polish_prompt import PolishPrompt
from autolyrics.domain.candidate import LyricsCandidate
from autolyrics.domain.lyrics import Line, Lyrics, SyncType, Word
from autolyrics.domain.services.candidate_selector import CandidateSelector
from autolyrics.domain.services.decision_applier import DecisionApplier
from autolyrics.domain.services.language_guesser import LanguageGuesser
from autolyrics.domain.services.lyrics_validator import LyricsValidator
from autolyrics.domain.services.offset_estimator import OffsetEstimator
from autolyrics.domain.services.song_title_parser import SongTitleParser
from autolyrics.domain.services.source_comparer import SourceComparer
from autolyrics.domain.services.timing_repairer import TimingRepairer
from autolyrics.domain.track import AudioRendition, Track


def w(text, begin=None, end=None, confidence=None):
    return Word(text=text, begin=begin, end=end, confidence=confidence)


def timed_line(*spec):
    return Line(words=[Word(text=t, begin=b, end=e) for t, b, e in spec])


class TestSongTitleParser:
    @pytest.mark.parametrize(
        ("title", "channel", "expected"),
        [
            ("Rick Astley - Never Gonna Give You Up (Official Music Video)", "Rick Astley",
             ("Never Gonna Give You Up", ["Rick Astley"])),
            ("Never Gonna Give You Up", "Rick Astley - Topic",
             ("Never Gonna Give You Up", ["Rick Astley"])),
            ("Ufo361 & Gunna - Song [Official Video]", "Ufo361", ("Song", ["Ufo361", "Gunna"])),
            ("Artist - Track | A COLORS SHOW", "COLORS", ("Track", ["Artist"])),
            ("Apache 207 - ROLLER prod. by Lucry & Suena (Official Video)", "Apache 207",
             ("ROLLER", ["Apache 207"])),
            ('Ufo361 - "Emotions" (Rich Rich - OUT NOW!)', "Stay High", ("Emotions", ["Ufo361"])),
            ("Song (feat. Someone) [Official Audio]", "Artist - Topic", ("Song", ["Artist"])),
        ],
    )
    def test_parse(self, title, channel, expected):
        assert SongTitleParser().parse(title, channel) == expected


class TestTrack:
    def test_best_audio_prefers_native_high_bitrate(self):
        track = Track("u", "t", [], audio=[
            AudioRendition("a", "media", ".webm", 129.0, None),
            AudioRendition("b", "media", ".m4a", 129.5, None),
            AudioRendition("c", "media", ".mp3", 192.0, "mp3"),
            AudioRendition("d", "media", ".webm", 48.0, None),
        ])
        assert track.best_audio().key == "b"


class TestCandidateSelector:
    def candidate(self, formats, fixtures, source, fmt, name, duration=None):
        c = LyricsCandidate(source, source, fmt, fixtures.read(name), SyncType.LINE,
                            duration=duration)
        c.lyrics = formats.parse(fmt, c.content, 213.6)
        return c

    def test_other_cut_becomes_text_only_and_tiny_lyrics_are_rejected(self, formats, fixtures):
        selector = CandidateSelector()
        long_version = self.candidate(formats, fixtures, "lrclib", "lrc", "rick.lrc", 346)
        selector.judge(long_version, 213.6)
        assert long_version.rejected is None
        assert long_version.text_only
        assert long_version.sync == SyncType.UNSYNCED

        junk = LyricsCandidate("lrclib", "LRCLIB", "lrc", "[00:00.00]probe2", SyncType.LINE,
                               duration=213)
        junk.lyrics = formats.parse("lrc", junk.content, 213.6)
        selector.judge(junk, 213.6)
        assert junk.rejected == "only 1 words"

    def test_timing_past_the_audio_end_is_text_only(self, formats, fixtures):
        c = self.candidate(formats, fixtures, "boidu", "ttml", "rick.ttml")
        CandidateSelector().judge(c, 120.0)
        assert c.text_only
        assert "past the audio end" in c.notes[0]

    def test_rank_prefers_word_timing_then_source(self, formats, fixtures):
        selector = CandidateSelector()
        lrc = self.candidate(formats, fixtures, "lrclib", "lrc", "rick.lrc", 212)
        qrc = self.candidate(formats, fixtures, "portato", "qrc", "rick.qrc.xml")
        ttml = self.candidate(formats, fixtures, "boidu", "ttml", "rick.ttml")
        for c in (lrc, qrc, ttml):
            selector.judge(c, 213.6)
        assert [c.source for c in selector.rank([lrc, qrc, ttml], 213.6)] == [
            "boidu", "portato", "lrclib"]

    def test_text_only_ranks_after_timed_but_keeps_careful_text_first(self, formats, fixtures):
        selector = CandidateSelector()
        plain_lrc = self.candidate(formats, fixtures, "lrclib", "lrc", "rick.lrc", 212)
        other_cut = self.candidate(formats, fixtures, "boidu", "ttml", "rick.ttml", 300)
        lrclib_cut = self.candidate(formats, fixtures, "lrclib", "lrc", "rick.lrc", 300)
        for c in (plain_lrc, other_cut, lrclib_cut):
            selector.judge(c, 213.6)
        assert selector.rank([lrclib_cut, other_cut, plain_lrc], 213.6) == [
            plain_lrc, other_cut, lrclib_cut]


class TestLanguageGuesser:
    def test_votes_and_metadata(self, plain):
        guesser = LanguageGuesser()
        assert guesser.guess(plain.parse("Ich bin raus und das ist der Song")) == "de"
        assert guesser.guess(plain.parse("You know the rules and so do I")) == "en"
        lyrics = plain.parse("Hola")
        lyrics.metadata.language = "es"
        assert guesser.guess(lyrics) == "es"


class TestTimingRepairer:
    def test_fill_gaps_spreads_by_length(self):
        words = [w("a ", 1.0, 1.2), w("bbb "), w("c ", 2.2, 2.4)]
        TimingRepairer().fill_gaps(words, Line(words=words))
        assert words[1].begin == pytest.approx(1.2)
        assert words[1].end == pytest.approx(2.2)
        assert words[1].flags == ["interpolated"]

    def test_fill_gaps_at_edges_and_without_neighbours(self):
        repairer = TimingRepairer()
        words = [w("x "), w("y ", 5.0, 5.5), w("z")]
        repairer.fill_gaps(words, Line(words=words))
        assert words[0].end == pytest.approx(5.0)
        assert words[2].begin == pytest.approx(5.5)
        untimed = [w("only")]
        repairer.fill_gaps(untimed, Line(words=untimed, begin=3.0, end=4.0))
        assert (untimed[0].begin, untimed[0].end) == (3.0, 4.0)

    def test_tidy_closes_gaps_orders_and_flags(self):
        words = [w("a ", 1.0, 1.2, 0.5), w("b ", 1.1, 1.5, 0.01), w("c", 1.7, 1.7, 0.4)]
        TimingRepairer().tidy(words)
        assert words[1].begin == pytest.approx(1.2)  # no overlap with the previous word
        assert words[1].end == pytest.approx(1.7)  # 0.2 s gap closed
        assert words[2].end == pytest.approx(1.75)  # minimum length
        assert words[1].flags == ["low-confidence"]

    def test_reanchor_detached_first_and_last_words(self):
        words = [w("Never ", 10.0, 10.3, 0.01), w("gonna ", 11.5, 11.8, 0.6),
                 w("up", 14.0, 14.2, 0.0)]
        TimingRepairer().reanchor_detached(words)
        assert (words[0].begin, words[0].end) == (pytest.approx(11.2), pytest.approx(11.5))
        assert words[2].begin == pytest.approx(11.8)
        assert words[1].flags == []


class TestOffsetEstimator:
    def test_local_offsets_follow_a_mid_song_shift(self):
        lines = []
        for i in range(12):
            shift = 3.0 if i < 6 else 7.0  # a skit after line 6 adds four seconds
            lines.append(Line(words=[w("x", 10 * i + shift, 10 * i + shift + 1, 0.9)],
                              begin=10 * i))
        offsets = OffsetEstimator().local_line_offsets(lines)
        assert offsets[0] == pytest.approx(3.0)
        assert offsets[-1] == pytest.approx(7.0)

    def test_word_offset(self):
        source = Lyrics(lines=[timed_line(*[(f"w{i} ", i, i + 0.5) for i in range(12)])])
        aligned = source.model_copy(deep=True)
        aligned.shift(0.8)
        for word in aligned.all_words:
            word.confidence = 0.5
        assert OffsetEstimator().word_offset(source, aligned) == {
            "offset": 0.8, "spread": 0.0, "words": 12}


class TestLyrics:
    def test_shift_clamps_at_zero(self):
        lyrics = Lyrics(lines=[Line(words=[w("a", 0.1, 0.5)])])
        lyrics.shift(-0.3)
        assert (lyrics.lines[0].words[0].begin, lyrics.lines[0].words[0].end) == (0.0, 0.2)


class TestLyricsValidator:
    def test_flags_problems(self):
        lyrics = Lyrics(lines=[
            timed_line(("long ", 10.0, 17.0), ("next ", 16.5, 17.5), ("far", 30.0, 30.5)),
            timed_line(("early", 2.0, 2.5)),
        ])
        report = LyricsValidator().check(lyrics, duration=20.0)
        assert report["by_issue"] == {"too-long": 1, "overlap": 1, "big-gap": 1, "past-end": 1,
                                      "out-of-order": 1}
        assert "too-long" in lyrics.lines[0].words[0].flags


CHOSEN = """Ich bin raus
Keine Kappe drauf, Feinsteinjacken
Das ist der Song
Lyrics by: Someone
Ciao (Ciao, ciao)"""

OTHER = """Ich bin raus
Keine Couple-Goals, Wellensteyn-Jacken
SSIO, das ist ein Ding
Das ist der Song
Ciao (Ciao, ciao)"""


class TestSourceComparison:
    def decide(self, plain, chosen_text=CHOSEN, others=(("LRCLIB", OTHER), ("Genius", OTHER))):
        comparer = SourceComparer()
        chosen = plain.parse(chosen_text)
        versions = comparer.group(chosen, [(label, plain.parse(text)) for label, text in others])
        return chosen, versions, comparer.decisions(chosen, versions)

    def test_identical_copies_merge(self, plain):
        _, versions, _ = self.decide(plain, others=(("LRCLIB", OTHER), ("LRCLIB", OTHER),
                                                    ("QQ", OTHER)))
        assert [v.label for v in versions] == ["LRCLIB ×2 + QQ"]

    def test_unrelated_structure_is_skipped(self, plain):
        _, versions, _ = self.decide(plain, others=(("Other", "La la la\nNa na na\nYeah yeah"),))
        assert versions == []

    def test_variants_and_insertions(self, plain):
        _, _, d = self.decide(plain)
        assert len(d.variants) == 1
        assert d.variants[0].line == 1
        assert d.variants[0].options == ["Keine Kappe drauf, Feinsteinjacken",
                                         "Keine Couple-Goals, Wellensteyn-Jacken"]
        assert (d.insertions[0].after, d.insertions[0].text) == (1, "SSIO, das ist ein Ding")
        assert "Wellensteyn-Jacken" in d.vocabulary

    def test_line_break_variants_are_not_offered(self):
        current = ["Glück nicht verwechseln mit Könn'n", "Aber dein Könn'n niemals anzweifeln",
                   "Denn nur mit Blut, Schweiß und Trän'n bezahlt man die Unendlichkeit"]
        joined = "Glück nicht verwechseln mit Könn'n, aber dein Könn'n niemals anzweifeln"
        is_break = SourceComparer.is_line_break_variant
        assert is_break(current, 0, joined)
        assert is_break(current, 1, joined)
        assert is_break(current, 2, "Bezahlt man die Unendlichkeit")
        assert not is_break(current, 0, "Glück nicht verwechseln mit Können")
        assert not is_break(current, 1, "Aber dein Könn'n niemals anzweifeln, ja")

    def test_prompt_lists_everything(self, plain):
        _, _, d = self.decide(plain)
        prompt = PolishPrompt(d, "Song", ["SSIO"], "LRCLIB (line sync)").render()
        assert "The current lyrics come from: LRCLIB (line sync)" in prompt
        assert "V1 – line 1:" in prompt
        assert "I1 – after line 1: SSIO, das ist ein Ding" in prompt
        assert "3: Lyrics by: Someone" in prompt


class TestDecisionApplier:
    def test_untimed_lyrics(self, plain, splitter):
        chosen, _, d = TestSourceComparison().decide(plain)
        answer = {
            "language": "de",
            "variants": [{"id": "V1", "choice": 1, "reason": "brand name"}],
            "insertions": [{"id": "I1", "accept": True}],
            "remove_lines": [{"line": 3, "reason": "credit"}],
            "spelling": [{"from": "Ciao", "to": "Tschau"}],  # invented: no source writes it
            "notes": [{"line": 2, "note": "check"}],
        }
        changes = DecisionApplier(splitter).apply(chosen, d, answer, word_synced=False)
        assert [line.text for line in chosen.lines] == [
            "Ich bin raus", "Keine Couple-Goals, Wellensteyn-Jacken", "SSIO, das ist ein Ding",
            "Das ist der Song", "Ciao"]
        assert chosen.lines[-1].background_text == "Ciao, ciao"
        assert chosen.metadata.language == "de"
        kinds = [c["kind"] for c in changes]
        assert kinds.count("rejected") == 1
        assert {"variant", "insert", "remove", "note", "language"} <= set(kinds)
        assert "llm-insert" in chosen.lines[2].words[0].flags
        assert "llm-note" in chosen.lines[3].words[0].flags

    def test_bad_choices_and_mass_removal_are_rejected(self, plain, splitter):
        chosen, _, d = TestSourceComparison().decide(plain)
        answer = {"variants": [{"id": "V1", "choice": 7}, {"id": "V9", "choice": 1}],
                  "remove_lines": [{"line": i} for i in range(4)]}
        changes = DecisionApplier(splitter).apply(chosen, d, answer, word_synced=False)
        assert len(chosen.lines) == 5
        assert [c["kind"] for c in changes].count("rejected") == 3

    def test_word_synced_line_keeps_or_spreads_times(self, plain, splitter):
        lyrics = Lyrics(lines=[
            timed_line(("Keine ", 1.0, 1.5), ("Kappe ", 1.5, 2.0), ("drauf", 2.0, 3.0)),
            timed_line(("Hallo ", 4.0, 4.5), ("du", 4.5, 5.0))])
        other = Lyrics(lines=[plain.parse("Keine Couple-Goals drauf").lines[0],
                              plain.parse("Hallo du da").lines[0]])
        comparer = SourceComparer()
        d = comparer.decisions(lyrics, comparer.group(lyrics, [("LRCLIB", other)]))
        answer = {"variants": [{"id": f"V{k}", "choice": 1}
                               for k in range(1, len(d.variants) + 1)]}
        DecisionApplier(splitter).apply(lyrics, d, answer, word_synced=True)
        same_count = lyrics.lines[0].words
        assert [x.text for x in same_count] == ["Keine ", "Couple-Goals ", "drauf"]
        assert (same_count[1].begin, same_count[1].end) == (1.5, 2.0)
        spread = lyrics.lines[1].words
        assert [x.text.strip() for x in spread] == ["Hallo", "du", "da"]
        assert spread[0].begin == 4.0
        assert spread[-1].end == pytest.approx(5.0)
        assert "interpolated" in spread[1].flags
