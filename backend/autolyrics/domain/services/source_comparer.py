import difflib
import re
from dataclasses import dataclass, field

from autolyrics.domain.lyrics import Lyrics


@dataclass
class SourceVersion:
    """Another source's text of the song: display text per line, background in parentheses."""

    label: str
    lines: list[str]


@dataclass
class Variant:
    line: int
    options: list[str]  # option 0 is the current text
    supporters: list[list[str]]  # which sources wrote each option


@dataclass
class Insertion:
    after: int  # index into the chosen lines; -1 = before the first line
    text: str
    supporters: list[str]


@dataclass
class Decisions:
    current: list[str]
    variants: list[Variant] = field(default_factory=list)
    insertions: list[Insertion] = field(default_factory=list)
    vocabulary: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.variants and not self.insertions


class TextKey:
    """Comparison keys that ignore case and punctuation."""

    @staticmethod
    def words(text: str) -> str:
        return re.sub(r"[^\w]+", " ", text.lower()).strip()

    @staticmethod
    def letters(text: str) -> str:
        return re.sub(r"[^\w]", "", text.lower())


class SourceComparer:
    """Cross-checks the chosen lyrics against every other source and finds the decisions a
    reviewer (DeepSeek) has to make: line variants and lines the chosen version lacks."""

    def __init__(self, similar: float = 0.6, max_variants: int = 3,
                 min_structure_match: float = 0.5):
        self._similar = similar  # lines at least this similar are versions of one another
        self._max_variants = max_variants
        self._min_structure = min_structure_match

    @staticmethod
    def lines_of(lyrics: Lyrics) -> list[str]:
        return [line.display for line in lyrics.content_lines]

    def group(self, chosen: Lyrics, others: list[tuple[str, Lyrics]]) -> list[SourceVersion]:
        """One version per distinct text, so twelve LRCLIB copies of one transcription count
        once ("LRCLIB ×12"), and only sources whose lines line up with the chosen lyrics."""
        chosen_keys = [TextKey.words(t) for t in self.lines_of(chosen)]
        grouped: dict[tuple[str, ...], list[str]] = {}
        texts: dict[tuple[str, ...], list[str]] = {}
        for label, lyrics in others:
            lines = self.lines_of(lyrics)
            key = tuple(TextKey.words(t) for t in lines)
            if key == tuple(chosen_keys):
                continue
            if self.structure_match(chosen_keys, list(key)) < self._min_structure:
                continue
            grouped.setdefault(key, []).append(label)
            texts.setdefault(key, lines)
        versions = []
        for key, labels in grouped.items():
            names = sorted(set(labels))
            label = " + ".join(f"{n} ×{labels.count(n)}" if labels.count(n) > 1 else n
                               for n in names)
            versions.append(SourceVersion(label, texts[key]))
        return versions

    def structure_match(self, a: list[str], b: list[str]) -> float:
        """Share of lines in `a` with a similar line in `b`: high for another transcription of
        the same song, low for a source that breaks lines differently or is another song."""
        if not a:
            return 0.0
        hits = 0
        for line in a:
            for other in b:
                m = difflib.SequenceMatcher(a=line, b=other)
                if (m.real_quick_ratio() >= self._similar and m.quick_ratio() >= self._similar
                        and m.ratio() >= self._similar):
                    hits += 1
                    break
        return hits / len(a)

    def decisions(self, chosen: Lyrics, others: list[SourceVersion]) -> Decisions:
        current = self.lines_of(chosen)
        decisions = Decisions(current=current)
        vocabulary = {w for text in current for w in text.split()}
        variant_map: dict[int, dict[str, list[str]]] = {}
        insert_map: dict[tuple[int, str], tuple[str, set[str]]] = {}

        current_keys = [TextKey.words(t) for t in current]
        for source in others:
            vocabulary |= {w for text in source.lines for w in text.split()}
            source_keys = [TextKey.words(t) for t in source.lines]
            matcher = difflib.SequenceMatcher(a=current_keys, b=source_keys, autojunk=False)
            for op, i1, i2, j1, j2 in matcher.get_opcodes():
                if op == "replace":
                    self._pair_replaced(current, source, (i1, i2), (j1, j2), variant_map,
                                        insert_map)
                elif op == "insert":
                    for j in range(j1, j2):
                        self._add_insertion(insert_map, i1 - 1, source.lines[j], source.label)

        for i, by_text in sorted(variant_map.items()):
            real = {t: labels for t, labels in by_text.items()
                    if not self.is_line_break_variant(current, i, t)}
            if not real:
                continue
            options, supporters = [current[i]], [["chosen"]]
            for text, labels in sorted(real.items(), key=lambda kv: -len(kv[1]))[:self._max_variants]:
                options.append(text)
                supporters.append(sorted(set(labels)))
            decisions.variants.append(Variant(i, options, supporters))

        # One odd transcription is not evidence of a dropped line; ask for agreement when there
        # are enough independent versions to agree.
        min_support = 2 if len(others) >= 3 else 1
        for (after, _), (text, labels) in sorted(insert_map.items()):
            if len(labels) >= min_support:
                decisions.insertions.append(Insertion(after, text, sorted(labels)))
        decisions.vocabulary = vocabulary
        return decisions

    @staticmethod
    def is_line_break_variant(current: list[str], i: int, option: str) -> bool:
        """True when `option` differs from line i only in where the lines break: the line joined
        with a neighbour, or a fragment of it. Those are formatting, not text, decisions."""
        here, opt = TextKey.letters(current[i]), TextKey.letters(option)
        if not here or not opt or here == opt:
            return False
        neighbours = []
        if i + 1 < len(current):
            neighbours.append(here + TextKey.letters(current[i + 1]))
        if i > 0:
            neighbours.append(TextKey.letters(current[i - 1]) + here)
        if opt in neighbours:
            return True
        # A fragment of the line: that source breaks lines elsewhere. A longer option is only
        # formatting when it is the join with a neighbour (above); otherwise it may be words the
        # chosen version dropped.
        return len(opt) < 0.8 * len(here) and (here.startswith(opt) or here.endswith(opt))

    def _pair_replaced(self, current: list[str], source: SourceVersion, chosen_range: tuple,
                       source_range: tuple, variant_map: dict, insert_map: dict) -> None:
        """Inside a replaced block, pair each source line with the most similar chosen line;
        unpaired source lines are candidate insertions."""
        i1, i2 = chosen_range
        used: set[int] = set()
        for j in range(*source_range):
            best_i, best = None, 0.0
            for i in range(i1, i2):
                ratio = difflib.SequenceMatcher(a=TextKey.words(current[i]),
                                                b=TextKey.words(source.lines[j])).ratio()
                if ratio > best:
                    best_i, best = i, ratio
            if best_i is not None and best >= self._similar:
                if TextKey.words(current[best_i]) != TextKey.words(source.lines[j]):
                    variant_map.setdefault(best_i, {}).setdefault(source.lines[j], []).append(
                        source.label)
                used.add(best_i)
            else:
                self._add_insertion(insert_map, max([*used, i1 - 1]), source.lines[j],
                                    source.label)

    @staticmethod
    def _add_insertion(insert_map: dict, after: int, text: str, label: str) -> None:
        key = (after, TextKey.words(text))
        if not key[1]:
            return
        insert_map.setdefault(key, (text, set()))[1].add(label)
