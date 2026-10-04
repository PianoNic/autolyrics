"""Final text touches with an LLM (DeepSeek), constrained to choosing between real options.

Code finds the decisions (where the lyrics sources disagree, lines one source lacks, lines that
are not lyrics) and DeepSeek picks. Every answer is validated before it is applied: a choice must
index an offered option, a spelling must appear in some source's text, and timings are never part
of the exchange. Each applied change lands in the report.
"""

import difflib
import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from autolyrics.config import settings
from autolyrics.formats.plain import split_background
from autolyrics.model import Line, Lyrics, Word, tokenize

log = logging.getLogger(__name__)

SIMILAR = 0.6  # lines at least this similar are versions of one another
MAX_VARIANTS = 3
MAX_REMOVED_SHARE = 0.25


def norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


@dataclass
class Source:
    label: str
    lines: list[str]  # display text per line, background in parentheses


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


def line_display(line: Line) -> str:
    if line.background:
        # Apple-style background words carry their own parentheses: "(Ooh-ooh," ... "up)".
        inner = line.background_text.strip()
        if inner.startswith("(") and inner.endswith(")"):
            inner = inner[1:-1]
        return f"{line.text} ({inner})".strip()
    return line.text


def source_lines(lyrics: Lyrics) -> list[str]:
    return [line_display(line) for line in lyrics.lines if line.words or line.background]


# -- finding the decisions ----------------------------------------------------

MIN_STRUCTURE_MATCH = 0.5  # sources whose lines line up worse than this are not compared


def structure_match(a: list[str], b: list[str]) -> float:
    """Share of lines in `a` that have a similar line in `b`: high for another transcription of
    the same song, low for a source that breaks the lines differently or is another song."""
    if not a:
        return 0.0
    hits = 0
    for line in a:
        for other in b:
            m = difflib.SequenceMatcher(a=line, b=other)
            if m.real_quick_ratio() >= SIMILAR and m.quick_ratio() >= SIMILAR and m.ratio() >= SIMILAR:
                hits += 1
                break
    return hits / len(a)


def group_sources(chosen: Lyrics, others: list[tuple[str, Lyrics]]) -> list[Source]:
    """One Source per distinct text, so twelve LRCLIB copies of one transcription count once
    (labelled "LRCLIB ×12"), and only sources whose lines line up with the chosen lyrics."""
    chosen_norm = [norm(t) for t in source_lines(chosen)]
    grouped: dict[tuple[str, ...], list[str]] = {}
    texts: dict[tuple[str, ...], list[str]] = {}
    for label, lyrics in others:
        lines = source_lines(lyrics)
        key = tuple(norm(t) for t in lines)
        if key == tuple(chosen_norm):
            continue
        if structure_match(chosen_norm, list(key)) < MIN_STRUCTURE_MATCH:
            continue
        grouped.setdefault(key, []).append(label)
        texts.setdefault(key, lines)
    out = []
    for key, labels in grouped.items():
        names = sorted(set(labels))
        label = " + ".join(f"{n} ×{labels.count(n)}" if labels.count(n) > 1 else n for n in names)
        out.append(Source(label, texts[key]))
    return out



