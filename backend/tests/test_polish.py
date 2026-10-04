import pytest

from autolyrics.formats.plain import parse_plain
from autolyrics.model import Line, Lyrics, Word
from autolyrics.polish import (
    apply_answer,
    build_prompt,
    find_decisions,
    group_sources,
    parse_json_reply,
)
from autolyrics.validate import check_lyrics

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


def decisions_for(chosen_text=CHOSEN, others=(("LRCLIB", OTHER), ("Genius", OTHER))):
    chosen = parse_plain(chosen_text)
    sources = group_sources(chosen, [(label, parse_plain(text)) for label, text in others])
    return chosen, sources, find_decisions(chosen, sources)


def test_group_sources_merges_identical_copies():
    _, sources, _ = decisions_for(others=(("LRCLIB", OTHER), ("LRCLIB", OTHER), ("QQ", OTHER)))
    assert [s.label for s in sources] == ["LRCLIB ×2 + QQ"]


def test_group_sources_skips_unrelated_structure():
    _, sources, _ = decisions_for(others=(("Other song", "La la la\nNa na na\nYeah yeah"),))
    assert sources == []


def test_find_decisions_variants_and_insertions():
    _, _, d = decisions_for()
    assert len(d.variants) == 1
    v = d.variants[0]
    assert v.line == 1
    assert v.options == ["Keine Kappe drauf, Feinsteinjacken", "Keine Couple-Goals, Wellensteyn-Jacken"]
    assert d.insertions[0].after == 1
    assert d.insertions[0].text == "SSIO, das ist ein Ding"
    assert "Wellensteyn-Jacken" in d.vocabulary


def test_prompt_lists_everything():
    _, _, d = decisions_for()
    prompt = build_prompt(d, "Song", ["SSIO"])
    assert "V1 – line 1:" in prompt
    assert "I1 – after line 1: SSIO, das ist ein Ding" in prompt
    assert "3: Lyrics by: Someone" in prompt


def test_apply_answer_on_untimed_lyrics():
    chosen, _, d = decisions_for()
    answer = {
        "language": "de",
        "variants": [{"id": "V1", "choice": 1, "reason": "brand name"}],
        "insertions": [{"id": "I1", "accept": True}],
        "remove_lines": [{"line": 3, "reason": "credit"}],
        "spelling": [{"from": "Ciao", "to": "Tschau"}],  # invented: no source writes it
        "notes": [{"line": 2, "note": "check"}],
    }
    changes = apply_answer(chosen, d, answer, word_synced=False)
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


def test_apply_answer_rejects_bad_choices_and_mass_removal():
    chosen, _, d = decisions_for()
    answer = {"variants": [{"id": "V1", "choice": 7}, {"id": "V9", "choice": 1}],
              "remove_lines": [{"line": i} for i in range(4)]}
    changes = apply_answer(chosen, d, answer, word_synced=False)
    assert len(chosen.lines) == 5
    assert [c["kind"] for c in changes].count("rejected") == 3


def timed_line(*spec):
    return Line(words=[Word(text=t, begin=b, end=e) for t, b, e in spec])


def test_variant_on_word_synced_line_keeps_or_spreads_times():
    lyrics = Lyrics(lines=[timed_line(("Keine ", 1.0, 1.5), ("Kappe ", 1.5, 2.0), ("drauf", 2.0, 3.0)),
                           timed_line(("Hallo ", 4.0, 4.5), ("du", 4.5, 5.0))])
    other = Lyrics(lines=[Line(words=parse_plain("Keine Couple-Goals drauf").lines[0].words),
                          Line(words=parse_plain("Hallo du da").lines[0].words)])
    sources = group_sources(lyrics, [("LRCLIB", other)])
    d = find_decisions(lyrics, sources)
    answer = {"variants": [{"id": f"V{k}", "choice": 1} for k in range(1, len(d.variants) + 1)],
              "insertions": [{"id": "I1", "accept": True}]}
    apply_answer(lyrics, d, answer, word_synced=True)
    same_count = lyrics.lines[0].words
    assert [w.text for w in same_count] == ["Keine ", "Couple-Goals ", "drauf"]
    assert (same_count[1].begin, same_count[1].end) == (1.5, 2.0)
    spread = lyrics.lines[1].words
    assert [w.text.strip() for w in spread] == ["Hallo", "du", "da"]
    assert spread[0].begin == 4.0
    assert spread[-1].end == pytest.approx(5.0)
    assert "interpolated" in spread[1].flags


def test_parse_json_reply_tolerates_fences():
    assert parse_json_reply('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json_reply("no json here")


def test_check_lyrics_flags_problems():
    lyrics = Lyrics(lines=[
        timed_line(("long ", 10.0, 17.0), ("next ", 16.5, 17.5), ("far", 30.0, 30.5)),
        timed_line(("early", 2.0, 2.5)),
    ])
    report = check_lyrics(lyrics, duration=20.0)
    assert report["by_issue"] == {"too-long": 1, "overlap": 1, "big-gap": 1, "past-end": 1,
                                  "out-of-order": 1}
    assert "too-long" in lyrics.lines[0].words[0].flags


def test_line_break_variants_are_not_offered():
    from autolyrics.polish import is_line_break_variant

    current = ["Glück nicht verwechseln mit Könn'n", "Aber dein Könn'n niemals anzweifeln",
               "Denn nur mit Blut, Schweiß und Trän'n bezahlt man die Unendlichkeit"]
    joined = "Glück nicht verwechseln mit Könn'n, aber dein Könn'n niemals anzweifeln"
    assert is_line_break_variant(current, 0, joined)
    assert is_line_break_variant(current, 1, joined)
    assert is_line_break_variant(current, 2, "Bezahlt man die Unendlichkeit")
    assert not is_line_break_variant(current, 0, "Glück nicht verwechseln mit Können")
    assert not is_line_break_variant(current, 1, "Aber dein Können niemals anzweifeln")
