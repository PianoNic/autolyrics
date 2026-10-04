"""TTML in the Apple Music lyric dialect, as Composer reads and writes it.

Not strict W3C TTML 1: span times are absolute and timestamps use m:ss.mmm. Composer's editor
imports what `write_ttml` produces, so keep the two in step with Composer's `utils/ttml.ts`.
"""

import re
import xml.etree.ElementTree as ET

from autolyrics.formats.plain import split_background
from autolyrics.formats.timefmt import format_time, parse_ttml_time
from autolyrics.model import Agent, Line, Lyrics, Metadata, SyncType, Word, tokenize

TT_NS = "http://www.w3.org/ns/ttml"
TTM_NS = "http://www.w3.org/ns/ttml#metadata"
ITUNES_NS = "http://music.apple.com/lyric-ttml-internal"
COMPOSER_NS = "https://composer.betterlyrics.org/ttml"
COMPOSER_NAMESPACES = (COMPOSER_NS, "https://composer.boidu.dev/ttml")
XML_NS = "http://www.w3.org/XML/1998/namespace"

_ROOT_TAG = re.compile(r"<tt\b[^>]*>")
_DECLARED = re.compile(r"xmlns:([A-Za-z][\w.-]*)\s*=")
_USED_ELEMENT = re.compile(r"</?([A-Za-z][\w.-]*):")
_USED_ATTRIBUTE = re.compile(r"\s([A-Za-z][\w.-]*):[\w.-]+\s*=")


# -- Reading ------------------------------------------------------------------


def _declare_missing_namespaces(content: str) -> str:
    """Bind prefixes a sloppy document uses without declaring, so the XML parser accepts it."""
    root = _ROOT_TAG.search(content)
    if not root:
        return content
    declared = {"xml", "xmlns", *_DECLARED.findall(root.group(0))}
    used = set(_USED_ELEMENT.findall(content)) | set(_USED_ATTRIBUTE.findall(content))
    missing = sorted(used - declared)
    if not missing:
        return content
    additions = "".join(f' xmlns:{p}="urn:autolyrics:unbound:{p}"' for p in missing)
    patched = root.group(0)[:-1] + additions + ">"
    return content.replace(root.group(0), patched, 1)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(el: ET.Element, local: str, namespaces: tuple[str, ...] = ()) -> str | None:
    if local in el.attrib:
        return el.attrib[local]
    for ns in namespaces:
        key = f"{{{ns}}}{local}"
        if key in el.attrib:
            return el.attrib[key]
    return None


def _role(el: ET.Element) -> str | None:
    return _attr(el, "role", (TTM_NS,))


def _timed_words(parent: ET.Element) -> list[Word]:
    """Direct child spans with a begin time; whitespace between spans marks a word break."""
    words: list[Word] = []
    for child in parent:
        if _local(child.tag) == "span" and _role(child) is None and "begin" in child.attrib:
            text = "".join(child.itertext())
            if text.strip():
                words.append(
                    Word(
                        text=text,
                        begin=parse_ttml_time(child.attrib.get("begin", "")),
                        end=parse_ttml_time(child.attrib.get("end", "")),
                    )
                )
        if words and re.search(r"\s", child.tail or ""):
            words[-1].text = words[-1].text.rstrip() + " "
    # A span may carry its own surrounding whitespace; normalise to the trailing-space rule.
    for w in words:
        w.text = w.text.strip() + (" " if w.text != w.text.rstrip() else "")
    if words:
        words[-1].text = words[-1].text.rstrip()
    return words


def _untimed_text(p: ET.Element) -> str:
    parts = [p.text or ""]
    for child in p:
        if _role(child) not in ("x-bg", "x-translation", "x-roman"):
            parts.append("".join(child.itertext()))
        parts.append(child.tail or "")
    return " ".join("".join(parts).split())


