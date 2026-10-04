import re

from autolyrics.domain.lyrics import Line, Lyrics, Word
from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.domain.services.source_comparer import Decisions, Insertion
from autolyrics.domain.services.timing_repairer import TimingRepairer


class DecisionApplier:
    """Applies a reviewer's answer to the decisions, validating every entry first: a choice must
    index an offered option, a spelling must appear in some source's text, removals are capped.
    Invalid entries are skipped and logged as rejected. Timings are never taken from the answer."""

    MAX_NOTES = 10

    def __init__(self, splitter: BackgroundSplitter, max_removed_share: float = 0.25):
        self._splitter = splitter
        self._max_removed_share = max_removed_share

    def apply(self, lyrics: Lyrics, decisions: Decisions, answer: dict,
              word_synced: bool) -> list[dict]:
        changes: list[dict] = []
        lines = lyrics.content_lines
        if len(lines) != len(decisions.current):
            raise ValueError("lyrics changed since the decisions were built")

        self._apply_language(lyrics, answer, changes)
        self._apply_variants(lines, decisions, answer, word_synced, changes)
        self._apply_spelling(lines, decisions, answer, changes)
        removals = self._removals(lines, answer, changes)
        accepted = self._insertions(decisions, answer, word_synced, changes)
        for idx in sorted(removals):
            changes.append({"kind": "remove", "line": idx, "text": lines[idx].display})
        self._rebuild(lyrics, lines, removals, accepted)
        self._apply_notes(lines, removals, answer, changes)
        return changes

    @staticmethod
    def _apply_language(lyrics: Lyrics, answer: dict, changes: list[dict]) -> None:
        language = answer.get("language")
        if isinstance(language, str) and re.fullmatch(r"[a-z]{2}", language):
            if lyrics.metadata.language != language:
                changes.append({"kind": "language", "to": language})
            lyrics.metadata.language = language

    def _apply_variants(self, lines: list[Line], decisions: Decisions, answer: dict,
                        word_synced: bool, changes: list[dict]) -> None:
        variants = {f"V{k}": v for k, v in enumerate(decisions.variants, 1)}
        for item in answer.get("variants") or []:
            v = variants.get(str(item.get("id")))
            choice = item.get("choice")
            if v is None or not isinstance(choice, int) or not 0 <= choice < len(v.options):
                changes.append({"kind": "rejected", "item": item,
                                "why": "unknown variant or choice"})
                continue
            if choice == 0:
                continue
            line = lines[v.line]
            before = line.display
            self.replace_text(line, v.options[choice], word_synced)
            changes.append({"kind": "variant", "line": v.line, "from": before,
                            "to": v.options[choice], "sources": v.supporters[choice],
                            "reason": item.get("reason")})

    def _apply_spelling(self, lines: list[Line], decisions: Decisions, answer: dict,
                        changes: list[dict]) -> None:
        known = {v.lower() for v in decisions.vocabulary}
        for item in answer.get("spelling") or []:
            src, dst = str(item.get("from") or ""), str(item.get("to") or "")
            if not src or not dst or src == dst or " " in src or " " in dst:
                continue
            if dst not in decisions.vocabulary and dst.lower() not in known:
                changes.append({"kind": "rejected", "item": item,
                                "why": "spelling not in any source"})
                continue
            count = self.respell(lines, src, dst)
            if count:
                changes.append({"kind": "spelling", "from": src, "to": dst, "count": count,
                                "reason": item.get("reason")})

    def _removals(self, lines: list[Line], answer: dict, changes: list[dict]) -> set[int]:
        removals = {item.get("line") for item in answer.get("remove_lines") or []
                    if isinstance(item.get("line"), int) and 0 <= item["line"] < len(lines)}
        if len(removals) > self._max_removed_share * len(lines):
            changes.append({"kind": "rejected", "item": sorted(removals),
                            "why": "too many lines marked for removal"})
            return set()
        return removals

    @staticmethod
    def _insertions(decisions: Decisions, answer: dict, word_synced: bool,
                    changes: list[dict]) -> list[Insertion]:
        insertions = {f"I{k}": ins for k, ins in enumerate(decisions.insertions, 1)}
        accepted = []
        for item in answer.get("insertions") or []:
            ins = insertions.get(str(item.get("id")))
            if ins is None or item.get("accept") is not True:
                continue
            if word_synced:
                changes.append({"kind": "rejected", "item": item,
                                "why": "the source's own timing has no slot for an added line"})
                continue
            accepted.append(ins)
            changes.append({"kind": "insert", "after": ins.after, "text": ins.text,
                            "sources": ins.supporters, "reason": item.get("reason")})
        return accepted

    def _apply_notes(self, lines: list[Line], removals: set[int], answer: dict,
                     changes: list[dict]) -> None:
        for item in (answer.get("notes") or [])[:self.MAX_NOTES]:
            idx, note = item.get("line"), item.get("note")
            if isinstance(idx, int) and 0 <= idx < len(lines) and note and idx not in removals:
                changes.append({"kind": "note", "line": idx, "note": str(note)})
                for w in lines[idx].words:
                    w.flag("llm-note")

    def replace_text(self, line: Line, display: str, word_synced: bool) -> None:
        """Give a line new text. Untimed lines just re-tokenise. A word-synced line keeps its
        times when the word count matches, and otherwise spreads the new words over its span."""
        main, background = self._splitter.split(display)
        if word_synced:
            self._retime(line.words, main)
            self._retime(line.background, background)
        line.words, line.background = main, background

    @staticmethod
    def _retime(old: list[Word], new: list[Word]) -> None:
        timed = [w for w in old if w.timed]
        if not new or not timed:
            return
        if len(old) == len(new):
            for o, n in zip(old, new, strict=True):
                n.begin, n.end, n.confidence = o.begin, o.end, o.confidence
                n.flags = [*o.flags, "llm-edit"]
            return
        begin, end = timed[0].begin, timed[-1].end
        TimingRepairer.spread(new, begin, end - begin, "llm-edit", "interpolated")

    @staticmethod
    def respell(lines: list[Line], src: str, dst: str) -> int:
        count = 0
        for line in lines:
            for w in line.all_words:
                stripped = w.text.rstrip().strip(".,!?;:\"'")
                if stripped.lower() == src.lower() and stripped != dst:
                    w.text = w.text.replace(stripped, dst, 1)
                    w.flag("llm-edit")
                    count += 1
        return count

    def _rebuild(self, lyrics: Lyrics, lines: list[Line], removals: set[int],
                 insertions: list[Insertion]) -> None:
        by_anchor: dict[int, list[Line]] = {}
        for ins in insertions:
            main, background = self._splitter.split(ins.text)
            new = Line(words=main or Word.tokenize(ins.text), background=background)
            for w in new.all_words:
                w.flag("llm-insert")
            by_anchor.setdefault(ins.after, []).append(new)
        out = list(by_anchor.get(-1, []))
        for i, line in enumerate(lines):
            if i not in removals:
                out.append(line)
            out.extend(by_anchor.get(i, []))
        lyrics.lines = out
