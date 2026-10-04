import logging

import httpx

from autolyrics.application.interfaces.lyrics import ILyricsProvider
from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery

log = logging.getLogger(__name__)


class HttpLyricsProvider(ILyricsProvider):
    """Base for the HTTP lyrics sources, ported from Composer's lyrics-search providers. Every
    failure (timeout, 404, bot challenge, missing key) means "no results", never an exception,
    so one dead source cannot sink a search."""

    name = "http"

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        if not self.can_search(query):
            return []
        return await self._search(query)

    def can_search(self, query: LyricsQuery) -> bool:
        return bool(query.track and query.artist)

    async def _search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        raise NotImplementedError

    def _headers(self) -> dict | None:
        return None

    async def _get_json(self, url: str, params: dict):
        try:
            response = await self._client.get(url, params=params, headers=self._headers(),
                                              timeout=20)
        except httpx.HTTPError as error:
            log.warning("[%s] request failed: %s", self.name, error)
            return None
        if response.status_code == 404:
            return None
        if response.status_code == 401:
            log.warning("[%s] needs an API key for songs it has not cached "
                        "(AUTOLYRICS_BOIDU_API_KEY)", self.name)
            return None
        if not response.is_success:
            log.warning("[%s] returned %s", self.name, response.status_code)
            return None
        try:
            return response.json()
        except ValueError:
            log.warning("[%s] returned non-JSON (likely a bot challenge)", self.name)
            return None

    @staticmethod
    def _usable_duration(value) -> float | None:
        return float(value) if isinstance(value, (int, float)) and value > 0 else None
