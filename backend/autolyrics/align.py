"""Forced alignment: known lyrics text + isolated vocals -> a time for every word.

Uses torchaudio's MMS_FA (wav2vec2 trained on 1,100+ languages). Text is romanised to the model's
a-z alphabet, so German, Turkish, Spanish, ... all go through the same model. The `*` star token
soaks up audio the text does not cover (ad-libs, intros), which keeps the alignment from dragging
words onto noise.
"""

import itertools
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.audio import to_wav
from autolyrics.model import Line, Lyrics, Word

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SECONDS = 320 / SAMPLE_RATE  # wav2vec2 downsamples 16 kHz audio by 320
CHUNK_SECONDS = 30.0
CONTEXT_SECONDS = 1.0
LINE_PADDING = 0.75  # seconds of slack around a line-synced line's window
LOW_CONFIDENCE = 0.03
CONFIDENT = 0.1  # words trusted when measuring offsets (no misplaced word scored above this)
DETACHED_CONFIDENCE = 0.05
DETACHED_GAP = 0.5
OFFSET_NEIGHBOURS = 4  # lines either side used for a line's local offset
CLOSE_GAP = 0.30  # word gaps shorter than this are closed, as sung words run into each other

_DIGITS = re.compile(r"\d+")
_SYMBOLS = {"&": " und ", "+": " plus ", "%": " prozent ", "$": " dollar ", "€": " euro "}
_SYMBOLS_EN = {"&": " and ", "+": " plus ", "%": " percent ", "$": " dollar ", "€": " euro "}


@dataclass
class Span:
    begin: float
    end: float
    score: float


# -- text ---------------------------------------------------------------------


def normalize(word: str, language: str, alphabet: set[str]) -> str:
    """Spell a lyric word in the aligner's alphabet: "Größe" -> "grosse", "187" -> "hundert..."."""
    from num2words import num2words
    from unidecode import unidecode

    text = word.lower()
    symbols = _SYMBOLS if language.startswith("de") else _SYMBOLS_EN
    for symbol, spoken in symbols.items():
        text = text.replace(symbol, spoken)

    def spell(m: re.Match) -> str:
        try:
            spoken = num2words(int(m.group(0)), lang=language.split("-")[0])
        except (NotImplementedError, OverflowError, ValueError):
            spoken = num2words(int(m.group(0)))
        if language.startswith("de"):
            # Said "hundertsiebenundachtzig", not "einhundert...".
            spoken = re.sub(r"^ein(hundert|tausend)", r"\1", spoken)
        return spoken

    text = _DIGITS.sub(spell, text)
    text = unidecode(text).lower().replace("`", "'").replace("’", "'")
    return "".join(c for c in text if c in alphabet)


GERMAN_HINTS = {"ich", "und", "nicht", "der", "die", "das", "ist", "du", "mit", "auf", "bin", "mein"}
ENGLISH_HINTS = {"the", "and", "you", "i'm", "is", "my", "it", "to", "me", "don't", "that"}


def guess_language(lyrics: Lyrics) -> str:
    if lyrics.metadata.language:
        return lyrics.metadata.language
    words = [w.text.strip().lower() for line in lyrics.lines for w in line.all_words]
    de = sum(w in GERMAN_HINTS for w in words)
    en = sum(w in ENGLISH_HINTS for w in words)
    return "de" if de > en else "en"


# -- model --------------------------------------------------------------------


