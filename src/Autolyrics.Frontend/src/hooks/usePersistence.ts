import { useJobLinkStore } from "@/auto/editor/job-link-store";
import { applySavedProject } from "@/lib/apply-saved-project";
import {
  clearAudioFile,
  loadAudioFile,
  saveAudioFile,
  type ProjectSaveInput,
  type SavedAudioSource,
} from "@/lib/persistence";
import { debouncedSave, flushPendingSave } from "@/lib/persistence-debounce";
import { markPersistenceSettled } from "@/lib/persistence-settled";
import { loadCurrentProjectWithPrimingMigration } from "@/lib/priming-migration";
import { type AudioSource, useAudioStore } from "@/stores/audio";
import { useProjectStore } from "@/stores/project";
import { useSettingsStore } from "@/stores/settings";
import { useEffect } from "react";

// -- Constants ----------------------------------------------------------------

const LOG_PREFIX = "[Persistence]";

// -- Helpers ------------------------------------------------------------------

function toSavedAudioSource(source: AudioSource): SavedAudioSource | undefined {
  return source ? { kind: "file", name: source.file.name } : undefined;
}

function playableFile(source: AudioSource): File | null {
  return source?.file ?? null;
}

function buildSaveInput(): ProjectSaveInput | null {
  const projectState = useProjectStore.getState();
  const liveAudioSource = useAudioStore.getState().source;
  // Skip only when the session is truly empty. Audio-loaded sessions need to
  // persist non-lyric fields like the audio source, even
  // before the user types any lyrics.
  const hasContent = projectState.lines.length > 0 || projectState.metadata.title;
  const hasContext = liveAudioSource !== null;
  if (!hasContent && !hasContext) return null;
  return {
    metadata: projectState.metadata,
    agents: projectState.agents,
    lines: projectState.lines,
    groups: projectState.groups,
    granularity: projectState.granularity,
    syllableSplitDefaults: projectState.syllableSplitDefaults,
    audioSource: toSavedAudioSource(liveAudioSource),
    dismissedSuggestions: projectState.dismissedSuggestions,
    dismissedExplicitSuggestions: projectState.dismissedExplicitSuggestions,
    primingStripped: projectState.primingStripped,
    customSnapPoints: projectState.customSnapPoints,
    hasUnexportedImport: projectState.hasUnexportedImport,
    importedMetadataKeys: projectState.importedMetadataKeys,
    ttmlEditState: projectState.ttmlEditState,
  };
}

function commitProjectSave(): void {
  const input = buildSaveInput();
  if (!input) return;
  debouncedSave(input);
}

// -- Hook ---------------------------------------------------------------------

function usePersistence(): void {
  useEffect(() => {
    Promise.all([loadCurrentProjectWithPrimingMigration(), loadAudioFile()])
      .then(([project, file]) => {
        if (file) useAudioStore.getState().setSource({ type: "file", file });
        if (project) {
          const issues = applySavedProject(project);
          if (issues.length > 0) {
            console.warn(
              `${LOG_PREFIX} loaded project has malformed fields (${issues.join(", ")}); using safe defaults. The raw record is still in IndexedDB; visit /recover to download it.`,
            );
          }
        }
      })
      .catch((err) => {
        console.error(`${LOG_PREFIX} initial load failed:`, err);
      })
      .finally(() => {
        if (import.meta.env.DEV) {
          console.log(`${LOG_PREFIX} settled`, {
            title: useProjectStore.getState().metadata.title,
            source: useAudioStore.getState().source,
          });
        }
        markPersistenceSettled();
      });
  }, []);

  useEffect(() => {
    const unsubscribe = useProjectStore.subscribe((state) => {
      if (!state.isDirty) return;
      commitProjectSave();
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    let prevSource = useAudioStore.getState().source;
    const unsubscribe = useAudioStore.subscribe((state) => {
      if (state.source === prevSource) return;
      const previous = prevSource;
      prevSource = state.source;

      const nextFile = playableFile(state.source);
      const prevFile = playableFile(previous);

      if (nextFile && nextFile !== prevFile) {
        saveAudioFile(nextFile).catch((err) => console.error(`${LOG_PREFIX} audio save failed:`, err));
        return;
      }
      if (!nextFile && prevFile) {
        clearAudioFile().catch((err) => console.error(`${LOG_PREFIX} audio clear failed:`, err));
      }
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    const unsubscribe = useAudioStore.subscribe((state, prev) => {
      if (state.volume === prev.volume) return;
      if (!useSettingsStore.getState().rememberVolume) return;
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        useSettingsStore.getState().set("lastVolume", state.volume);
      }, 500);
    });
    return () => {
      unsubscribe();
      if (debounceTimer) clearTimeout(debounceTimer);
    };
  }, []);

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Always flush so debounced saves (title edits, lyrics typing, anything
      // queued within the debounce window) land in IDB before the page closes.
      // The leave-confirmation prompt below stays gated on meaningful project
      // content so we don't nag on every audio-only reload.
      flushPendingSave();
      const state = useProjectStore.getState();
      // Songs from autolyrics save themselves back to the backend; only a free project can be lost.
      const savedElsewhere = useJobLinkStore.getState().jobId !== null;
      if (state.isDirty && state.lines.length > 0 && !savedElsewhere) {
        e.preventDefault();
        return "";
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);
}

// -- Exports ------------------------------------------------------------------

export { usePersistence };
