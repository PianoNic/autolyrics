import logging
import re
from typing import ClassVar

import httpx

from autolyrics.domain.candidate import LyricsCandidate, LyricsQuery
from autolyrics.domain.lyrics import SyncType
from autolyrics.infrastructure.providers.http_provider import HttpLyricsProvider

log = logging.getLogger(__name__)


class AppleWebToken:
    """The developer token Apple's own web player (music.apple.com) uses for its API calls. It is
    embedded in the player's script and changes every few months, so it is read from there and
    kept until Apple rejects it."""

    PAGE = "https://music.apple.com/us/browse"
    SCRIPT = re.compile(r'/assets/index~[\w-]+\.js')
    TOKEN = re.compile(r'eyJ0eXAi[\w-]*\.[\w-]+\.[\w-]+')

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._token: str | None = None

    async def get(self) -> str | None:
        if self._token is None:
            self._token = await self._fetch()
        return self._token

    def forget(self) -> None:
        self._token = None

    async def _fetch(self) -> str | None:
        try:
            page = await self._client.get(self.PAGE, headers=AppleMusicProvider.BROWSER,
                                          timeout=20, follow_redirects=True)
            script = self.SCRIPT.search(page.text)
            if script is None:
                log.warning("[apple] web player script not found")
                return None
            js = await self._client.get(f"https://music.apple.com{script.group(0)}",
                                        headers=AppleMusicProvider.BROWSER, timeout=30)
        except httpx.HTTPError as error:
            log.warning("[apple] could not load the web player: %s", error)
            return None
        token = self.TOKEN.search(js.text)
        if token is None:
            log.warning("[apple] no token in the web player script")
        return token.group(0) if token else None


class AppleMusicProvider(HttpLyricsProvider):
    """Apple Music's own lyrics (the source most other services copy), read with the user's own
    subscription: the `media-user-token` cookie of a logged-in music.apple.com tab. Without that
    token Apple answers lyrics requests with 404, so the provider stays silent."""

    name = "apple"
    API = "https://amp-api.music.apple.com/v1"
    BROWSER: ClassVar = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"}
    TIMING = re.compile(r'itunes:timing="(\w+)"')
    SONGS = 3  # search results whose lyrics are fetched

    def __init__(self, client: httpx.AsyncClient, user_token: str | None,
                 storefront: str | None = None, web_token: AppleWebToken | None = None):
        super().__init__(client)
        self._user_token = (user_token or "").strip() or None
        self._storefront = storefront
        self._web_token = web_token or AppleWebToken(client)

    def can_search(self, query: LyricsQuery) -> bool:
        return self._user_token is not None and super().can_search(query)

    async def _search(self, query: LyricsQuery) -> list[LyricsCandidate]:
        storefront = await self._ensure_storefront()
        if storefront is None:
            return []
        body = await self._api(f"/catalog/{storefront}/search",
                               {"term": f"{query.artist} {query.track}", "types": "songs",
                                "limit": 5})
        songs = (((body or {}).get("results") or {}).get("songs") or {}).get("data") or []
        found = []
        for song in [s for s in songs if (s.get("attributes") or {}).get("hasLyrics")][:self.SONGS]:
            candidate = await self._lyrics(storefront, song)
            if candidate is not None:
                found.append(candidate)
        return found

    async def _lyrics(self, storefront: str, song: dict) -> LyricsCandidate | None:
        attributes = song.get("attributes") or {}
        kinds = (["syllable-lyrics", "lyrics"] if attributes.get("hasTimeSyncedLyrics")
                 else ["lyrics"])
        for kind in kinds:
            body = await self._api(f"/catalog/{storefront}/songs/{song['id']}/{kind}", {})
            ttml = self._ttml(body)
            if not ttml:
                continue
            duration = attributes.get("durationInMillis")
            return LyricsCandidate(
                self.name, "Apple Music", "ttml", ttml, self._sync(ttml, kind),
                attributes.get("name"), attributes.get("artistName"),
                duration / 1000 if isinstance(duration, (int, float)) else None, song["id"])
        return None

    @staticmethod
    def _ttml(body) -> str | None:
        data = (body or {}).get("data") or []
        attributes = (data[0].get("attributes") or {}) if data else {}
        ttml = attributes.get("ttml")
        if not ttml:
            localized = attributes.get("ttmlLocalizations")
            ttml = localized if isinstance(localized, str) else None
        return ttml or None

    def _sync(self, ttml: str, kind: str) -> SyncType:
        timing = self.TIMING.search(ttml)
        value = timing.group(1).lower() if timing else "line"
        if value == "word":
            return SyncType.SYLLABLE if kind == "syllable-lyrics" else SyncType.WORD
        return SyncType.LINE if value == "line" else SyncType.UNSYNCED

    async def _ensure_storefront(self) -> str | None:
        if self._storefront is None:
            body = await self._api("/me/storefront", {})
            data = (body or {}).get("data") or []
            self._storefront = data[0].get("id") if data else None
            if self._storefront is None:
                log.warning("[apple] could not read the account's storefront; is "
                            "AUTOLYRICS_APPLE_MUSIC_USER_TOKEN current?")
        return self._storefront

    async def _api(self, path: str, params: dict, retry: bool = True):
        token = await self._web_token.get()
        if token is None:
            return None
        headers = {**self.BROWSER, "Authorization": f"Bearer {token}",
                   "media-user-token": self._user_token or "",
                   "Origin": "https://music.apple.com", "Referer": "https://music.apple.com/"}
        try:
            response = await self._client.get(f"{self.API}{path}", params=params,
                                              headers=headers, timeout=20)
        except httpx.HTTPError as error:
            log.warning("[apple] request failed: %s", error)
            return None
        if response.status_code == 401 and retry:
            self._web_token.forget()  # Apple rotated the web player's token
            return await self._api(path, params, retry=False)
        if response.status_code in (401, 403):
            log.warning("[apple] refused (%s): the Apple Music token has probably expired",
                        response.status_code)
            return None
        if not response.is_success:
            return None
        try:
            return response.json()
        except ValueError:
            return None