def parse_ttml(content: str) -> Lyrics:
    content = content.replace('\\"', '"').replace("\\n", "\n")
    root = ET.fromstring(_declare_missing_namespaces(content).encode("utf-8"))

    metadata = Metadata()
    metadata.language = root.attrib.get(f"{{{XML_NS}}}lang") or None
    agents: list[Agent] = []

    for el in root.iter():
        name = _local(el.tag)
        if name == "title" and el.text and not metadata.title:
            metadata.title = el.text.strip()
        elif name == "agent" and _attr(el, "id", (XML_NS,)):
            agent_name = next((n.text for n in el if _local(n.tag) == "name" and n.text), None)
            agents.append(
                Agent(id=_attr(el, "id", (XML_NS,)), type=el.attrib.get("type", "person"),
                      name=agent_name)
            )
        elif name == "meta" and el.attrib.get("key"):
            key, value = el.attrib["key"], el.attrib.get("value", "")
            if key == "artists" and value:
                metadata.artists.append(value)
            elif key == "album" and value:
                metadata.album = value
            elif key in ("songwriter", "songwriters") and value:
                metadata.songwriters.append(value)
        elif name == "songwriter" and el.text:
            metadata.songwriters.append(el.text.strip())
        elif name == "body" and el.attrib.get("dur"):
            metadata.duration = parse_ttml_time(el.attrib["dur"])

    lines: list[Line] = []
    for p in root.iter():
        if _local(p.tag) != "p":
            continue
        agent = (_attr(p, "agent", (TTM_NS,)) or "v1").lstrip("#")
        bg_el = next((c for c in p if _local(c.tag) == "span" and _role(c) == "x-bg"), None)
        background = _timed_words(bg_el) if bg_el is not None else []
        if bg_el is not None and not background:
            background = tokenize("".join(bg_el.itertext()))

        words = _timed_words(p)
        line = Line(words=words, background=background, agent=agent)
        if not words:
            if bg_el is None:
                line.words, line.background = split_background(_untimed_text(p))
            else:
                line.words = tokenize(_untimed_text(p))
            line.begin = parse_ttml_time(p.attrib.get("begin", ""))
            line.end = parse_ttml_time(p.attrib.get("end", ""))
        if line.words or line.background:
            lines.append(line)

    return Lyrics(lines=lines, agents=agents or [Agent(id="v1")], metadata=metadata)


def detect_ttml_sync_type(content: str) -> SyncType:
    if re.search(r"<span\b[^>]*\bbegin\s*=", content):
        return SyncType.SYLLABLE
    if re.search(r"<p\b[^>]*\bbegin\s*=", content):
        return SyncType.LINE
    return SyncType.UNSYNCED


# -- Writing ------------------------------------------------------------------


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;")


def _esc_attr(text: str) -> str:
    return _esc(text).replace('"', "&quot;")


def _spans(words: list[Word]) -> str:
    out = []
    for i, w in enumerate(words):
        space = " " if i < len(words) - 1 and w.text.endswith(" ") else ""
        out.append(
            f'<span begin="{format_time(w.begin)}" end="{format_time(w.end)}">'
            f"{_esc(w.text.rstrip())}</span>{space}"
        )
    return "".join(out)


def write_ttml(lyrics: Lyrics) -> str:
    """Serialise in Composer's TTML shape. Word-timed lines get spans, others line timing."""
    word_level = lyrics.sync_type.is_word_level
    timing = "Word" if word_level else "Line"
    meta = lyrics.metadata
    lang = f' xml:lang="{_esc_attr(meta.language)}"' if meta.language else ""

    root = (
        f'<tt xmlns="{TT_NS}" xmlns:ttm="{TTM_NS}" xmlns:ttp="http://www.w3.org/ns/ttml#parameter"'
        f' xmlns:itunes="{ITUNES_NS}" xmlns:composer="{COMPOSER_NS}" ttp:timeBase="media"{lang}'
        f' itunes:timing="{timing}" composer:timing="{timing}">'
    )
    parts = [
        root,
        "  <head>",
        "    <metadata>",
    ]
    if meta.title:
        parts.append(f"      <ttm:title>{_esc(meta.title)}</ttm:title>")
    for artist in meta.artists:
        parts.append(f'      <composer:meta key="artists" value="{_esc_attr(artist)}"/>')
    if meta.album:
        parts.append(f'      <composer:meta key="album" value="{_esc_attr(meta.album)}"/>')
    for writer in meta.songwriters:
        parts.append(f'      <composer:meta key="songwriter" value="{_esc_attr(writer)}"/>')
    for agent in lyrics.agents:
        if agent.name:
            parts.append(f'      <ttm:agent xml:id="{_esc_attr(agent.id)}" type="{agent.type}">')
            parts.append(f"        <ttm:name>{_esc(agent.name)}</ttm:name>")
            parts.append("      </ttm:agent>")
        else:
            parts.append(f'      <ttm:agent xml:id="{_esc_attr(agent.id)}" type="{agent.type}"/>')
    parts += ["    </metadata>", "  </head>"]

    dur = f' dur="{format_time(meta.duration)}"' if meta.duration else ""
    parts += [f"  <body{dur}>", "    <div>"]

    key = 0
    for line in lyrics.lines:
        bounds = line.bounds()
        if bounds is None or not (line.words or line.background):
            continue
        key += 1
        begin, end = bounds
        if word_level and line.word_timed:
            content = _spans(line.words)
            if line.background:
                content += f'<span ttm:role="x-bg">{_spans(line.background)}</span>'
        else:
            content = _esc(line.text)
            if line.background:
                content += (
                    f'<span ttm:role="x-bg"><span begin="{format_time(begin)}" '
                    f'end="{format_time(end)}">{_esc(line.background_text)}</span></span>'
                )
        parts.append(
            f'      <p begin="{format_time(begin)}" end="{format_time(end)}" itunes:key="L{key}"'
            f' ttm:agent="{_esc_attr(line.agent)}">{content}</p>'
        )

    parts += ["    </div>", "  </body>", "</tt>"]
    return "\n".join(parts)
