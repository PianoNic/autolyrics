import httpx

from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery
from autolyrics.infrastructure.formats.qrc_format import QrcFormat
from autolyrics.infrastructure.formats.ttml_format import TtmlFormat
from autolyrics.infrastructure.providers.http_provider import HttpLyricsProvider


class BoiduKeyedProvider(HttpLyricsProvider):
    """lyrics-api.boidu.dev serves cached songs freely and wants an API key for new ones."""

    def __init__(self, client: httpx.AsyncClient, api_key: str | None):
        super().__init__(client)
        self._api_key = api_key

    def _headers(self) -> dict | None:
        return {"X-API-Key": self._api_key} if self._api_key else None


class BetterLyricsProvider(BoiduKeyedProvider):
    """Better Lyrics: Apple-style TTML, often word- or syllable-synced. Keyed on a video id."""

    name = "boidu"
    URL = "https://lyrics-api.boidu.dev/getLyrics"

    def can_search(self, query: LyricsQuery) -> bool:
        return bool(query.track and query.artist and query.duration and query.video_id)

    async def _search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        params = {"s": query.track, "a": query.artist, "d": round(query.duration),
                  "videoId": query.video_id}
        if query.album:
            params["al"] = query.album
        body = await self._get_json(self.URL, params)
        ttml = body.get("ttml") if isinstance(body, dict) else None
        if not ttml:
            return []
        return [LyricsCandidate(self.name, "Better Lyrics", "ttml", ttml, TtmlFormat.detect(ttml),
                                query.track, query.artist, source_id=query.video_id)]


class PortatoProvider(BoiduKeyedProvider):
    """QQ Music lyrics as QRC, usually word-synced; needs an album or a duration to match."""

    name = "portato"
    URL = "https://lyrics-api.boidu.dev/qq/getLyrics"

    def __init__(self, client: httpx.AsyncClient, api_key: str | None, qrc: QrcFormat):
        super().__init__(client, api_key)
        self._qrc = qrc

    def can_search(self, query: LyricsQuery) -> bool:
        return bool(query.track and query.artist and (query.album or query.duration))

    async def _search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        params = {"song": query.track, "artist": query.artist}
        if query.album:
            params["album"] = query.album
        if query.duration:
            params["duration"] = round(query.duration)
        if query.video_id:
            params["videoId"] = query.video_id
        body = await self._get_json(self.URL, params)
        qrc = body.get("lyrics") if isinstance(body, dict) else None
        if not qrc:
            return []
        return [LyricsCandidate(self.name, "QQ Music (Portato)", "qrc", qrc,
                                self._qrc.detect(qrc), query.track, query.artist)]
