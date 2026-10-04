"""Build the alignment benchmark: songs whose word/syllable timing is already known.

    python scripts/collect_benchmark.py [benchmarks_dir]
    python scripts/collect_benchmark.py training --charts=us,de,gb,fr,jp,kr,es,it,br,mx
    python scripts/collect_benchmark.py training --itunes=us,jp,kr --proxies=proxies.txt --workers=8

With --charts the songs come from Apple Music's public most-played charts of those countries
instead of SONGS (training data for the acoustic model); songs of the benchmark are skipped.

For each song in SONGS it finds a syllable- or word-synced TTML (binimum; these are hand-made
Apple-style files), then a YouTube upload whose length matches that file within MAX_DRIFT
seconds (so the timing belongs to the same master), and downloads its audio through ArgonFetch.
Each song lands in <benchmarks_dir>/<slug>/ as source.*, truth.ttml and meta.json. Songs already
collected are skipped.
"""

import asyncio
import json
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import ClassVar

import httpx

from autolyrics.domain.candidate import LyricsCandidate
from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.domain.services.song_title_parser import SongTitleParser
from autolyrics.infrastructure.clients.media.argonfetch import ArgonFetchMediaResolver, RetryPolicy
from autolyrics.infrastructure.clients.providers.binimum import BinimumProvider
from autolyrics.infrastructure.services.formats.ttml_format import TtmlFormat

# Chosen to be hard: fast rap, melisma, whisper, choirs and backing vocals, autotune, German and
# Japanese, plus the songs that broke the current aligner.
SONGS = [
    ("Eminem", "Rap God"),
    ("Whitney Houston", "I Will Always Love You"),
    ("Billie Eilish", "bad guy"),
    ("Queen", "Bohemian Rhapsody"),
    ("YOASOBI", "アイドル"),
    ("Rammstein", "Du hast"),
    ("Ariana Grande", "7 rings"),
    ("Adele", "Rolling in the Deep"),
    ("Daft Punk", "Get Lucky"),
    ("Sia", "Chandelier"),
    ("Kendrick Lamar", "HUMBLE."),
    ("Bruno Mars", "Uptown Funk"),
    ("Linkin Park", "Numb"),
    ("Mariah Carey", "All I Want for Christmas Is You"),
    ("BTS", "Dynamite"),
    ("Cro", "Easy"),
    ("Apache 207", "Roller"),
    ("Imagine Dragons", "Believer"),
    ("The Weeknd", "Blinding Lights"),
    ("Lorde", "Royals"),
    ("Kroi", "SPIN"),
    ("Alohaii", "Lovesick Loop"),
]

MAX_DRIFT = 2.0  # seconds the upload may differ from the lyrics' length
YOUTUBE_RESULTS = 6


class ProxyPool:
    """Proxies from a file, one per line: `host:port:user:pass` (Webshare) or a proxy URL.
    A proxy that fails or is refused rests for a while; the others carry on."""

    REST = 300.0  # seconds a failing proxy is left alone

    def __init__(self, path: Path | None):
        self.urls: list[str] = []
        if path is not None and path.exists():
            for line in path.read_text(encoding="utf-8").split():
                if "://" in line:
                    self.urls.append(line)
                elif line.count(":") == 3:
                    host, port, user, password = line.split(":")
                    self.urls.append(f"http://{user}:{password}@{host}:{port}")
        self.transports = {url: httpx.AsyncHTTPTransport(proxy=url, retries=0) for url in self.urls}
        self._resting: dict[str, float] = {}

    def __len__(self) -> int:
        return len(self.urls)

    def healthy(self, now: float) -> list[str]:
        return [u for u in self.urls if self._resting.get(u, 0.0) <= now]

    def rest(self, url: str, now: float) -> None:
        self._resting[url] = now + self.REST

    @staticmethod
    def label(url: str) -> str:
        return url.rsplit("@", 1)[-1]  # host:port, never the credentials

    async def aclose(self) -> None:
        for transport in self.transports.values():
            await transport.aclose()


