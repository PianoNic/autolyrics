from autolyrics.domain.services.source_comparer import Decisions


class PolishPrompt:
    """The instructions and question for the LLM that reviews the lyrics text."""

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
- "Whisper (machine transcription)" is not a lyrics source: it is what a speech recogniser heard
  in this recording, often misspelled or misheard. Never prefer its spelling or wording over a
  lyrics source. Use it only as evidence that something is sung: accept a variant from it only
  when it adds a sung word the lyrics lack (e.g. a leading "Ja,"), and a missing line only when
  it is clearly a sung line (a name, an intro shout) that every lyrics source dropped.
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

    def __init__(self, decisions: Decisions, title: str, artists: list[str],
                 current_source: str = ""):
        self._decisions = decisions
        self._title = title
        self._artists = artists
        self._current_source = current_source

    def render(self) -> str:
        d = self._decisions
        parts = [f"Song: {', '.join(self._artists)} – {self._title}"]
        if self._current_source:
            parts.append(f"The current lyrics come from: {self._current_source}")
        parts += ["", "Current lyrics (line number: text):"]
        parts += [f"{i}: {text}" for i, text in enumerate(d.current)]
        if d.variants:
            parts += ["", "Variants (other sources wrote these lines differently):"]
            for k, v in enumerate(d.variants, 1):
                parts.append(f"V{k} – line {v.line}:")
                for n, (text, who) in enumerate(zip(v.options, v.supporters, strict=True)):
                    parts.append(f"  {n}: {text}   [{', '.join(who)}]")
        if d.insertions:
            parts += ["",
                      "Missing-line candidates (other sources have these, the current lyrics do not):"]
            for k, ins in enumerate(d.insertions, 1):
                where = "before line 0" if ins.after < 0 else f"after line {ins.after}"
                parts.append(f"I{k} – {where}: {ins.text}   [{', '.join(ins.supporters)}]")
        parts += ["", "Answer with JSON in exactly this shape:", self.SCHEMA]
        return "\n".join(parts)
