import asyncio
import json
from dataclasses import dataclass

from mediatorx import UNIT, ICommand, ICommandHandler, Unit

from autolyrics.application.interfaces.audio import ITranscriber, IVocalSeparator
from autolyrics.application.interfaces.jobs import IJobRepository
from autolyrics.application.interfaces.llm import ILlmClient
from autolyrics.application.interfaces.progress import IProgress
from autolyrics.application.pipeline.context import PipelineContext
from autolyrics.application.pipeline.polish_prompt import PolishPrompt
from autolyrics.domain.job import Stage
from autolyrics.domain.services.decision_applier import DecisionApplier
from autolyrics.domain.services.source_comparer import SourceComparer


@dataclass
class PolishLyricsCommand(ICommand[Unit]):
    context: PipelineContext


class PolishLyricsHandler(ICommandHandler[PolishLyricsCommand, Unit]):
    """Cross-checks the chosen text against the other sources and lets the LLM pick where they
    disagree. Runs before alignment, so corrected text is what gets aligned. Optional: without a
    key, or when the LLM is unavailable, the lyrics stay as found."""

    WITNESS = "Whisper (machine transcription)"

    def __init__(self, llm: ILlmClient, comparer: SourceComparer, applier: DecisionApplier,
                 repository: IJobRepository, separator: IVocalSeparator,
                 transcriber: ITranscriber, witness: bool = False):
        # Whisper as a second opinion when every source has the same text. Off by default: it
        # costs a transcription per song and rarely changes a word.
        self._witness = witness
        self._separator = separator
        self._transcriber = transcriber
        self._llm = llm
        self._comparer = comparer
        self._applier = applier
        self._repository = repository

    def _needs_witness(self, ctx: PipelineContext) -> bool:
        chosen = ctx.chosen
        return (self._witness and ctx.audio is not None and chosen is not None
                and chosen.source not in ("user", "file") and "transcription" not in ctx.report)

    def _hear(self, ctx: PipelineContext, vocals, hearing: IProgress):
        try:
            return self._transcriber.transcribe(vocals, ctx.workspace,
                                                ctx.lyrics.metadata.language, hearing)
        except Exception:  # noqa: BLE001 - a second opinion only; the clean-up works without it
            return None
        finally:
            self._transcriber.release()

    async def handle(self, command: PolishLyricsCommand) -> Unit:
        ctx = command.context
        if ctx.lyrics is None:
            return UNIT
        if ctx.job.options.skip_llm:
            await ctx.reporter.skipped(Stage.POLISH, "LLM clean-up disabled")
            return UNIT
        if not self._llm.configured:
            await ctx.reporter.skipped(Stage.POLISH, "No LLM API key configured (AGENT_API_KEY)")
            return UNIT

        await ctx.reporter.running(Stage.POLISH, "Cross-checking sources and asking DeepSeek")
        others = [(c.label, c.lyrics) for c in ctx.candidates[1:] if c.lyrics is not None]
        versions = self._comparer.group(ctx.lyrics, others)
        if not versions and self._needs_witness(ctx):
            # Every source has the same text, so there is nothing to compare: what the recording
            # actually contains is the only second opinion left.
            await ctx.reporter.running(Stage.POLISH, "All sources agree; checking them against "
                                                     "what Whisper hears")
            try:
                stems = await ctx.stems(self._separator,
                                        ctx.reporter.progress(Stage.POLISH, "Isolating vocals"))
            except Exception:  # noqa: BLE001 - a second opinion only
                stems = None
            witness = None if stems is None else await asyncio.to_thread(
                self._hear, ctx, stems.vocals,
                ctx.reporter.progress(Stage.POLISH, "Listening (Whisper)"))
            if witness is not None:
                versions = [self._comparer.witness(self.WITNESS, witness)]
        decisions = self._comparer.decisions(ctx.lyrics, versions)
        chosen = ctx.report.get("chosen") or {}
        origin = f"{chosen.get('label', 'a lyrics source')} ({chosen.get('sync', 'unknown')} sync)"
        prompt = PolishPrompt(decisions, ctx.lyrics.metadata.title or "",
                              ctx.lyrics.metadata.artists, origin).render()
        self._repository.save_artifact(ctx.job.id, "llm-prompt.txt", prompt)
        try:
            answer = await self._llm.complete_json(PolishPrompt.SYSTEM, prompt)
        except Exception as error:  # noqa: BLE001 - the clean-up is a refinement, never a blocker
            ctx.report["polish"] = {"error": str(error)}
            await ctx.reporter.failed(Stage.POLISH,
                                      f"DeepSeek unavailable, lyrics left as found: {error}")
            return UNIT
        self._repository.save_artifact(ctx.job.id, "llm-answer.json",
                                       json.dumps(answer, indent=2, ensure_ascii=False))

        working = ctx.lyrics.model_copy(deep=True)
        try:
            changes = self._applier.apply(working, decisions, answer,
                                          word_synced=working.sync_type.is_word_level)
        except ValueError as error:
            ctx.report["polish"] = {"error": str(error)}
            await ctx.reporter.failed(Stage.POLISH, f"Could not apply DeepSeek's answer: {error}")
            return UNIT
        ctx.lyrics = working
        ctx.report["polish"] = {
            "sources_compared": [v.label for v in versions],
            "variants": len(decisions.variants),
            "insertion_candidates": len(decisions.insertions),
            "changes": changes,
        }
        applied = [c for c in changes if c["kind"] not in ("note", "rejected", "language")]
        notes = sum(c["kind"] == "note" for c in changes)
        await ctx.reporter.done(Stage.POLISH,
                                f"{len(versions)} other versions compared, {len(applied)} changes, "
                                f"{notes} notes for review", changes=changes)
        return UNIT
