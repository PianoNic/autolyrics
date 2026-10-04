"""Lyrics providers, ported from Composer's `utils/lyrics-search/providers`.

Every provider swallows its own failures (timeouts, 404s, bot challenges) and returns no results,
so one dead source never sinks a search.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from autolyrics.formats.lrc import detect_lrc_sync_type, parse_lrc
from autolyrics.formats.plain import parse_plain
from autolyrics.formats.qrc import detect_qrc_sync_type, parse_qrc
from autolyrics.formats.ttml import detect_ttml_sync_type, parse_ttml
from autolyrics.model import Lyrics, SyncType

log = logging.getLogger(__name__)

# Better word timing first: Better Lyrics serves Apple-style TTML, binimum mixes sources,
# QQ's word timing is good but its text is often a different edit, LRCLIB is community-made.
SOURCE_PREFERENCE = {"boidu": 0, "binimum": 1, "portato": 2, "lrclib": 3}


@dataclass
class Query:
    track: str
    artist: str
    album: str | None = None
    duration: float | None = None
    video_id: str | None = None


@dataclass
class Candidate:
    source: str
    label: str
    format: str  # "ttml" | "lrc" | "qrc" | "plain"
    content: str
    declared_sync: SyncType
    track: str | None = None
    artist: str | None = None
    duration: float | None = None
    source_id: str | None = None
    lyrics: Lyrics | None = None
    rejected: str | None = None
    notes: list[str] = field(default_factory=list)

    def parse(self, audio_duration: float | None) -> Lyrics:
        if self.lyrics is None:
            parser = {
                "ttml": lambda c: parse_ttml(c),
                "lrc": lambda c: parse_lrc(c, audio_duration),
                "qrc": lambda c: parse_qrc(c, audio_duration),
                "plain": parse_plain,
            }[self.format]
            self.lyrics = parser(self.content)
        return self.lyrics

    @property
    def sync(self) -> SyncType:
        return self.lyrics.sync_type if self.lyrics else self.declared_sync

    def summary(self) -> dict:
        return {
            "source": self.source, "label": self.label, "format": self.format,
            "sync": self.sync.value, "track": self.track, "artist": self.artist,
            "duration": self.duration, "id": self.source_id, "rejected": self.rejected,
            "lines": len(self.lyrics.lines) if self.lyrics else None, "notes": self.notes,
        }


# -- Providers ----------------------------------------------------------------


async def _get_json(client: httpx.AsyncClient, url: str, params: dict, name: str):
    try:
        response = await client.get(url, params=params, timeout=20)
    except httpx.HTTPError as error:
        log.warning("[%s] request failed: %s", name, error)
        return None
    if response.status_code == 404:
        return None
    if not response.is_success:
        log.warning("[%s] returned %s", name, response.status_code)
        return None
    try:
        return response.json()
    except ValueError:
        # binimum sits behind a Cloudflare challenge that answers with HTML.
        log.warning("[%s] returned non-JSON (likely a bot challenge)", name)
        return None


async def search_boidu(q: Query, client: httpx.AsyncClient) -> list[Candidate]:
    if not (q.track and q.artist and q.duration and q.video_id):
        return []
    params = {"s": q.track, "a": q.artist, "d": round(q.duration), "videoId": q.video_id}
    if q.album:
        params["al"] = q.album
    body = await _get_json(client, "https://lyrics-api.boidu.dev/getLyrics", params, "boidu")
    ttml = (body or {}).get("ttml") if isinstance(body, dict) else None
    if not ttml:
        return []
    return [Candidate("boidu", "Better Lyrics", "ttml", ttml, detect_ttml_sync_type(ttml),
                      q.track, q.artist, source_id=q.video_id)]


async def search_portato(q: Query, client: httpx.AsyncClient) -> list[Candidate]:
    if not (q.track and q.artist and (q.album or q.duration)):
        return []
    params = {"song": q.track, "artist": q.artist}
    if q.album:
        params["album"] = q.album
    if q.duration:
        params["duration"] = round(q.duration)
    if q.video_id:
        params["videoId"] = q.video_id
    body = await _get_json(client, "https://lyrics-api.boidu.dev/qq/getLyrics", params, "portato")
    qrc = (body or {}).get("lyrics") if isinstance(body, dict) else None
    if not qrc:
        return []
    return [Candidate("portato", "QQ Music (Portato)", "qrc", qrc, detect_qrc_sync_type(qrc),
                      q.track, q.artist)]


async def search_binimum(q: Query, client: httpx.AsyncClient) -> list[Candidate]:
    if not (q.track and q.artist):
        return []
    params = {"track": q.track, "artist": q.artist}
    if q.album:
        params["album"] = q.album
    if q.duration:
        params["duration"] = round(q.duration)
    body = await _get_json(client, "https://lyrics-api.binimum.org/", params, "binimum")
    if not isinstance(body, dict):
        return []
    out = []
    for r in body.get("results") or []:
        url = r.get("lyricsUrl")
        if not url:
            continue
        try:
            response = await client.get(url, timeout=20)
            response.raise_for_status()
        except httpx.HTTPError as error:
            log.warning("[binimum] lyrics fetch failed: %s", error)
            continue
        ttml = response.text
        sync = r.get("timing_type") if r.get("timing_type") in ("syllable", "word", "line") else "line"
        out.append(Candidate("binimum", "Binimum", "ttml", ttml, SyncType(sync),
                             r.get("track_name"), r.get("artist_name"),
                             _usable_duration(r.get("duration")), str(r.get("id"))))
    return out


async def search_lrclib(q: Query, client: httpx.AsyncClient) -> list[Candidate]:
    if not q.track:
        return []
    params = {"track_name": q.track}
    if q.artist:
        params["artist_name"] = q.artist
    body = await _get_json(client, "https://lrclib.net/api/search", params, "lrclib")
    if not isinstance(body, list):
        return []
    out = []
    for r in body:
        synced, plain = r.get("syncedLyrics"), r.get("plainLyrics")
        if r.get("instrumental"):
            continue
        if synced and synced.strip():
            out.append(Candidate("lrclib", "LRCLIB", "lrc", synced, detect_lrc_sync_type(synced),
                                 r.get("trackName"), r.get("artistName"),
                                 _usable_duration(r.get("duration")), str(r.get("id"))))
        elif plain and plain.strip():
            out.append(Candidate("lrclib", "LRCLIB", "plain", plain, SyncType.UNSYNCED,
                                 r.get("trackName"), r.get("artistName"),
                                 _usable_duration(r.get("duration")), str(r.get("id"))))
    return out


def _usable_duration(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


PROVIDERS = (search_boidu, search_binimum, search_portato, search_lrclib)


async def search_all(q: Query, client: httpx.AsyncClient) -> list[Candidate]:
    results = await asyncio.gather(*(p(q, client) for p in PROVIDERS), return_exceptions=True)
    out: list[Candidate] = []
    for provider, result in zip(PROVIDERS, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("[%s] crashed: %s", provider.__name__, result)
            continue
        out.extend(result)
    return out


# -- Validation and ranking ---------------------------------------------------

MIN_WORDS = 12


def validate(c: Candidate, audio_duration: float | None, tolerance: float) -> None:
    """Parse the candidate and set `rejected` when it cannot be this recording's lyrics."""
    if audio_duration and c.duration and abs(c.duration - audio_duration) > tolerance:
        c.rejected = f"length {c.duration:.0f}s vs audio {audio_duration:.0f}s"
        return
    try:
        lyrics = c.parse(audio_duration)
    except Exception as error:  # noqa: BLE001 - any malformed document from an untrusted source
        c.rejected = f"unparseable: {error}"
        return
    words = sum(len(line.all_words) for line in lyrics.lines)
    if words < MIN_WORDS:
        c.rejected = f"only {words} words"
        return
    if audio_duration and lyrics.sync_type != SyncType.UNSYNCED:
        ends = [b[1] for line in lyrics.lines if (b := line.bounds())]
        if ends and max(ends) > audio_duration + tolerance:
            c.rejected = f"timed past the end of the audio ({max(ends):.0f}s > {audio_duration:.0f}s)"
            return
    if c.declared_sync.is_word_level and not lyrics.sync_type.is_word_level:
        c.notes.append(f"declared {c.declared_sync.value} but parsed as {lyrics.sync_type.value}")


def rank(candidates: list[Candidate], audio_duration: float | None) -> list[Candidate]:
    """Usable candidates, best first: finer sync, preferred source, closest length."""
    usable = [c for c in candidates if c.rejected is None and c.lyrics is not None]

    def key(c: Candidate):
        closeness = abs((c.duration or audio_duration or 0) - (audio_duration or 0))
        return (-c.sync.rank, SOURCE_PREFERENCE.get(c.source, 9), closeness)

    return sorted(usable, key=key)
