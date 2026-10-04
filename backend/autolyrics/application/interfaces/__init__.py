"""Ports: what the application needs from the outside world. Infrastructure implements them."""

from autolyrics.application.interfaces.audio import IAudioTools, ILyricsAligner, IVocalSeparator
from autolyrics.application.interfaces.jobs import (
    IJobEventBroadcaster,
    IJobQueue,
    IJobRepository,
    IJobSubscription,
)
from autolyrics.application.interfaces.llm import ILlmClient
from autolyrics.application.interfaces.lyrics import (
    ILyricsExporter,
    ILyricsFormats,
    ILyricsProvider,
)
from autolyrics.application.interfaces.media import IMediaResolver

__all__ = [
    "IAudioTools",
    "IJobEventBroadcaster",
    "IJobQueue",
    "IJobRepository",
    "IJobSubscription",
    "ILlmClient",
    "ILyricsAligner",
    "ILyricsExporter",
    "ILyricsFormats",
    "ILyricsProvider",
    "IMediaResolver",
    "IVocalSeparator",
]