def find_decisions(chosen: Lyrics, others: list[Source]) -> Decisions:
    current = source_lines(chosen)
    decisions = Decisions(current=current)
    vocabulary = {w for text in current for w in _words(text)}

    variant_map: dict[int, dict[str, list[str]]] = {}
    insert_map: dict[tuple[int, str], tuple[str, set[str]]] = {}

    cur_norm = [norm(t) for t in current]
    for source in others:
        vocabulary |= {w for text in source.lines for w in _words(text)}
        src_norm = [norm(t) for t in source.lines]
        matcher = difflib.SequenceMatcher(a=cur_norm, b=src_norm, autojunk=False)
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "replace":
                _pair_replaced(current, source, i1, i2, j1, j2, variant_map, insert_map)
            elif op == "insert":
                for j in range(j1, j2):
                    _add_insertion(insert_map, i1 - 1, source.lines[j], source.label)

    for i, by_text in sorted(variant_map.items()):
        options = [current[i]]
        supporters = [["chosen"]]
        real = {t: labels for t, labels in by_text.items() if not is_line_break_variant(current, i, t)}
        if not real:
            continue
        for text, labels in sorted(real.items(), key=lambda kv: -len(kv[1]))[:MAX_VARIANTS]:
            options.append(text)
            supporters.append(sorted(set(labels)))
        decisions.variants.append(Variant(i, options, supporters))

    # One odd transcription is not evidence of a dropped line; ask for agreement when there are
    # enough independent versions to agree.
    min_support = 2 if len(others) >= 3 else 1
    for (after, _), (text, labels) in sorted(insert_map.items()):
        if len(labels) >= min_support:
            decisions.insertions.append(Insertion(after, text, sorted(labels)))
    decisions.vocabulary = vocabulary
    return decisions


def is_line_break_variant(current: list[str], i: int, option: str) -> bool:
    """True when `option` differs from line i only in where the lines break: the line joined
    with a neighbour, or a fragment of it. Those are formatting, not text, decisions."""
    def letters(text: str) -> str:
        return re.sub(r"[^\w]", "", text.lower())

    here, opt = letters(current[i]), letters(option)
    if not here or not opt or here == opt:
        return False
    neighbours = []
    if i + 1 < len(current):
        neighbours.append(here + letters(current[i + 1]))
    if i > 0:
        neighbours.append(letters(current[i - 1]) + here)
    if opt in neighbours:
        return True
    # A fragment of the line ("Bezahlt man die Unendlichkeit"): that source breaks lines elsewhere.
    # A longer option is only formatting when it is the join with a neighbour (above); otherwise
    # it may be words the chosen version dropped.
    return len(opt) < 0.8 * len(here) and (here.startswith(opt) or here.endswith(opt))


def _pair_replaced(current, source, i1, i2, j1, j2, variant_map, insert_map) -> None:
    """Inside a replaced block, pair each source line with the most similar chosen line;
    unpaired source lines are candidate insertions."""
    used: set[int] = set()
    for j in range(j1, j2):
        best_i, best = None, 0.0
        for i in range(i1, i2):
            ratio = difflib.SequenceMatcher(a=norm(current[i]), b=norm(source.lines[j])).ratio()
            if ratio > best:
                best_i, best = i, ratio
        if best_i is not None and best >= SIMILAR:
            if norm(current[best_i]) != norm(source.lines[j]):
                variant_map.setdefault(best_i, {}).setdefault(source.lines[j], []).append(
                    source.label)
            used.add(best_i)
        else:
            anchor = max([i for i in used] + [i1 - 1])
            _add_insertion(insert_map, anchor, source.lines[j], source.label)


def _add_insertion(insert_map, after: int, text: str, label: str) -> None:
    key = (after, norm(text))
    if not key[1]:
        return
    entry = insert_map.setdefault(key, (text, set()))
    entry[1].add(label)


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text) if w]


# -- talking to DeepSeek ------------------------------------------------------

SYSTEM = """You clean up song lyrics for a synced-lyrics file. You never write lyrics yourself:
you only choose between versions that real lyrics sources wrote, and you answer with JSON only.

Rules:
- For each variant, pick the option that is most likely what is actually sung on this recording.
  Answer 0 to keep the current text, which is the default: only switch when the current text has a
  genuinely different or misspelled word (a misheard word, a wrong brand or name, a typo).
- Keep the current text's style. Do not switch for contractions or dropped letters ("feelin'" vs
  "feeling", "komm'n" vs "kommen"), capitalisation, punctuation, or where lines break; word-synced
  sources deliberately write what is sung. Never move words between the main line and the
  background vocals in parentheses.
- Many sources copy one another, so agreement counts for less than a clearly better word.
- For each missing-line candidate, accept it only if it is clearly a real sung line that the chosen
  version dropped (more supporting sources make that more likely). Never accept section labels.
- List lines of the current lyrics that are not sung lyrics at all: credits ("Lyrics by", "Produced
  by"), section labels ("[Chorus]", "Hook:"), "Instrumental", translations. Do not remove real
  lyrics, ad-libs or repeated lines.
- Spelling: only propose a replacement when the same word is spelled inconsistently within the
  lyrics or the sources; "to" must be a spelling that appears in the sources.
- language: the main language of the lyrics as an ISO 639-1 code.
- notes: short warnings about lines a human should double-check (max 10)."""

