"""Build the alignment benchmark: songs whose word/syllable timing is already known.

    python scripts/collect_benchmark.py [benchmarks_dir]

For each song in SONGS it finds a syllable- or word-synced TTML (binimum; these are hand-made
Apple-style files), then a YouTube upload whose length matches that file within MAX_DRIFT
seconds (so the timing belongs to the same master), and downloads its audio through ArgonFetch.
Each song lands in <benchmarks_dir>/<slug>/ as source.*, truth.ttml and meta.json. Songs already
collected are skipped.
"""

import asyncio
import json
import re
import sys
import unicodedata
from pathlib import Path

import httpx

from autolyrics.domain.candidate import LyricsQuery
from autolyrics.domain.services.background_splitter import BackgroundSplitter
from autolyrics.domain.services.song_title_parser import SongTitleParser
from autolyrics.infrastructure.formats.ttml_format import TtmlFormat
from autolyrics.infrastructure.media.argonfetch import ArgonFetchMediaResolver, RetryPolicy
from autolyrics.infrastructure.providers.binimum import BinimumProvider

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

    @staticmethod
    def slug(artist: str, title: str) -> str:
        text = unicodedata.normalize("NFKC", f"{artist}-{title}").lower()
        return re.sub(r"[^\w]+", "-", text).strip("-")

    async def collect(self, artist: str, title: str) -> str:
        folder = self._root / self.slug(artist, title)
        if (folder / "meta.json").exists():
            return "already collected"
        candidates = await self._lyrics.search(LyricsQuery(track=title, artist=artist))
        timed = [c for c in candidates if c.declared_sync.is_word_level and c.duration]
        if not timed:
            return "no word-synced lyrics"
        truth = max(timed, key=lambda c: c.declared_sync.rank)
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

    async def run(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        for artist, title in SONGS:
            try:
                outcome = await self.collect(artist, title)
            except Exception as error:  # noqa: BLE001 - one song must not stop the collection
                outcome = f"failed: {error}"
            print(f"{artist} – {title}: {outcome}", flush=True)


async def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("benchmarks")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        await BenchmarkCollector(root, client).run()


if __name__ == "__main__":
    asyncio.run(main())
