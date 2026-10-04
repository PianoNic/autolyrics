import asyncio
import time
from dataclasses import dataclass

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.interfaces.audio import ILyricsAligner, ITranscriber, IVocalSeparator
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.domain.job import Stage
from autolyrics.domain.lyrics import SyncType
from autolyrics.domain.services.line_anchorer import LineAnchorer


@dataclass
class AlignLyricsCommand(ICommand[Unit]):
    context: PipelineContext


class AlignLyricsHandler(ICommandHandler[AlignLyricsCommand, Unit]):
    """Isolates the vocals, then either times every word (line-synced or plain text) or checks
    a word-synced source's timing against them and shifts it when it sits consistently off."""

    def __init__(self, separator: IVocalSeparator, aligner: ILyricsAligner,
                 transcriber: ITranscriber, anchorer: LineAnchorer,
                 offset_min: float = 0.12, offset_max_spread: float = 0.15):
        self._separator = separator
        self._aligner = aligner
        self._transcriber = transcriber
        self._anchorer = anchorer
        self._offset_min = offset_min  # shift when the source sits at least this far off...
        self._offset_max_spread = offset_max_spread  # ...and its words agree on the shift

    async def handle(self, command: AlignLyricsCommand) -> Unit:
        ctx = command.context
        if ctx.lyrics is None:
            raise await ctx.reporter.fail(Stage.ALIGN, "No lyrics to align")
        word_level = ctx.lyrics.sync_type.is_word_level
        await ctx.reporter.running(Stage.ALIGN, "Isolating vocals (Demucs)")
        started = time.time()
        try:
            vocals = await asyncio.to_thread(self._separator.separate, ctx.audio, ctx.workspace)
            await ctx.reporter.running(
                Stage.ALIGN, f"Vocals isolated in {time.time() - started:.0f}s; "
                + ("checking the source's timing against them" if word_level else "aligning words"))
            if word_level:
                result = await asyncio.to_thread(self._check_offset, ctx, vocals)
            else:
                if ctx.lyrics.sync_type == SyncType.UNSYNCED:
                    await ctx.reporter.running(
                        Stage.ALIGN, "No line times; finding where each line is sung (Whisper)")
                    ctx.report["anchoring"] = await asyncio.to_thread(self._anchor, ctx, vocals)
                result = await asyncio.to_thread(self._aligner.align, ctx.lyrics, vocals,
                                                 ctx.workspace)
        except Exception as error:  # model, decoder and memory errors alike
            raise await ctx.reporter.fail(Stage.ALIGN, str(error)) from error
        finally:
            self._aligner.release()

        if "transcription" in ctx.report:
            # Machine-heard text: every word is a guess until someone has read it.
            for word in ctx.lyrics.all_words:
                word.flag("transcribed")

        if word_level:
            ctx.report["offset_check"] = result
            label = (ctx.report.get("chosen") or {}).get("label", "The source")
            message = (f"{label} timing kept, shifted {result['offset'] * 1000:+.0f} ms onto "
                       f"this audio" if result["applied"]
                       else f"{label} timing kept ({result['reason']})")
            await ctx.reporter.done(Stage.ALIGN, message, **result)
        else:
            ctx.report["alignment"] = result
            await ctx.reporter.done(
                Stage.ALIGN, f"{result['words']} words aligned, {result['low_confidence']} "
                f"uncertain, {result['interpolated']} interpolated", **result)
        return UNIT

    def _anchor(self, ctx: PipelineContext, vocals) -> dict:
        """Plain text has no line times, and a whole song is a lot to align blind: a
        transcription knows where lines are sung even where it misheard them."""
        try:
            heard = self._transcriber.transcribe(vocals, ctx.workspace,
                                                 ctx.lyrics.metadata.language)
        except Exception as error:  # noqa: BLE001 - only a timing aid; alignment works without it
            return {"matched_lines": 0, "error": str(error)}
        finally:
            self._transcriber.release()
        matched = self._anchorer.anchor(ctx.lyrics, heard, ctx.duration or 0.0)
        return {"matched_lines": matched, "lines": len(ctx.lyrics.content_lines)}

    def _check_offset(self, ctx: PipelineContext, vocals) -> dict:
        check = self._aligner.measure_offset(ctx.lyrics, vocals, ctx.workspace)
        # Shift only for a clear, consistent offset; a spread-out difference means the aligner
        # disagrees word by word, and the source's own timing is the better bet.
        if check["spread"] is None:
            return {**check, "applied": False, "reason": "too few confident words to compare"}
        if abs(check["offset"]) < self._offset_min:
            return {**check, "applied": False, "reason": "already in sync"}
        if check["spread"] > self._offset_max_spread:
            return {**check, "applied": False, "reason": "offset not consistent"}
        ctx.lyrics.shift(check["offset"])
        return {**check, "applied": True, "reason": "consistent offset"}
