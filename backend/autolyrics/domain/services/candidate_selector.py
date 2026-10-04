from typing import ClassVar

from autolyrics.domain.candidate import LyricsCandidate
from autolyrics.domain.lyrics import SyncType


class CandidateSelector:
    """Judges parsed lyrics candidates against the audio and orders the usable ones."""

    # Better word timing first: Better Lyrics serves Apple-style TTML, binimum mixes sources,
    # QQ's word timing is good but its text is often a different edit, LRCLIB is community-made.
    SOURCE_PREFERENCE: ClassVar = {"boidu": 0, "binimum": 1, "portato": 2, "lrclib": 3}

    def __init__(self, duration_tolerance: float = 3.0, min_words: int = 12):
        self._tolerance = duration_tolerance
        self._min_words = min_words

    def judge(self, c: LyricsCandidate, audio_duration: float | None) -> None:
        """Reject a parsed candidate, or demote it to text-only when its timing cannot belong
        to this recording. The candidate must already be parsed (or carry `rejected`)."""
        if c.rejected is not None or c.lyrics is None:
            return
        lyrics = c.lyrics
        words = len(lyrics.all_words)
        if words < self._min_words:
            c.rejected = f"only {words} words"
            return
        if audio_duration and c.duration and abs(c.duration - audio_duration) > self._tolerance:
            c.text_only = True
            c.notes.append(f"length {c.duration:.0f}s vs audio {audio_duration:.0f}s: text only")
        elif audio_duration and lyrics.sync_type != SyncType.UNSYNCED:
            ends = [b[1] for line in lyrics.lines if (b := line.bounds())]
            if ends and max(ends) > audio_duration + self._tolerance:
                c.text_only = True
                c.notes.append(f"timed past the audio end ({max(ends):.0f}s > "
                               f"{audio_duration:.0f}s): text only")
        if c.declared_sync.is_word_level and not lyrics.sync_type.is_word_level:
            c.notes.append(
                f"declared {c.declared_sync.value} but parsed as {lyrics.sync_type.value}")

    def rank(self, candidates: list[LyricsCandidate],
             audio_duration: float | None) -> list[LyricsCandidate]:
        """Usable candidates, best first: finer sync, preferred source, closest length."""

        def key(c: LyricsCandidate):
            closeness = abs((c.duration or audio_duration or 0) - (audio_duration or 0))
            # Among text-only candidates, a word-synced source still has the most careful text.
            declared = c.lyrics.sync_type.rank if c.lyrics else 0
            return (-c.sync.rank, -declared, self.SOURCE_PREFERENCE.get(c.source, 9), closeness)

        return sorted((c for c in candidates if c.usable), key=key)