SCHEMA = """{
  "language": "de",
  "variants": [{"id": "V1", "choice": 0, "reason": "..."}],
  "insertions": [{"id": "I1", "accept": false, "reason": "..."}],
  "remove_lines": [{"line": 12, "reason": "..."}],
  "spelling": [{"from": "S-S-I-O", "to": "SSIO", "reason": "..."}],
  "notes": [{"line": 3, "note": "..."}]
}"""


def build_prompt(decisions: Decisions, title: str, artists: list[str],
                 current_source: str = "") -> str:
    parts = [f"Song: {', '.join(artists)} – {title}"]
    if current_source:
        parts.append(f"The current lyrics come from: {current_source}")
    parts += ["", "Current lyrics (line number: text):"]
    parts += [f"{i}: {text}" for i, text in enumerate(decisions.current)]
    if decisions.variants:
        parts += ["", "Variants (other sources wrote these lines differently):"]
        for k, v in enumerate(decisions.variants, 1):
            parts.append(f"V{k} – line {v.line}:")
            for n, (text, who) in enumerate(zip(v.options, v.supporters, strict=True)):
                parts.append(f"  {n}: {text}   [{', '.join(who)}]")
    if decisions.insertions:
        parts += ["", "Missing-line candidates (other sources have these, the current lyrics do not):"]
        for k, ins in enumerate(decisions.insertions, 1):
            where = "before line 0" if ins.after < 0 else f"after line {ins.after}"
            parts.append(f"I{k} – {where}: {ins.text}   [{', '.join(ins.supporters)}]")
    parts += ["", "Answer with JSON in exactly this shape:", SCHEMA]
    return "\n".join(parts)


async def ask_llm(prompt: str, client: httpx.AsyncClient) -> dict:
    if not settings.llm_api_key:
        raise RuntimeError("no LLM API key configured (AGENT_API_KEY)")
    response = await client.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
        },
        timeout=180,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"] or ""
    return parse_json_reply(content)


def parse_json_reply(content: str) -> dict:
    """Models sometimes wrap JSON in a code fence or add a sentence; take the outermost object."""
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM reply contains no JSON object")
    return json.loads(content[start:end + 1])


# -- applying the answer ------------------------------------------------------


