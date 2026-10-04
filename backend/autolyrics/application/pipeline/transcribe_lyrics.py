import asyncio
import time
from dataclasses import dataclass

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.interfaces.audio import ITranscriber, IVocalSeparator
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.domain.job import Stage
from autolyrics.domain.services.lyrics_tidier import LyricsTidier


@dataclass
class TranscribeLyricsCommand(ICommand[Unit]):
    context: PipelineContext


class TranscribeLyricsHandler(ICommandHandler[TranscribeLyricsCommand, Unit]):
    """The fallback when no lyrics source has the song (or transcription was asked for): Whisper
    hears the isolated vocals. The result is a rough draft; every word stays flagged for review
    and lyrics platforms that refuse AI transcriptions should get a corrected version."""

    def __init__(self, separator: IVocalSeparator, transcriber: ITranscriber,
                 tidier: LyricsTidier):
        self._tidier = tidier
        self._separator = separator
        self._transcriber = transcriber

    async def handle(self, command: TranscribeLyricsCommand) -> Unit:
        ctx = command.context
        if ctx.lyrics is not None:
            return UNIT
        await ctx.reporter.running(Stage.LYRICS, "No lyrics to start from; transcribing the vocals "
                                                 "with Whisper")
        started = time.time()
        try:
            vocals = await asyncio.to_thread(
                self._separator.separate, ctx.audio, ctx.workspace,
                ctx.reporter.progress(Stage.LYRICS, "Isolating vocals"))
            lyrics = await asyncio.to_thread(
                self._transcriber.transcribe, vocals, ctx.workspace, None,
                ctx.reporter.progress(Stage.LYRICS, "Transcribing (Whisper)"))
        except Exception as error:  # model, decoder and memory errors alike
            raise await ctx.reporter.fail(Stage.LYRICS, f"transcription failed: {error}") from error
        finally:
            self._transcriber.release()
        if not lyrics.lines:
            raise await ctx.reporter.fail(Stage.LYRICS, "Whisper heard no vocals in this song")

        self._tidier.tidy(lyrics)
        lyrics.metadata.title = ctx.track.title
        lyrics.metadata.artists = list(ctx.track.artists)
        lyrics.metadata.duration = ctx.duration
        ctx.lyrics = lyrics
        ctx.report["transcription"] = {
            "language": lyrics.metadata.language, "lines": len(lyrics.lines),
            "words": len(lyrics.all_words), "seconds": round(time.time() - started, 1)}
        ctx.report["chosen"] = {"source": "whisper", "label": "Whisper transcription",
                                "sync": "line"}
        await ctx.reporter.done(Stage.LYRICS,
                                f"Transcribed {len(lyrics.lines)} lines "
                                f"({lyrics.metadata.language or 'unknown language'}); "
                                f"every word needs a check", **ctx.report["transcription"])
        return UNIT