class Aligner:
    def __init__(self, device: str | None = None):
        import torch
        import torchaudio

        self.torch = torch
        self.F = torchaudio.functional
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        bundle = torchaudio.pipelines.MMS_FA
        self.model = bundle.get_model(with_star=True).to(self.device).eval()
        self.dictionary = bundle.get_dict(star="*")
        self.alphabet = {c for c in self.dictionary if c not in ("-", "*")}

    def close(self) -> None:
        del self.model
        if self.device == "cuda":
            self.torch.cuda.empty_cache()

    def emissions(self, waveform: np.ndarray):
        """Log-probabilities per 20 ms frame for the whole song, computed in chunks."""
        torch = self.torch
        total = len(waveform)
        chunk = int(CHUNK_SECONDS * SAMPLE_RATE)
        context = int(CONTEXT_SECONDS * SAMPLE_RATE)
        frames = []
        with torch.inference_mode():
            for start in range(0, total, chunk):
                left = max(0, start - context)
                right = min(total, start + chunk + context)
                segment = torch.from_numpy(waveform[left:right]).float()[None].to(self.device)
                # Already log-probabilities over the alphabet; the star column is a constant 0.
                emission, _ = self.model(segment)
                emission = emission[0]
                skip = round((start - left) / 320)
                keep = round((min(total, start + chunk) - start) / 320)
                frames.append(emission[skip: skip + keep].cpu())
        return torch.cat(frames)

    def align(self, emission, words: list[str], offset_frame: int) -> list[Span] | None:
        """Align normalised words inside an emission slice. None when it cannot fit."""
        torch = self.torch
        transcript = ["*", *words, "*"]
        tokens = [self.dictionary[c] for w in transcript for c in w]
        # CTC needs a frame per token plus one blank between repeated letters.
        repeats = sum(1 for a, b in itertools.pairwise(tokens) if a == b)
        if emission.shape[0] < len(tokens) + repeats:
            return None
        targets = torch.tensor([tokens], dtype=torch.int32, device=self.device)
        try:
            alignment, scores = self.F.forced_align(emission[None].to(self.device), targets, blank=0)
        except RuntimeError as error:
            log.warning("forced_align failed: %s", error)
            return None
        spans = self.F.merge_tokens(alignment[0].cpu(), scores[0].exp().cpu())
        out: list[Span] = []
        i = 0
        for k, word in enumerate(transcript):
            word_spans = spans[i: i + len(word)]
            i += len(word)
            if k == 0 or k == len(transcript) - 1:
                continue
            length = sum(s.end - s.start for s in word_spans)
            score = sum(s.score * (s.end - s.start) for s in word_spans) / max(length, 1)
            out.append(Span((word_spans[0].start + offset_frame) * FRAME_SECONDS,
                            (word_spans[-1].end + offset_frame) * FRAME_SECONDS, float(score)))
        return out


# -- driver -------------------------------------------------------------------


def _frames(seconds: float) -> int:
    return max(0, int(seconds / FRAME_SECONDS))


def _align_words(aligner: Aligner, emission, words: list[Word], language: str,
                 start: float, end: float) -> bool:
    """Time `words` inside [start, end]. Unalignable words (no letters) stay untimed."""
    normalized = [normalize(w.text, language, aligner.alphabet) for w in words]
    alignable = [(w, n) for w, n in zip(words, normalized, strict=True) if n]
    if not alignable:
        return False
    lo, hi = _frames(start), min(emission.shape[0], math.ceil(end / FRAME_SECONDS))
    spans = aligner.align(emission[lo:hi], [n for _, n in alignable], lo)
    if spans is None:
        return False
    for (word, _), span in zip(alignable, spans, strict=True):
        word.begin, word.end, word.confidence = span.begin, span.end, span.score
    return True


def _line_text_window(line: Line, duration: float, offset: float = 0.0) -> tuple[float, float]:
    return (max(0.0, line.begin + offset - LINE_PADDING),
            min(duration, line.end + offset + LINE_PADDING))