class PoliteTransport(httpx.AsyncBaseTransport):
    """Every request of the collector goes through here: a minimum gap per host (and per proxy)
    so free services are not hammered, and retries with backoff when a host pushes back (429,
    5xx, dropped connections), honouring Retry-After.

    YouTube searches are spread over the proxies, each keeping its own gap; everything else goes
    out directly. lrc.red (binimum) is a free community service: its gap holds for the whole
    collector, however many workers or proxies there are."""

    GAPS: ClassVar = {"lyrics-api.binimum.org": 1.0, "lrc.red": 1.0, "www.youtube.com": 2.0,
                      "app.argonfetch.dev": 0.5}
    PROXIED: ClassVar = {"www.youtube.com"}
    DEFAULT_GAP = 0.5
    RETRIES = 5

    def __init__(self, proxies: ProxyPool | None = None):
        self._direct = httpx.AsyncHTTPTransport(retries=0)
        self._proxies = proxies or ProxyPool(None)
        self._next: dict[tuple[str, str], float] = {}
        self._lock = asyncio.Lock()
        self.throttled = 0

    async def _route(self, host: str) -> str:
        """Wait for a turn and pick the route ("" = direct, else a proxy URL)."""
        while True:
            async with self._lock:
                now = asyncio.get_running_loop().time()
                routes = [""]
                if host in self.PROXIED and len(self._proxies):
                    routes = self._proxies.healthy(now) or [""]
                route = min(routes, key=lambda r: self._next.get((host, r), 0.0))
                at = max(now, self._next.get((host, route), 0.0))
                self._next[(host, route)] = at + self.GAPS.get(host, self.DEFAULT_GAP)
            if at > now:
                await asyncio.sleep(at - now)
            return route

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        delay = 5.0
        host = request.url.host
        for attempt in range(self.RETRIES + 1):
            route = await self._route(host)
            transport = self._proxies.transports[route] if route else self._direct
            try:
                response = await transport.handle_async_request(request)
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError,
                    httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ProxyError):
                if route:
                    self._proxies.rest(route, asyncio.get_running_loop().time())
                    continue  # another proxy takes the request right away
                if attempt == self.RETRIES:
                    raise
            else:
                refused = response.status_code in (403, 429) and route
                if response.status_code not in (429, 500, 502, 503, 504) and not refused:
                    return response
                if attempt == self.RETRIES:
                    return response
                self.throttled += response.status_code == 429
                retry_after = response.headers.get("retry-after", "")
                await response.aclose()
                if route:
                    self._proxies.rest(route, asyncio.get_running_loop().time())
                    continue
                if retry_after.isdigit():
                    delay = max(delay, float(retry_after))
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300.0)
        raise RuntimeError("unreachable")

    async def aclose(self) -> None:
        await self._direct.aclose()
        await self._proxies.aclose()


