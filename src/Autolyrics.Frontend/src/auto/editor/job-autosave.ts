import { autolyrics } from "@/auto/api/autolyrics-client";
import { useJobLinkStore } from "@/auto/editor/job-link-store";
import { useProjectStore } from "@/stores/project";
import { generateTTML } from "@/utils/ttml";
import { useEffect } from "react";

// -- Constants ----------------------------------------------------------------

const AUTOSAVE_DELAY_MS = 1500;

// -- Helpers ------------------------------------------------------------------

function currentTtml(): string {
  const { metadata, agents, lines, groups } = useProjectStore.getState();
  return generateTTML({ metadata, agents, lines, groups });
}

// Writes the editor's project back to the song it came from, when there is anything to write.
async function saveLinkedJob(): Promise<void> {
  const { jobId, setSaveState } = useJobLinkStore.getState();
  const project = useProjectStore.getState();
  if (!jobId) return;
  if (!project.isDirty || project.lines.length === 0) {
    setSaveState("saved");
    return;
  }
  setSaveState("saving");
  try {
    await autolyrics.saveTtml(jobId, currentTtml());
    // Only clean if nothing changed while the request was in flight.
    if (useJobLinkStore.getState().jobId === jobId) useProjectStore.getState().markClean();
    setSaveState("saved");
  } catch (error) {
    console.error("[autolyrics] autosave failed", error);
    setSaveState("error");
  }
}

// On leaving the page there is no time to await a request; keepalive lets it finish anyway.
function flushOnLeave(): void {
  const { jobId } = useJobLinkStore.getState();
  const project = useProjectStore.getState();
  if (!jobId || !project.isDirty || project.lines.length === 0) return;
  void fetch(autolyrics.ttmlUrl(jobId), {
    method: "PUT",
    headers: { "content-type": "application/ttml+xml" },
    body: currentTtml(),
    keepalive: true,
  }).catch(() => undefined);
}

// -- Hook ---------------------------------------------------------------------

// Songs from autolyrics are saved back to the backend as you edit, so there is no save button to
// remember and nothing to lose when switching songs or closing the tab. Returns the cleanup.
function startJobAutosave(): () => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const unsubscribe = useProjectStore.subscribe((state, previous) => {
    const unchanged =
      state.lines === previous.lines &&
      state.metadata === previous.metadata &&
      state.agents === previous.agents &&
      state.groups === previous.groups;
    if (!state.isDirty || unchanged) return;
    if (!useJobLinkStore.getState().jobId) return;
    useJobLinkStore.getState().setSaveState("pending");
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void saveLinkedJob(), AUTOSAVE_DELAY_MS);
  });
  window.addEventListener("pagehide", flushOnLeave);
  return () => {
    unsubscribe();
    if (timer) clearTimeout(timer);
    window.removeEventListener("pagehide", flushOnLeave);
  };
}

function useJobAutosave(): void {
  useEffect(() => startJobAutosave(), []);
}

// -- Exports ------------------------------------------------------------------

export { saveLinkedJob, startJobAutosave, useJobAutosave };
