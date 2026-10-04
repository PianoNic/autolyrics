import numpy as np

from autolyrics.infrastructure.services.ml.singing.acoustic import Emissions
from autolyrics.infrastructure.services.ml.singing.ctc_solver import GlobalCtcSolver, SolverLine

BLANK, A, B, GAP = 0, 1, 2, 3


def emissions(frames: int, peaks: dict[int, list[int]]) -> Emissions:
    """Blank everywhere except the given token at the given frames."""
    p = np.full((frames, 4), 0.01)
    p[:, BLANK] = 0.97
    for token, at in peaks.items():
        for t in at:
            p[t] = 0.01
            p[t, token] = 0.97
    return Emissions(np.log(p / p.sum(1, keepdims=True)).astype(np.float32), 0.1, BLANK)


class TestGlobalCtcSolver:
    def test_places_words_where_their_tokens_are_heard(self):
        em = emissions(40, {A: [5, 6, 7], B: [20, 21]})
        spans = GlobalCtcSolver().solve(em, [SolverLine([[A], [B]])], word_gap=None,
                                        line_gap=None)
        assert [(round(s.begin, 1), round(s.end, 1)) for s in spans] == [(0.5, 0.8), (2.0, 2.2)]
        assert all(s.score > 0.5 for s in spans)

    def test_optional_gap_tokens_may_be_skipped(self):
        em = emissions(30, {A: [5], B: [6]})  # sung straight through, no gap
        spans = GlobalCtcSolver().solve(em, [SolverLine([[A], [B]])], word_gap=GAP,
                                        line_gap=None)
        assert [round(s.begin, 1) for s in spans] == [0.5, 0.6]

    def test_the_source_line_time_picks_between_two_equal_candidates(self):
        # The same word is heard twice; the source says the line starts near 3.0 s.
        em = emissions(60, {A: [10, 30]})
        late = GlobalCtcSolver().solve(em, [SolverLine([[A]], prior_start=3.0)], None, None)
        early = GlobalCtcSolver().solve(em, [SolverLine([[A]], prior_start=1.0)], None, None)
        assert round(late[0].begin, 1) == 3.0 and round(early[0].begin, 1) == 1.0

    def test_repeated_tokens_need_a_blank_between_them(self):
        em = emissions(30, {A: [5, 9]})
        spans = GlobalCtcSolver().solve(em, [SolverLine([[A, A]])], None, None)
        assert [(t.begin, t.end) for t in spans[0].tokens] == [(5, 6), (9, 10)]


class TestSyllables:
    def test_hyphenation_keeps_the_trailing_space_on_the_last_piece(self):
        from autolyrics.infrastructure.services.ml.singing.syllables import Syllabifier

        assert Syllabifier().pieces("beautiful ", "en") == ["beau", "ti", "ful "]
        assert Syllabifier().pieces("fire ", "en") == ["fire "]

    def test_each_syllable_starts_at_the_consonant_before_its_vowel(self):
        from autolyrics.domain.lyrics import Word
        from autolyrics.infrastructure.services.ml.singing.ctc_solver import TokenSpan, WordSpan
        from autolyrics.infrastructure.services.ml.singing.lam_model import PHONE_ID
        from autolyrics.infrastructure.services.ml.singing.syllables import (
            Syllabifier,
            SyllableTimer,
        )

        phones = ["b", "j", "uː", "t", "ɪ", "f", "ʊ", "l"]  # beautiful
        tokens = [PHONE_ID[p] for p in phones]
        spans = [TokenSpan(10 + 5 * i, 11 + 5 * i, 0.9) for i in range(len(phones))]
        span = WordSpan(0, 0, 1.0, 4.6, 0.9, spans)
        word = Word(text="beautiful ", begin=1.0, end=5.0, confidence=0.9)
        pieces = SyllableTimer(Syllabifier()).split(word, span, tokens, "en", True, 0.1)
        assert [(p.text, p.begin, p.end) for p in pieces] == [
            ("beau", 1.0, 2.5), ("ti", 2.5, 3.5), ("ful ", 3.5, 5.0)]


