"""Lyrics data model shared by every stage.

Mirrors Composer's model so its editor can load the result: a word's text keeps a trailing space
when a space follows it, and syllables of one word are consecutive words without that space.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class SyncType(StrEnum):
    SYLLABLE = "syllable"
    WORD = "word"
    LINE = "line"
    UNSYNCED = "unsynced"

    @property
    def rank(self) -> int:
        return {"syllable": 3, "word": 2, "line": 1, "unsynced": 0}[self.value]

    @property
    def is_word_level(self) -> bool:
        return self in (SyncType.SYLLABLE, SyncType.WORD)


class Word(BaseModel):
    text: str
    begin: float | None = None
    end: float | None = None
    # 0..1 from the aligner; None when the time came from a lyrics source.
    confidence: float | None = None
    # Why a reviewer should look at this word, e.g. "low-confidence", "interpolated".
    flags: list[str] = Field(default_factory=list)

    @property
    def timed(self) -> bool:
        return self.begin is not None and self.end is not None


class Line(BaseModel):
    words: list[Word] = Field(default_factory=list)
    background: list[Word] = Field(default_factory=list)
    agent: str = "v1"
    # Line-level timing, used when the words carry no times of their own.
    begin: float | None = None
    end: float | None = None

    @property
    def text(self) -> str:
        return words_text(self.words)

    @property
    def background_text(self) -> str:
        return words_text(self.background)

    @property
    def all_words(self) -> list[Word]:
        return [*self.words, *self.background]

    @property
    def word_timed(self) -> bool:
        return bool(self.words) and all(w.timed for w in self.all_words)

    def bounds(self) -> tuple[float, float] | None:
        """Effective (begin, end): from the words when they are timed, else the line times."""
        timed = [w for w in self.all_words if w.timed]
        if timed and len(timed) == len(self.all_words):
            return min(w.begin for w in timed), max(w.end for w in timed)
        if self.begin is not None and self.end is not None:
            return self.begin, self.end
        return None


class Agent(BaseModel):
    id: str
    type: str = "person"
    name: str | None = None


class Metadata(BaseModel):
    title: str | None = None
    artists: list[str] = Field(default_factory=list)
    album: str | None = None
    language: str | None = None
    duration: float | None = None
    songwriters: list[str] = Field(default_factory=list)


class Lyrics(BaseModel):
    lines: list[Line] = Field(default_factory=list)
    agents: list[Agent] = Field(default_factory=lambda: [Agent(id="v1")])
    metadata: Metadata = Field(default_factory=Metadata)

    @property
    def sync_type(self) -> SyncType:
        lines = [line for line in self.lines if line.words]
        if not lines:
            return SyncType.UNSYNCED
        if all(line.word_timed for line in lines):
            syllables = any(
                not w.text.endswith(" ") and i < len(line.words) - 1
                for line in lines
                for i, w in enumerate(line.words)
            )
            return SyncType.SYLLABLE if syllables else SyncType.WORD
        if all(line.bounds() is not None for line in lines):
            return SyncType.LINE
        return SyncType.UNSYNCED

    def strip_timing(self) -> None:
        for line in self.lines:
            line.begin = line.end = None
            for w in line.all_words:
                w.begin = w.end = w.confidence = None

    @property
    def plain_text(self) -> str:
        out = []
        for line in self.lines:
            text = line.text
            if line.background:
                text = f"{text} ({line.background_text})" if text else f"({line.background_text})"
            out.append(text)
        return "\n".join(out)


def words_text(words: list[Word]) -> str:
    return "".join(w.text for w in words).strip()


def tokenize(text: str) -> list[Word]:
    """Split plain text into untimed words, keeping Composer's trailing-space convention."""
    parts = text.split()
    return [Word(text=p + (" " if i < len(parts) - 1 else "")) for i, p in enumerate(parts)]
