import re


class SongTitleParser:
    """Turns a video title like 'Artist - "Title" (Official Video) prod. by X' into the song."""

    NOISE_WORDS = (r"official|offiziell|lyric|audio|video|visuali[sz]er|\bhd\b|\b4k\b|explicit|clip|"
                   r"out now|prod\.?|premiere|feat\.?|ft\.|remaster")
    BRACKETED_NOISE = re.compile(rf"\s*[\(\[][^\)\]]*(?:{NOISE_WORDS})[^\)\]]*[\)\]]", re.IGNORECASE)
    # Unbracketed tails: "Song prod. by X", "Song | A COLORS SHOW", "Song feat. X".
    TAIL_NOISE = re.compile(r"\s+(?:prod\.?\s+by\b.*|\|.*|(?:feat\.?|ft\.)\s.*)$", re.IGNORECASE)
    ARTIST_SEPARATORS = re.compile(r",|&| x | feat\.? ")
    QUOTES = "\"'“”„‘’«»"

    def parse(self, title: str, channel: str | None) -> tuple[str, list[str]]:
        artists = [channel.removesuffix(" - Topic").strip()] if channel else []
        if " - " in title:
            left, title = title.split(" - ", 1)
            artists = [a.strip() for a in self.ARTIST_SEPARATORS.split(left) if a.strip()]
        title = self.BRACKETED_NOISE.sub("", title)
        title = self.TAIL_NOISE.sub("", title).strip().strip(self.QUOTES).strip()
        return title, artists