class TestTimingJudge:
    def test_agreement_and_a_clear_hearing_make_a_word_trusted(self):
        from autolyrics.infrastructure.services.ml.singing.timing_judge import (
            TimingJudge,
            WordEvidence,
        )

        judge = TimingJudge()
        sure = WordEvidence(score=0.6, disagreement=0.0, outside_window=0.0, voiced_start=True,
                            duration_ratio=1.0)
        guess = WordEvidence(score=0.01, disagreement=2.5, outside_window=2.0,
                             voiced_start=False, duration_ratio=6.0)
        assert judge.probability(sure) > TimingJudge.UNSURE > judge.probability(guess)


class TestVocalAnalyzer:
    def test_short_unvoiced_gaps_inside_singing_are_closed(self):
        import numpy as np

        from autolyrics.infrastructure.services.ml.singing.vocal_analyzer import VocalAnalyzer

        voiced = np.array([0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1], dtype=bool)
        closed = VocalAnalyzer._close_gaps(voiced, 3)
        assert closed.tolist() == [0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1]

    def test_a_voice_holds_until_it_stops(self):
        import numpy as np

        from autolyrics.infrastructure.services.ml.singing.vocal_analyzer import VocalEvents

        voiced = np.zeros(100, dtype=bool)
        voiced[10:60] = True
        events = VocalEvents(0.1, voiced, np.zeros(100), np.zeros(100))
        assert events.voiced_until(2.0, limit=9.0) == 6.0
        assert events.voiced_until(2.0, limit=4.0) == 4.0
        assert events.voiced_until(7.0, limit=9.0) == 7.0


class TestRepeatMemory:
    @staticmethod
    def _line(start: float, confidence: float, gaps=(0.0, 0.5, 1.0)):
        from autolyrics.domain.lyrics import Line, Word

        return Line(words=[Word(text=t, begin=start + g, end=start + g + 0.4,
                                confidence=confidence)
                           for t, g in zip(("Hands ", "go ", "higher"), gaps, strict=True)])

    def test_a_doubtful_repeat_borrows_the_trusted_rhythm(self):
        from autolyrics.infrastructure.services.ml.singing.repeat_memory import RepeatMemory

        lines = [self._line(10.0, 0.99), self._line(30.0, 0.99),
                 self._line(50.0, 0.5, gaps=(0.0, 1.7, 1.9))]
        lines[2].words[0].confidence = 0.98  # its surest word anchors it
        changed = RepeatMemory().apply(lines)
        assert changed == {(2, 0), (2, 1), (2, 2)}
        assert [w.begin for w in lines[2].words] == [50.0, 50.5, 51.0]
        assert "from-repeat" in lines[2].words[1].flags

    def test_repeats_that_disagree_lend_nothing(self):
        from autolyrics.infrastructure.services.ml.singing.repeat_memory import RepeatMemory

        lines = [self._line(10.0, 0.99), self._line(30.0, 0.99, gaps=(0.0, 1.0, 2.0)),
                 self._line(50.0, 0.5)]
        assert RepeatMemory().apply(lines) == set()


class TestRoformerStemNames:
    def test_the_last_bracket_names_the_stem(self):
        from pathlib import Path

        from autolyrics.infrastructure.services.ml.roformer_separator import RoformerVocalSeparator

        files = [Path("1-vocals_(Instrumental)_karaoke.wav"), Path("1-vocals_(Vocals)_karaoke.wav")]
        assert RoformerVocalSeparator._stem(files, "vocals").name == "1-vocals_(Vocals)_karaoke.wav"
        assert RoformerVocalSeparator._stem(files, "instrumental") == files[0]


class TestOptionalBlocks:
    def test_background_words_sung_after_the_line_are_placed_there(self):
        em = emissions(40, {A: [5], B: [12], GAP: [20]})
        line = SolverLine([[A], [B]], optional_from=1)
        spans = GlobalCtcSolver().solve(em, [line], word_gap=None, line_gap=None)
        assert [(s.word, round(s.begin, 1)) for s in spans] == [(0, 0.5), (1, 1.2)]

    def test_a_block_the_audio_lacks_is_skipped_whole(self):
        # Line 1 "A", optional "B B" (not sung), line 2 "A": the second A must not be eaten.
        em = emissions(40, {A: [5, 25]})
        lines = [SolverLine([[A], [B, B]], optional_from=1), SolverLine([[A]])]
        spans = GlobalCtcSolver().solve(em, lines, word_gap=None, line_gap=None)
        assert [(s.line, s.word, round(s.begin, 1)) for s in spans] == [(0, 0, 0.5), (1, 0, 2.5)]
