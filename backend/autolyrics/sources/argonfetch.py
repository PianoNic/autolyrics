"""ArgonFetch: turns a song link into metadata and a downloadable audio stream."""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from autolyrics.config import settings

_YT_HOSTS = ("youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be")
# Bracketed decorations YouTube titles carry that are not part of the song title.
_NOISE_WORDS = (r"official|offiziell|lyric|audio|video|visuali[sz]er|\bhd\b|\b4k\b|explicit|clip|"
                r"out now|prod\.?|premiere|feat\.?|ft\.|remaster")
_BRACKETED_NOISE = re.compile(rf"\s*[\(\[][^\)\]]*(?:{_NOISE_WORDS})[^\)\]]*[\)\]]", re.IGNORECASE)
# Unbracketed tails: "Song prod. by X", "Song | A COLORS SHOW", "Song feat. X".
_TAIL_NOISE = re.compile(r"\s+(?:prod\.?\s+by\b.*|\|.*|(?:feat\.?|ft\.)\s.*)$", re.IGNORECASE)
_QUOTES = "\"'“”„‘’«»"


@dataclass
class AudioRendition:
    key: str
    url_type: str
    extension: str
    bitrate: float
    convert_to: str | None


@dataclass
class ResolvedTrack:
    source_url: str
    title: str | None
    artists: list[str]
    cover_url: str | None
    video_id: str | None
    audio: list[AudioRendition]

    def best_audio(self) -> AudioRendition:
        """Highest bitrate in the source container: no transcoding, so no added encoder delay."""
        native = [a for a in self.audio if a.convert_to is None] or self.audio
        if not native:
            raise ValueError("ArgonFetch returned no audio renditions")
        return max(native, key=lambda a: (a.bitrate, a.extension == ".m4a"))


def youtube_video_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.hostname not in _YT_HOSTS:
        return None
    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/") or None
    if parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
        return parsed.path.split("/")[2] or None
    return (parse_qs(parsed.query).get("v") or [None])[0]


def clean_youtube_title(title: str, author: str | None) -> tuple[str, list[str]]:
    """Split 'Artist - "Title" (Official Video) prod. by X' into title and artists."""
    artists = [author.removesuffix(" - Topic").strip()] if author else []
    if " - " in title:
        left, title = title.split(" - ", 1)
        artists = [a.strip() for a in re.split(r",|&| x | feat\.? ", left) if a.strip()]
    title = _BRACKETED_NOISE.sub("", title)
    title = _TAIL_NOISE.sub("", title).strip().strip(_QUOTES).strip()
    return title, artists


def _split_artists(author: str | None) -> list[str]:
    if not author:
        return []
    return [a.strip() for a in author.split(",") if a.strip()]


RETRIES = 3


async def _retry(make_call):
    """ArgonFetch occasionally drops a connection or answers 5xx while busy; try again."""
    for attempt in range(RETRIES):
        try:
            return await make_call()
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            transient = isinstance(error, httpx.TransportError) or error.response.status_code >= 500
            if not transient or attempt == RETRIES - 1:
                raise
            await asyncio.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


async def resolve(url: str, client: httpx.AsyncClient) -> ResolvedTrack:
    async def call():
        response = await client.get(f"{settings.argonfetch_base_url}/api/Fetch/GetResource",
                                    params={"url": url}, timeout=180)
        response.raise_for_status()
        return response.json()

    body = await _retry(call)
    if body.get("type") != "Media" or not body.get("mediaItems"):
        raise ValueError(f"ArgonFetch did not return a single track for {url} ({body.get('type')})")
    item = body["mediaItems"][0]

    audio = [
        AudioRendition(
            key=r["key"],
            url_type=(r.get("urlType") or "Media").lower(),
            extension=r.get("fileExtension") or "",
            bitrate=float(r.get("bitrate") or 0),
            convert_to=r.get("convertTo"),
        )
        for r in (item.get("audio") or {}).get("renditions", [])
    ]
    # For a Spotify link the top-level requestedUrl is the YouTube Music match ArgonFetch chose.
    video_id = youtube_video_id(body.get("requestedUrl")) or youtube_video_id(url)
    title = item.get("title") or body.get("title")
    author = item.get("author") or body.get("author")
    artists = _split_artists(author)

    if youtube_video_id(url):
        # A YouTube link carries the video's title, not the song's; Spotify links are clean.
        if title:
            title, artists = clean_youtube_title(title, author)
        elif video_id:
            title, artists = await _youtube_oembed(video_id, client)

    return ResolvedTrack(
        source_url=url,
        title=title,
        artists=artists,
        cover_url=item.get("coverUrl") or body.get("coverUrl"),
        video_id=video_id,
        audio=audio,
    )


async def _youtube_oembed(video_id: str, client: httpx.AsyncClient) -> tuple[str | None, list[str]]:
    """ArgonFetch leaves title and author empty for YouTube links; oEmbed fills them in."""
    try:
        response = await client.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None, []
    return clean_youtube_title(data.get("title") or "", data.get("author_name"))


async def download_audio(track: ResolvedTrack, dest_dir: Path, client: httpx.AsyncClient) -> Path:
    rendition = track.best_audio()
    url = f"{settings.argonfetch_base_url}/api/stream/{rendition.url_type}/{rendition.key}"
    if rendition.convert_to:
        url += f"?format={rendition.convert_to}"
    dest = dest_dir / f"source{rendition.extension or '.audio'}"
    if dest.exists() and dest.stat().st_size > 0:
        return dest  # a rerun of the same job keeps its audio (and the vocals made from it)
    partial = dest.with_suffix(dest.suffix + ".part")

    async def call():
        async with client.stream("GET", url, timeout=httpx.Timeout(30, read=300)) as response:
            response.raise_for_status()
            with partial.open("wb") as fh:
                async for chunk in response.aiter_bytes(1 << 16):
                    fh.write(chunk)

    await _retry(call)
    partial.replace(dest)
    if dest.stat().st_size == 0:
        raise ValueError("ArgonFetch returned an empty audio file")
    return dest
