"""TTML in the Apple Music lyric dialect, as Composer reads and writes it.

Not strict W3C TTML 1: span times are absolute and timestamps use m:ss.mmm. Composer's editor
imports what `write` produces, so keep the two in step with Composer's `utils/ttml.ts`.
"""

import re
import xml.etree.ElementTree as ET

from autolyrics.domain.lyrics import Agent, Line, Lyrics, Metadata, SyncType, Word
from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.infrastructure.services.formats.time_format import TimeFormat


class TtmlDocument:
    """Namespace-tolerant access to a parsed TTML tree."""

    TTM_NS = "http://www.w3.org/ns/ttml#metadata"
    XML_NS = "http://www.w3.org/XML/1998/namespace"
    ROOT_TAG = re.compile(r"<tt\b[^>]*>")
    DECLARED = re.compile(r"xmlns:([A-Za-z][\w.-]*)\s*=")
    USED_ELEMENT = re.compile(r"</?([A-Za-z][\w.-]*):")
    USED_ATTRIBUTE = re.compile(r"\s([A-Za-z][\w.-]*):[\w.-]+\s*=")

    def __init__(self, content: str):
        content = content.replace('\\"', '"').replace("\\n", "\n")
        self.root = ET.fromstring(self._declare_missing_namespaces(content).encode("utf-8"))

    @classmethod
    def _declare_missing_namespaces(cls, content: str) -> str:
        """Bind prefixes a sloppy document uses without declaring, so the parser accepts it."""
        root = cls.ROOT_TAG.search(content)
        if not root:
            return content
        declared = {"xml", "xmlns", *cls.DECLARED.findall(root.group(0))}
        used = set(cls.USED_ELEMENT.findall(content)) | set(cls.USED_ATTRIBUTE.findall(content))
        missing = sorted(used - declared)
        if not missing:
            return content
        additions = "".join(f' xmlns:{p}="urn:autolyrics:unbound:{p}"' for p in missing)
        return content.replace(root.group(0), root.group(0)[:-1] + additions + ">", 1)

    @staticmethod
    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def attr(el: ET.Element, local: str, namespaces: tuple[str, ...] = ()) -> str | None:
        if local in el.attrib:
            return el.attrib[local]
        for ns in namespaces:
            key = f"{{{ns}}}{local}"
            if key in el.attrib:
                return el.attrib[key]
        return None

    @classmethod
    def role(cls, el: ET.Element) -> str | None:
        return cls.attr(el, "role", (cls.TTM_NS,))


