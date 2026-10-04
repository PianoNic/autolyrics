"""Plain text lyrics: one line per line, parenthesised parts become background vocals."""

import re

from autolyrics.model import Line, Lyrics, Word, tokenize

_PARENS = re.compile(r"\(([^()]*)\)")
# Section labels such as "[Chorus]" or "[Part 2: SSIO]" that some sources mix into the text.
_SECTION = re.compile(r"^\s*\[[^\]]*\]\s*$")


def split_background(text: str) -> tuple[list[Word], list[Word]]:
    """Split a line into main words and the words inside parentheses."""
    background = " ".join(m.strip() for m in _PARENS.findall(text) if m.strip())
    main = " ".join(_PARENS.sub(" ", text).split())
    return tokenize(main), tokenize(background)


def parse_plain(content: str) -> Lyrics:
    lines = []
    for raw in content.splitlines():
        if not raw.strip() or _SECTION.match(raw):
            continue
        main, background = split_background(raw)
        if main or background:
            lines.append(Line(words=main, background=background))
    return Lyrics(lines=lines)
