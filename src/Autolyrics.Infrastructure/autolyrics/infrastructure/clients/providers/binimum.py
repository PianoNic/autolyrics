import logging

import httpx

from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery
from autolyrics.domain.lyrics import SyncType
from autolyrics.infrastructure.clients.providers.http_provider import HttpLyricsProvider

log = logging.getLogger(__name__)


class BinimumProvider(HttpLyricsProvider):
    """binimum: a search across several sources; each result links to a TTML document."""

    name = "binimum"
    URL = "https://lrc.red/api/v1"  # binimum moved here; the old address redirects
    TIMINGS = ("syllable", "word", "line")

    async def _search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        params = {"track": query.track, "artist": query.artist}
        if query.album:
            params["album"] = query.album
        if query.duration:
            params["duration"] = round(query.duration)
        body = await self._get_json(self.URL, params)
        if not isinstance(body, dict):
            return []
        found = []
        for result in body.get("results") or []:
            candidate = await self._fetch(result)
            if candidate is not None:
                found.append(candidate)
        return found

    async def _fetch(self, result: dict) -> LyricsCandidate | None:
        url = result.get("lyricsUrl")
        if not url:
            return None
        try:
            response = await self._client.get(url, timeout=20)
            response.raise_for_status()
        except httpx.HTTPError as error:
            log.warning("[binimum] lyrics fetch failed: %s", error)
            return None
        timing = result.get("timing_type")
        sync = SyncType(timing if timing in self.TIMINGS else "line")
        return LyricsCandidate(self.name, "Binimum", "ttml", response.text, sync,
                               result.get("track_name"), result.get("artist_name"),
                               self._usable_duration(result.get("duration")),
                               str(result.get("id")))