class YouTubeSearch:
    """The first results of a YouTube search with their lengths, read from the results page."""

    BLOCK = '"videoRenderer":{"videoId":"'
    LENGTH = re.compile(r'"lengthText":\{"accessibility":\{[^}]*\}\},"simpleText":"([\d:]+)"')

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def search(self, query: str) -> list[tuple[str, float]]:
        response = await self._client.get(
            "https://www.youtube.com/results", params={"search_query": query},
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"}, timeout=20)
        found = []
        for block in response.text.split(self.BLOCK)[1:]:
            video_id = block[:11]
            # A block runs to the next video; live streams have no length.
            length_match = self.LENGTH.search(block[:20000])
            if length_match is None:
                continue
            length = length_match.group(1)
            seconds = 0
            for part in length.split(":"):
                seconds = seconds * 60 + int(part)
            if video_id not in [v for v, _ in found]:
                found.append((video_id, float(seconds)))
        return found[:YOUTUBE_RESULTS]


class BenchmarkCollector:
    def __init__(self, root: Path, client: httpx.AsyncClient):
        self._root = root
        self._client = client
        self._lyrics = BinimumProvider(client)
        self._youtube = YouTubeSearch(client)
        self._media = ArgonFetchMediaResolver(client, "https://app.argonfetch.dev",
                                              SongTitleParser(), RetryPolicy())
        self._ttml = TtmlFormat(BackgroundSplitter())

    # "(Remastered 2014)", "[Listenin' Continuous Album Mix]", "(feat. X)", "- Radio Edit": chart
    # titles carry release details the lyrics sources do not index.
    BRACKETED = re.compile(r"\s*[(\[]([^)\]]*)[)\]]")
    DASHED = re.compile(r"\s+-\s+(.*)$")
    RELEASE_WORDS = re.compile(r"\b(feat|with|from|remaster(ed)?|live|mix|edit|version|remix|"
                               r"sped up|slowed|acoustic|instrumental|bonus)\b", re.IGNORECASE)

    @classmethod
    def _release_detail(cls, match: re.Match) -> str:
        return "" if cls.RELEASE_WORDS.search(match.group(1)) else match.group(0)

    @classmethod
    def clean_title(cls, title: str) -> str:
        cleaned = cls.DASHED.sub(cls._release_detail, cls.BRACKETED.sub(cls._release_detail, title))
        return cleaned.strip() or title

    @staticmethod
    def slug(artist: str, title: str) -> str:
        text = unicodedata.normalize("NFKC", f"{artist}-{title}").lower()
        return re.sub(r"[^\w]+", "-", text).strip("-")

    async def collect(self, artist: str, title: str) -> str:
        folder = self._root / self.slug(artist, title)
        if (folder / "meta.json").exists():
            return "already collected"
        locks = self._root / ".locks"
        locks.mkdir(parents=True, exist_ok=True)
        lock = locks / self.slug(artist, title)
        # Several collectors may run at once: one song, one collector. A lock older than ten
        # minutes belongs to a collector that stopped, and the song is free again.
        if lock.exists() and time.time() - lock.stat().st_mtime < 600:
            return "taken by another collector"
        lock.write_text(str(os.getpid()))
        try:
            return await self._collect(artist, title, folder)
        finally:
            lock.unlink(missing_ok=True)

    async def _best_timed(self, artist: str, title: str) -> LyricsCandidate | None:
        """The search results say each file's timing; only the best syllable- or word-synced
        one is downloaded, instead of every result (the lyrics service is paced, so each
        download costs a second)."""
        body = await self._lyrics._get_json(self._lyrics.URL, {"track": title, "artist": artist})
        results = (body or {}).get("results") or [] if isinstance(body, dict) else []
        rank = {"syllable": 2, "word": 1}
        timed = [r for r in results if r.get("timing_type") in rank and r.get("duration")]
        if not timed:
            return None
        return await self._lyrics._fetch(max(timed, key=lambda r: rank[r["timing_type"]]))

    async def _collect(self, artist: str, title: str, folder: Path) -> str:
        truth = await self._best_timed(artist, title)
        if truth is None:
            return "no word-synced lyrics"
        lyrics = self._ttml.parse(truth.content)
        if not lyrics.sync_type.is_word_level:
            return f"lyrics parse as {lyrics.sync_type.value}"

        videos = await self._youtube.search(f"{artist} {title} official audio")
        matching = sorted((v for v in videos if abs(v[1] - truth.duration) <= MAX_DRIFT),
                          key=lambda v: abs(v[1] - truth.duration))
        if not matching:
            lengths = ", ".join(f"{s:.0f}s" for _, s in videos)
            return f"no upload of {truth.duration:.0f}s (found {lengths})"
        video_id, length = matching[0]
        track = await self._media.resolve(f"https://www.youtube.com/watch?v={video_id}")
        folder.mkdir(parents=True, exist_ok=True)
        audio = await self._media.download_audio(track, folder)
        (folder / "truth.ttml").write_text(truth.content, encoding="utf-8", newline="\n")
        meta = {"artist": artist, "title": title, "video_id": video_id, "audio": audio.name,
                "upload_seconds": length, "lyrics_seconds": truth.duration,
                "sync": lyrics.sync_type.value, "words": len(lyrics.all_words),
                "lyrics_source": truth.label, "lyrics_id": truth.source_id}
        (folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                                          encoding="utf-8", newline="\n")
        return f"ok: {lyrics.sync_type.value}, {len(lyrics.all_words)} words, video {video_id}"

    async def run(self, songs: list[tuple[str, str]] | None = None,
                  skip: set[str] | None = None, workers: int = 1) -> None:
        """`workers` songs at a time; the transport keeps every service's pace."""
        self._root.mkdir(parents=True, exist_ok=True)
        queue: asyncio.Queue = asyncio.Queue()
        for song in songs or SONGS:
            if not (skip and self.slug(*song) in skip):
                queue.put_nowait(song)

        async def worker() -> None:
            while not queue.empty():
                artist, title = queue.get_nowait()
                try:
                    outcome = await self.collect(artist, title)
                except Exception as error:  # noqa: BLE001 - one song must not stop the rest
                    outcome = f"failed: {error}"
                print(f"{artist} – {title}: {outcome}", flush=True)

        await asyncio.gather(*(worker() for _ in range(workers)))


class AppleCharts:
    """Apple Music's public most-played songs per country (no account needed)."""

    URL = "https://rss.marketingtools.apple.com/api/v2/{country}/music/most-played/100/songs.json"

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def songs(self, countries: list[str]) -> list[tuple[str, str]]:
        seen: dict[str, tuple[str, str]] = {}
        for country in countries:
            try:
                response = await self._client.get(self.URL.format(country=country), timeout=20)
                results = response.json()["feed"]["results"]
            except (httpx.HTTPError, ValueError, KeyError) as error:
                print(f"chart {country}: {error}")
                continue
            for r in results:
                # The main artist only: "A & B" credits rarely match the lyrics sources.
                artist = re.split(r" & |, | feat\. ", r["artistName"])[0]
                title = BenchmarkCollector.clean_title(r["name"])
                seen.setdefault(BenchmarkCollector.slug(artist, title), (artist, title))
        return list(seen.values())


class ItunesCharts:
    """The older iTunes feed: up to 200 top songs per country and genre, so many more songs (and
    more languages) than the most-played charts."""

    URL = "https://itunes.apple.com/{country}/rss/topsongs/limit=200{genre}/json"
    # Pop, hip-hop/rap, rock, R&B/soul, dance, alternative, latin, K-pop, J-pop, and all genres.
    GENRES = ("", "14", "18", "21", "15", "17", "20", "12", "51", "27")

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def songs(self, countries: list[str]) -> list[tuple[str, str]]:
        seen: dict[str, tuple[str, str]] = {}
        for country in countries:
            for genre in self.GENRES:
                url = self.URL.format(country=country, genre=f"/genre={genre}" if genre else "")
                try:
                    response = await self._client.get(url, timeout=20)
                    entries = response.json()["feed"].get("entry") or []
                except (httpx.HTTPError, ValueError, KeyError):
                    continue
                for e in entries if isinstance(entries, list) else [entries]:
                    artist = re.split(r" & |, | feat\. ", e["im:artist"]["label"])[0]
                    title = BenchmarkCollector.clean_title(e["im:name"]["label"])
                    seen.setdefault(BenchmarkCollector.slug(artist, title), (artist, title))
            print(f"chart {country}: {len(seen)} songs so far", flush=True)
        return list(seen.values())


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0]) if args else Path("benchmarks")
    charts = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--charts=")), None)
    itunes = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--itunes=")), None)
    proxy_file = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--proxies=")),
                      None)
    proxies = ProxyPool(Path(proxy_file) if proxy_file else None)
    workers = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--workers=")),
                       "1"))
    if len(proxies):
        print(f"{len(proxies)} proxies for YouTube, {workers} workers", flush=True)
    transport = PoliteTransport(proxies)
    async with httpx.AsyncClient(follow_redirects=True, transport=transport) as client:
        collector = BenchmarkCollector(root, client)
        if charts is None and itunes is None:
            await collector.run()
            return
        songs = (await AppleCharts(client).songs(charts.split(",")) if charts
                 else await ItunesCharts(client).songs(itunes.split(",")))
        random.Random(1).shuffle(songs)  # spread the languages; parallel collectors rarely meet
        benchmark = Path(__file__).resolve().parents[1] / "benchmarks"
        skip = {p.name for p in benchmark.iterdir()} if benchmark.exists() else set()
        print(f"{len(songs)} chart songs, {len(skip)} benchmark songs left out", flush=True)
        await collector.run(songs, skip, workers)


if __name__ == "__main__":
    asyncio.run(main())
