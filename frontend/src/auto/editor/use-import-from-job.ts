import { autolyrics, type JobLyrics } from "@/auto/api/autolyrics-client";
import { saveLinkedJob } from "@/auto/editor/job-autosave";
import { type ReviewCheck, useJobLinkStore } from "@/auto/editor/job-link-store";
import { describeFlags, lineBounds, lineDisplay, needsReview } from "@/auto/review/flags";
import { DEFAULT_AGENTS } from "@/domain/agent/colors";
import { getPersistenceSettled } from "@/lib/persistence-settled";
import { useAudioStore } from "@/stores/audio";
import { useProjectStore } from "@/stores/project";
import { parseLyricsFile } from "@/utils/lyrics-parsers";
import { useEffect } from "react";
import { toast } from "sonner";

// -- Constants ----------------------------------------------------------------

const JOB_PARAM = "job";

// -- Helpers ------------------------------------------------------------------

function reviewChecks(lyrics: JobLyrics): ReviewCheck[] {
  return lyrics.lines.flatMap((line) => {
    const flagged = [...line.words, ...line.background].filter(needsReview);
    const bounds = lineBounds(line);
    if (flagged.length === 0 || !bounds) return [];
    const words = flagged.map((word) => word.text.trim()).join(", ");
    return [{ begin: bounds.begin, label: lineDisplay(line), reason: `${words}: ${describeFlags(flagged[0])}`, done: false }];
  });
}

function stripJobParam(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete(JOB_PARAM);
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
}

async function fetchJobFiles(
  jobId: string,
): Promise<{ ttml: string; audio: File; title: string | null; checks: ReviewCheck[] }> {
  const [job, lyrics, ttmlResponse, audioResponse] = await Promise.all([
    autolyrics.getJob(jobId),
    autolyrics.getLyrics(jobId),
    fetch(autolyrics.fileUrl(jobId, "lyrics.ttml")),
    fetch(autolyrics.audioUrl(jobId)),
  ]);
  if (!ttmlResponse.ok || !audioResponse.ok) throw new Error("the job's files are not available");
  const blob = await audioResponse.blob();
  const extension = blob.type === "audio/webm" ? "webm" : blob.type === "audio/mpeg" ? "mp3" : "m4a";
  const name = `${[job.artists.join(", "), job.title].filter(Boolean).join(" - ") || "song"}.${extension}`;
  return {
    ttml: await ttmlResponse.text(),
    audio: new File([blob], name, { type: blob.type }),
    title: job.title,
    checks: reviewChecks(lyrics),
  };
}

// -- Hook ---------------------------------------------------------------------

// `/editor?job=<id>` opens an autolyrics job in the editor on the timeline: its TTML becomes the
// project, its audio the song, and its flagged lines the "to check" list. The parameter is
// removed afterwards, so a reload keeps the edits instead of importing the job again.
function useImportFromJob(): void {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const jobId = new URLSearchParams(window.location.search).get(JOB_PARAM);
    if (!jobId) return;

    let cancelled = false;
    void (async () => {
      try {
        const files = await fetchJobFiles(jobId);
        await getPersistenceSettled();
        if (cancelled) return;

        // Opening a song always replaces the project; the previous song keeps its edits.
        if (useJobLinkStore.getState().jobId !== jobId) await saveLinkedJob();
        if (cancelled) return;

        const parsed = parseLyricsFile("lyrics.ttml", files.ttml);
        if (parsed.lines.length === 0) throw new Error("the job has no lyrics");

        const project = useProjectStore.getState();
        project.reset();
        const state = useProjectStore.getState();
        state.setMetadata(parsed.metadata);
        state.setLines(parsed.lines);
        state.setGroups(parsed.groups ?? []);
        state.setAgents(parsed.agents && parsed.agents.length > 0 ? parsed.agents : DEFAULT_AGENTS);
        state.setGranularity(parsed.lines.some((line) => line.words && line.words.length > 0) ? "word" : "line");
        state.clearHistory();
        state.markClean();
        useAudioStore.getState().setSource({ type: "file", file: files.audio });
        useJobLinkStore.getState().link(jobId, files.title, files.checks);
        // The aligned words are what to look at first: open where they can be dragged.
        useProjectStore.getState().setActiveTab("timeline");
        stripJobParam();
        toast.success(`Opened “${files.title ?? "song"}” from autolyrics`);
      } catch (error) {
        console.error("[autolyrics] could not open the job in the editor", error);
        toast.error("Could not open the song from autolyrics");
        stripJobParam();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);
}

// -- Exports ------------------------------------------------------------------

export { useImportFromJob };