def align_lyrics(lyrics: Lyrics, vocals_16k: np.ndarray, aligner: Aligner,
                 emission=None) -> dict:
    """Give every word in `lyrics` a time, in place. Returns alignment statistics."""
    language = guess_language(lyrics)
    duration = len(vocals_16k) / SAMPLE_RATE
    if emission is None:
        emission = aligner.emissions(vocals_16k)
    lines = [line for line in lyrics.lines if line.words or line.background]
    line_synced = all(line.begin is not None and line.end is not None for line in lines)

    for w in (w for line in lines for w in line.all_words):
        w.begin = w.end = w.confidence = None
        w.flags = []

    # A whole-song pass first: it is the result for plain text, and for line-synced text it
    # measures how far the given line times sit from this audio (a different master, an
    # intro the source's audio lacks), so the line windows can be shifted onto the vocals.
    _align_global(aligner, emission, lines, language)
    line_offset = 0.0
    failed_lines = 0
    if line_synced:
        offsets = _local_offsets(lines)
        line_offset = float(np.median(offsets)) if offsets else 0.0
        for line, offset in zip(lines, offsets or [0.0] * len(lines), strict=True):
            start, end = _line_text_window(line, duration, offset)
            # When the window misses, the line timing may be off: retry wider, else keep the
            # whole-song pass.
            if (line.words
                    and not _align_words(aligner, emission, line.words, language, start, end)
                    and not _align_words(aligner, emission, line.words, language,
                                         max(0.0, start - 3), min(duration, end + 3))):
                failed_lines += 1

    for line in lines:
        if line.background:
            timed = [w for w in line.words if w.timed]
            if timed:
                start, end = timed[0].begin - 1.5, timed[-1].end + 2.5
            elif line.begin is not None:
                start, end = _line_text_window(line, duration, line_offset)
            else:
                continue
            _align_words(aligner, emission, line.background, language,
                         max(0.0, start), min(duration, end))

    for line in lines:
        reanchor_detached(line.words)
        fill_gaps(line.words, line)
        fill_gaps(line.background, line)
        polish_line(line.words)
        polish_line(line.background)
        line.begin = line.end = None  # word times are the truth now

    words = [w for line in lines for w in line.all_words]
    scored = [w.confidence for w in words if w.confidence is not None]
    return {
        "language": language,
        "mode": "line-windows" if line_synced else "global",
        "line_offset": round(line_offset, 3),
        "words": len(words),
        "low_confidence": sum("low-confidence" in w.flags for w in words),
        "interpolated": sum("interpolated" in w.flags for w in words),
        "reanchored": sum("reanchored" in w.flags for w in words),
        "mean_confidence": round(float(np.mean(scored)), 3) if scored else None,
        "failed_lines": failed_lines,
    }


def _local_offsets(lines: list[Line]) -> list[float]:
    """Per line, how far the given line time sits from where the whole-song pass heard it.

    A median over neighbouring lines rather than one song-wide number: a music video that inserts
    a skit shifts everything after it, so the offset changes partway through the song.
    """
    diffs: list[float | None] = []
    for line in lines:
        first = next((w for w in line.words if w.timed and (w.confidence or 0) >= CONFIDENT), None)
        diffs.append(first.begin - line.begin if first is not None and line.begin is not None
                     else None)
    known = [d for d in diffs if d is not None]
    if len(known) < 3:
        return []
    fallback = float(np.median(known))
    offsets = []
    for i in range(len(lines)):
        near = [d for d in diffs[max(0, i - OFFSET_NEIGHBOURS): i + OFFSET_NEIGHBOURS + 1]
                if d is not None]
        offsets.append(float(np.median(near)) if len(near) >= 2 else fallback)
    return offsets


def measure_offset(lyrics: Lyrics, vocals_16k: np.ndarray, aligner: Aligner,
                   emission=None) -> dict:
    """How far a word-synced source's times sit from this audio: align its text from scratch and
    compare word starts. A consistent shift means the source was timed against another master."""
    if emission is None:
        emission = aligner.emissions(vocals_16k)
    probe = lyrics.model_copy(deep=True)
    align_lyrics(probe, vocals_16k, aligner, emission)
    diffs = []
    for src_line, probe_line in zip(lyrics.lines, probe.lines, strict=True):
        for src, aligned in zip(src_line.words, probe_line.words, strict=True):
            if src.timed and aligned.timed and (aligned.confidence or 0) >= CONFIDENT:
                diffs.append(aligned.begin - src.begin)
    if len(diffs) < 10:
        return {"offset": 0.0, "spread": None, "words": len(diffs)}
    diffs = np.array(diffs)
    offset = float(np.median(diffs))
    spread = float(np.median(np.abs(diffs - offset)))
    return {"offset": round(offset, 3), "spread": round(spread, 3), "words": len(diffs)}


