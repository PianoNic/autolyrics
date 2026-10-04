from dataclasses import dataclass, field


@dataclass
class AudioRendition:
    key: str
    url_type: str
    extension: str
    bitrate: float
    convert_to: str | None


@dataclass
class Track:
    """A song as the media resolver found it."""

    source_url: str
    title: str | None
    artists: list[str]
    cover_url: str | None = None
    # The YouTube video the audio comes from; some lyrics sources key on it.
    video_id: str | None = None
    audio: list[AudioRendition] = field(default_factory=list)

    def best_audio(self) -> AudioRendition:
        """Highest bitrate in the source container: no transcoding, so no added encoder delay."""
        native = [a for a in self.audio if a.convert_to is None] or self.audio
        if not native:
            raise ValueError("no audio renditions available")
        return max(native, key=lambda a: (a.bitrate, a.extension == ".m4a"))

    def summary(self) -> dict:
        return {"title": self.title, "artists": self.artists, "video_id": self.video_id,
                "cover_url": self.cover_url}
