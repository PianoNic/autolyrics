import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from autolyrics.application.interfaces.media import IMediaResolver
from autolyrics.domain.services.song_title_parser import SongTitleParser
from autolyrics.domain.track import AudioRendition, Track


class YouTubeLink:
    HOSTS = ("youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be")

    @classmethod
    def video_id(cls, url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.hostname not in cls.HOSTS:
            return None
        if parsed.hostname == "youtu.be":
            return parsed.path.strip("/") or None
        if parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            return parsed.path.split("/")[2] or None
        return (parse_qs(parsed.query).get("v") or [None])[0]


class RetryPolicy:
    """Retries transient HTTP failures: dropped connections and 5xx answers."""

    def __init__(self, attempts: int = 3, backoff: float = 2.0):
        self._attempts = attempts
        self._backoff = backoff

    async def run(self, call):
        for attempt in range(self._attempts):
            try:
                return await call()
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                transient = (isinstance(error, httpx.TransportError)
                             or error.response.status_code >= 500)
                if not transient or attempt == self._attempts - 1:
                    raise
                await asyncio.sleep(self._backoff * (attempt + 1))
        raise AssertionError("unreachable")


class ArgonFetchMediaResolver(IMediaResolver):
    """ArgonFetch turns a song link into metadata and a downloadable audio stream. For a Spotify
    link it also picks the matching YouTube Music upload, whose id some lyrics sources need."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, titles: SongTitleParser,
                 retry: RetryPolicy):
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._titles = titles
        self._retry = retry

    async def resolve(self, url: str) -> Track:
        body = await self._retry.run(lambda: self._get_resource(url))
        if body.get("type") != "Media" or not body.get("mediaItems"):
            raise ValueError(f"ArgonFetch did not return a single track for {url} "
                             f"({body.get('type')})")
        item = body["mediaItems"][0]
        audio = [
            AudioRendition(key=r["key"], url_type=(r.get("urlType") or "Media").lower(),
                           extension=r.get("fileExtension") or "",
                           bitrate=float(r.get("bitrate") or 0), convert_to=r.get("convertTo"))
            for r in (item.get("audio") or {}).get("renditions", [])
        ]
        # For a Spotify link the top-level requestedUrl is the YouTube Music match it chose.
        video_id = YouTubeLink.video_id(body.get("requestedUrl")) or YouTubeLink.video_id(url)
        title = item.get("title") or body.get("title")
        author = item.get("author") or body.get("author")
        artists = [a.strip() for a in (author or "").split(",") if a.strip()]

        if YouTubeLink.video_id(url):
            # A YouTube link carries the video's title, not the song's; Spotify links are clean.
            if title:
                title, artists = self._titles.parse(title, author)
            elif video_id:
                title, artists = await self._youtube_oembed(video_id)

        return Track(source_url=url, title=title, artists=artists,
                     cover_url=item.get("coverUrl") or body.get("coverUrl"), video_id=video_id,
                     audio=audio)

    async def _get_resource(self, url: str) -> dict:
        response = await self._client.get(f"{self._base_url}/api/Fetch/GetResource",
                                          params={"url": url}, timeout=180)
        response.raise_for_status()
        return response.json()

    async def _youtube_oembed(self, video_id: str) -> tuple[str | None, list[str]]:
        """When ArgonFetch leaves the title empty, YouTube's oEmbed fills it in."""
        try:
            response = await self._client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                timeout=20)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return None, []
        return self._titles.parse(data.get("title") or "", data.get("author_name"))

    async def download_audio(self, track: Track, directory: Path) -> Path:
        rendition = track.best_audio()
        url = f"{self._base_url}/api/stream/{rendition.url_type}/{rendition.key}"
        if rendition.convert_to:
            url += f"?format={rendition.convert_to}"
        dest = directory / f"source{rendition.extension or '.audio'}"
        if dest.exists() and dest.stat().st_size > 0:
            return dest  # a rerun keeps its audio (and the vocals made from it)
        partial = dest.with_suffix(dest.suffix + ".part")

        async def stream() -> None:
            async with self._client.stream("GET", url,
                                           timeout=httpx.Timeout(30, read=300)) as response:
                response.raise_for_status()
                with partial.open("wb") as fh:
                    async for chunk in response.aiter_bytes(1 << 16):
                        fh.write(chunk)

        await self._retry.run(stream)
        partial.replace(dest)
        if dest.stat().st_size == 0:
            raise ValueError("ArgonFetch returned an empty audio file")
        return dest