def apply_answer(lyrics: Lyrics, decisions: Decisions, answer: dict,
                 word_synced: bool) -> list[dict]:
    """Apply validated decisions in place and return the change log. Invalid entries are skipped
    and logged as rejected."""
    changes: list[dict] = []
    lines = [line for line in lyrics.lines if line.words or line.background]
    if len(lines) != len(decisions.current):
        raise ValueError("lyrics changed since the decisions were built")

    language = answer.get("language")
    if isinstance(language, str) and re.fullmatch(r"[a-z]{2}", language):
        if lyrics.metadata.language != language:
            changes.append({"kind": "language", "to": language})
        lyrics.metadata.language = language

    variants = {f"V{k}": v for k, v in enumerate(decisions.variants, 1)}
    for item in answer.get("variants") or []:
        v = variants.get(str(item.get("id")))
        choice = item.get("choice")
        if v is None or not isinstance(choice, int) or not 0 <= choice < len(v.options):
            changes.append({"kind": "rejected", "item": item, "why": "unknown variant or choice"})
            continue
        if choice == 0:
            continue
        line = lines[v.line]
        before = line_display(line)
        replace_line_text(line, v.options[choice], word_synced)
        changes.append({"kind": "variant", "line": v.line, "from": before,
                        "to": v.options[choice], "sources": v.supporters[choice],
                        "reason": item.get("reason")})

    for item in answer.get("spelling") or []:
        src, dst = str(item.get("from") or ""), str(item.get("to") or "")
        if not src or not dst or src == dst or " " in src or " " in dst:
            continue
        if dst not in decisions.vocabulary and dst.lower() not in {
                v.lower() for v in decisions.vocabulary}:
            changes.append({"kind": "rejected", "item": item, "why": "spelling not in any source"})
            continue
        count = respell(lines, src, dst)
        if count:
            changes.append({"kind": "spelling", "from": src, "to": dst, "count": count,
                            "reason": item.get("reason")})

    removals = set()
    for item in answer.get("remove_lines") or []:
        idx = item.get("line")
        if isinstance(idx, int) and 0 <= idx < len(lines):
            removals.add(idx)
    if len(removals) > MAX_REMOVED_SHARE * len(lines):
        changes.append({"kind": "rejected", "item": sorted(removals),
                        "why": "too many lines marked for removal"})
        removals = set()

    insertions = {f"I{k}": ins for k, ins in enumerate(decisions.insertions, 1)}
    accepted: list[Insertion] = []
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

    for idx in sorted(removals):
        changes.append({"kind": "remove", "line": idx, "text": line_display(lines[idx])})

    _rebuild(lyrics, lines, removals, accepted)

    for item in (answer.get("notes") or [])[:10]:
        idx, note = item.get("line"), item.get("note")
        if isinstance(idx, int) and 0 <= idx < len(lines) and note and idx not in removals:
            changes.append({"kind": "note", "line": idx, "note": str(note)})
            for w in lines[idx].words:
                if "llm-note" not in w.flags:
                    w.flags.append("llm-note")
    return changes


def replace_line_text(line: Line, display: str, word_synced: bool) -> None:
    """Give a line new text. Untimed lines just re-tokenise. A word-synced line keeps its times
    when the word count matches, and otherwise spreads the new words over the line's span."""
    main, background = split_background(display)
    if not word_synced:
        line.words, line.background = main, background
        return
    for old, new in ((line.words, main), (line.background, background)):
        _retime(old, new)
    line.words, line.background = main, background


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
    weights = [max(1, len(n.text.strip())) for n in new]
    t = begin
    for n, weight in zip(new, weights, strict=True):
        n.begin, n.end = t, t + (end - begin) * weight / sum(weights)
        t = n.end
        n.flags = ["llm-edit", "interpolated"]


def respell(lines: list[Line], src: str, dst: str) -> int:
    count = 0
    for line in lines:
        for w in line.all_words:
            core = w.text.rstrip()
            stripped = core.strip(".,!?;:\"'")
            if stripped.lower() == src.lower() and stripped != dst:
                w.text = w.text.replace(stripped, dst, 1)
                if "llm-edit" not in w.flags:
                    w.flags.append("llm-edit")
                count += 1
    return count


def _rebuild(lyrics: Lyrics, lines: list[Line], removals: set[int],
             insertions: list[Insertion]) -> None:
    by_anchor: dict[int, list[Line]] = {}
    for ins in insertions:
        main, background = split_background(ins.text)
        new = Line(words=main or tokenize(ins.text), background=background)
        for w in new.all_words:
            w.flags.append("llm-insert")
        by_anchor.setdefault(ins.after, []).append(new)
    out = list(by_anchor.get(-1, []))
    for i, line in enumerate(lines):
        if i not in removals:
            out.append(line)
        out.extend(by_anchor.get(i, []))
    lyrics.lines = out