def shift_lyrics(lyrics: Lyrics, seconds: float) -> None:
    for line in lyrics.lines:
        if line.begin is not None:
            line.begin = max(0.0, round(line.begin + seconds, 3))
            line.end = max(0.0, round(line.end + seconds, 3))
        for w in line.all_words:
            if w.timed:
                w.begin = max(0.0, round(w.begin + seconds, 3))
                w.end = max(0.0, round(w.end + seconds, 3))


def _align_global(aligner: Aligner, emission, lines: list[Line], language: str) -> None:
    """No line times: align the whole song in one pass, with a star between lines."""
    transcript: list[str] = []
    owners: list[Word] = []
    for line in lines:
        for w in line.words:
            n = normalize(w.text, language, aligner.alphabet)
            if n:
                transcript.append(n)
                owners.append(w)
        transcript.append("*")
        owners.append(None)
    spans = aligner.align(emission, transcript[:-1], 0)
    if spans is None:
        raise RuntimeError("lyrics are longer than the audio can hold")
    for word, span in zip(owners[:-1], spans, strict=True):
        if word is not None:
            word.begin, word.end, word.confidence = span.begin, span.end, span.score


def reanchor_detached(words: list[Word]) -> None:
    """A barely-recognised word far from the rest of its line was almost always pulled onto a
    backing vocal or an echo; put it back against its neighbour."""
    for k, w in enumerate(words):
        if not w.timed or (w.confidence or 0) >= DETACHED_CONFIDENCE:
            continue
        nxt = words[k + 1] if k + 1 < len(words) and words[k + 1].timed else None
        prev = words[k - 1] if k > 0 and words[k - 1].timed else None
        length = min(w.end - w.begin, 0.4)
        if nxt is not None and nxt.begin - w.end > DETACHED_GAP:
            w.begin, w.end = nxt.begin - length, nxt.begin
            w.flags.append("reanchored")
        elif nxt is None and prev is not None and w.begin - prev.end > DETACHED_GAP:
            w.begin, w.end = prev.end, prev.end + length
            w.flags.append("reanchored")


def fill_gaps(words: list[Word], line: Line) -> None:
    """Time unaligned words by spreading them between their timed neighbours by length."""
    i = 0
    while i < len(words):
        if words[i].timed:
            i += 1
            continue
        j = i
        while j < len(words) and not words[j].timed:
            j += 1
        prev_end = words[i - 1].end if i > 0 else None
        next_begin = words[j].begin if j < len(words) else None
        if prev_end is None and next_begin is None:
            if line.begin is None:
                return
            prev_end, next_begin = line.begin, line.end
        elif prev_end is None:
            prev_end = max(0.0, next_begin - 0.3 * (j - i))
        elif next_begin is None:
            next_begin = prev_end + 0.3 * (j - i)
        weights = [max(1, len(w.text.strip())) for w in words[i:j]]
        total = sum(weights)
        t = prev_end
        span = max(0.05 * (j - i), next_begin - prev_end)
        for w, weight in zip(words[i:j], weights, strict=True):
            w.begin, w.end = t, t + span * weight / total
            t = w.end
            w.flags.append("interpolated")
        i = j


def polish_line(words: list[Word]) -> None:
    """Close small gaps, enforce order and a minimum length, flag weak words."""
    for k, w in enumerate(words):
        if not w.timed:
            continue
        if k > 0 and words[k - 1].timed and w.begin < words[k - 1].end:
            w.begin = words[k - 1].end
        if k + 1 < len(words) and words[k + 1].timed:
            gap = words[k + 1].begin - w.end
            if 0 < gap < CLOSE_GAP:
                w.end = words[k + 1].begin
        w.end = max(w.end, w.begin + 0.05)
        w.begin, w.end = round(w.begin, 3), round(w.end, 3)
        if w.confidence is not None and w.confidence < LOW_CONFIDENCE:
            w.flags.append("low-confidence")


def load_vocals_16k(vocals_path: Path, work_dir: Path) -> np.ndarray:
    wav_path = to_wav(vocals_path, work_dir / "vocals16k.wav", sample_rate=SAMPLE_RATE, mono=True)
    data, _ = sf.read(wav_path, dtype="float32")
    return data
