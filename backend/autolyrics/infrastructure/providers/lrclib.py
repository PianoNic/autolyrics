import httpx

from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery
from autolyrics.domain.lyrics import SyncType
from autolyrics.infrastructure.formats.lrc_format import LrcFormat
from autolyrics.infrastructure.providers.http_provider import HttpLyricsProvider


class LrclibProvider(HttpLyricsProvider):
    """LRCLIB: community lyrics, line-synced LRC or plain text, often many copies per song."""

    name = "lrclib"
    URL = "https://lrclib.net/api/search"

    def __init__(self, client: httpx.AsyncClient, lrc: LrcFormat):
        super().__init__(client)
        self._lrc = lrc

    def can_search(self, query: LyricsQuery) -> bool:
        return bool(query.track)

    async def _search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        params = {"track_name": query.track}
        if query.artist:
            params["artist_name"] = query.artist
        body = await self._get_json(self.URL, params)
        if not isinstance(body, list):
            return []
        found = []
        for result in body:
            if result.get("instrumental"):
                continue
            synced, plain = result.get("syncedLyrics"), result.get("plainLyrics")
            meta = (result.get("trackName"), result.get("artistName"),
                    self._usable_duration(result.get("duration")), str(result.get("id")))
            if synced and synced.strip():
                found.append(LyricsCandidate(self.name, "LRCLIB", "lrc", synced,
                                             self._lrc.detect(synced), *meta))
            elif plain and plain.strip():
                found.append(LyricsCandidate(self.name, "LRCLIB", "plain", plain,
                                             SyncType.UNSYNCED, *meta))
        return found