class TtmlFormat:
    TT_NS = "http://www.w3.org/ns/ttml"
    TTM_NS = TtmlDocument.TTM_NS
    ITUNES_NS = "http://music.apple.com/lyric-ttml-internal"
    COMPOSER_NS = "https://composer.betterlyrics.org/ttml"
    XML_NS = TtmlDocument.XML_NS
    SKIPPED_ROLES = ("x-bg", "x-translation", "x-roman")

    def __init__(self, splitter: BackgroundSplitter):
        self._splitter = splitter

    # -- reading --------------------------------------------------------------

    @staticmethod
    def detect(content: str) -> SyncType:
        if re.search(r"<span\b[^>]*\bbegin\s*=", content):
            return SyncType.SYLLABLE
        if re.search(r"<p\b[^>]*\bbegin\s*=", content):
            return SyncType.LINE
        return SyncType.UNSYNCED

    def parse(self, content: str) -> Lyrics:
        doc = TtmlDocument(content)
        metadata, agents = self._read_head(doc)
        lines = [line for p in doc.root.iter() if doc.local(p.tag) == "p"
                 if (line := self._read_line(doc, p)).has_content]
        return Lyrics(lines=lines, agents=agents or [Agent(id="v1")], metadata=metadata)

    def _read_head(self, doc: TtmlDocument) -> tuple[Metadata, list[Agent]]:
        metadata = Metadata(language=doc.root.attrib.get(f"{{{self.XML_NS}}}lang") or None)
        agents: list[Agent] = []
        for el in doc.root.iter():
            name = doc.local(el.tag)
            if name == "title" and el.text and not metadata.title:
                metadata.title = el.text.strip()
            elif name == "agent" and doc.attr(el, "id", (self.XML_NS,)):
                agent_name = next((n.text for n in el if doc.local(n.tag) == "name" and n.text),
                                  None)
                agents.append(Agent(id=doc.attr(el, "id", (self.XML_NS,)),
                                    type=el.attrib.get("type", "person"), name=agent_name))
            elif name == "meta" and el.attrib.get("key"):
                self._read_meta(el.attrib["key"], el.attrib.get("value", ""), metadata)
            elif name == "songwriter" and el.text:
                metadata.songwriters.append(el.text.strip())
            elif name == "body" and el.attrib.get("dur"):
                metadata.duration = TimeFormat.parse_ttml(el.attrib["dur"])
        return metadata, agents

    @staticmethod
    def _read_meta(key: str, value: str, metadata: Metadata) -> None:
        if not value:
            return
        if key == "artists":
            metadata.artists.append(value)
        elif key == "album":
            metadata.album = value
        elif key in ("songwriter", "songwriters"):
            metadata.songwriters.append(value)

    def _read_line(self, doc: TtmlDocument, p: ET.Element) -> Line:
        agent = (doc.attr(p, "agent", (self.TTM_NS,)) or "v1").lstrip("#")
        bg_el = next((c for c in p if doc.local(c.tag) == "span" and doc.role(c) == "x-bg"), None)
        background = self._timed_words(doc, bg_el) if bg_el is not None else []
        if bg_el is not None and not background:
            background = Word.tokenize("".join(bg_el.itertext()))

        words = self._timed_words(doc, p)
        line = Line(words=words, background=background, agent=agent)
        if not words:
            if bg_el is None:
                line.words, line.background = self._splitter.split(self._untimed_text(doc, p))
            else:
                line.words = Word.tokenize(self._untimed_text(doc, p))
            line.begin = TimeFormat.parse_ttml(p.attrib.get("begin", ""))
            line.end = TimeFormat.parse_ttml(p.attrib.get("end", ""))
        return line

    @staticmethod
    def _timed_words(doc: TtmlDocument, parent: ET.Element) -> list[Word]:
        """Direct child spans with a begin time; whitespace between spans marks a word break."""
        words: list[Word] = []
        for child in parent:
            if doc.local(child.tag) == "span" and doc.role(child) is None and "begin" in child.attrib:
                text = "".join(child.itertext())
                if text.strip():
                    words.append(Word(text=text,
                                      begin=TimeFormat.parse_ttml(child.attrib.get("begin", "")),
                                      end=TimeFormat.parse_ttml(child.attrib.get("end", ""))))
            if words and re.search(r"\s", child.tail or ""):
                words[-1].text = words[-1].text.rstrip() + " "
        # A span may carry its own surrounding whitespace; normalise to the trailing-space rule.
        for w in words:
            w.text = w.text.strip() + (" " if w.text != w.text.rstrip() else "")
        if words:
            words[-1].text = words[-1].text.rstrip()
        return words

    @classmethod
    def _untimed_text(cls, doc: TtmlDocument, p: ET.Element) -> str:
        parts = [p.text or ""]
        for child in p:
            if doc.role(child) not in cls.SKIPPED_ROLES:
                parts.append("".join(child.itertext()))
            parts.append(child.tail or "")
        return " ".join("".join(parts).split())

    # -- writing --------------------------------------------------------------

    @staticmethod
    def _esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;")

    @classmethod
    def _esc_attr(cls, text: str) -> str:
        return cls._esc(text).replace('"', "&quot;")

    @classmethod
    def _spans(cls, words: list[Word]) -> str:
        out = []
        for i, w in enumerate(words):
            space = " " if i < len(words) - 1 and w.text.endswith(" ") else ""
            out.append(f'<span begin="{TimeFormat.apple(w.begin)}" end="{TimeFormat.apple(w.end)}">'
                       f"{cls._esc(w.text.rstrip())}</span>{space}")
        return "".join(out)

    def write(self, lyrics: Lyrics) -> str:
        """Serialise in Composer's TTML shape. Word-timed lines get spans, others line timing."""
        word_level = lyrics.sync_type.is_word_level
        timing = "Word" if word_level else "Line"
        parts = [self._root_tag(lyrics, timing), "  <head>", "    <metadata>",
                 *self._head_lines(lyrics), "    </metadata>", "  </head>"]
        meta = lyrics.metadata
        dur = f' dur="{TimeFormat.apple(meta.duration)}"' if meta.duration else ""
        parts += [f"  <body{dur}>", "    <div>"]
        key = 0
        for line in lyrics.lines:
            bounds = line.bounds()
            if bounds is None or not line.has_content:
                continue
            key += 1
            parts.append(self._paragraph(line, bounds, key, word_level))
        parts += ["    </div>", "  </body>", "</tt>"]
        return "\n".join(parts)

    def _root_tag(self, lyrics: Lyrics, timing: str) -> str:
        language = lyrics.metadata.language
        lang = f' xml:lang="{self._esc_attr(language)}"' if language else ""
        return (f'<tt xmlns="{self.TT_NS}" xmlns:ttm="{self.TTM_NS}"'
                f' xmlns:ttp="http://www.w3.org/ns/ttml#parameter"'
                f' xmlns:itunes="{self.ITUNES_NS}" xmlns:composer="{self.COMPOSER_NS}"'
                f' ttp:timeBase="media"{lang} itunes:timing="{timing}"'
                f' composer:timing="{timing}">')

    def _head_lines(self, lyrics: Lyrics) -> list[str]:
        meta = lyrics.metadata
        out = []
        if meta.title:
            out.append(f"      <ttm:title>{self._esc(meta.title)}</ttm:title>")
        for artist in meta.artists:
            out.append(f'      <composer:meta key="artists" value="{self._esc_attr(artist)}"/>')
        if meta.album:
            out.append(f'      <composer:meta key="album" value="{self._esc_attr(meta.album)}"/>')
        for writer in meta.songwriters:
            out.append(f'      <composer:meta key="songwriter" value="{self._esc_attr(writer)}"/>')
        for agent in lyrics.agents:
            if agent.name:
                out.append(f'      <ttm:agent xml:id="{self._esc_attr(agent.id)}" '
                           f'type="{agent.type}">')
                out.append(f"        <ttm:name>{self._esc(agent.name)}</ttm:name>")
                out.append("      </ttm:agent>")
            else:
                out.append(f'      <ttm:agent xml:id="{self._esc_attr(agent.id)}" '
                           f'type="{agent.type}"/>')
        return out

    def _paragraph(self, line: Line, bounds: tuple[float, float], key: int,
                   word_level: bool) -> str:
        begin, end = bounds
        if word_level and line.word_timed:
            content = self._spans(line.words)
            if line.background:
                content += f'<span ttm:role="x-bg">{self._spans(line.background)}</span>'
        else:
            content = self._esc(line.text)
            if line.background:
                content += (f'<span ttm:role="x-bg"><span begin="{TimeFormat.apple(begin)}" '
                            f'end="{TimeFormat.apple(end)}">{self._esc(line.background_text)}'
                            f"</span></span>")
        return (f'      <p begin="{TimeFormat.apple(begin)}" end="{TimeFormat.apple(end)}"'
                f' itunes:key="L{key}" ttm:agent="{self._esc_attr(line.agent)}">{content}</p>')
