import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

// -- Types --------------------------------------------------------------------

interface ReviewCheck {
  // Where the line starts, for jumping the playhead there.
  begin: number;
  label: string;
  reason: string;
  done: boolean;
}

type SaveState = "saved" | "pending" | "saving" | "error";

interface JobLinkState {
  // The autolyrics job the editor's project came from, so edits can be saved back to it.
  jobId: string | null;
  title: string | null;
  // Lines the backend flagged for a human look; TTML carries no flags, so they live here.
  checks: ReviewCheck[];
  // Autosave status for the header; not persisted.
  saveState: SaveState;
}

interface JobLinkActions {
  link: (jobId: string, title: string | null, checks: ReviewCheck[]) => void;
  unlink: () => void;
  toggleCheck: (index: number) => void;
  setSaveState: (saveState: SaveState) => void;
}

// -- Store --------------------------------------------------------------------

const useJobLinkStore = create<JobLinkState & JobLinkActions>()(
  persist(
    (set) => ({
      jobId: null,
      title: null,
      checks: [],
      saveState: "saved",
      link: (jobId, title, checks) => set({ jobId, title, checks, saveState: "saved" }),
      unlink: () => set({ jobId: null, title: null, checks: [], saveState: "saved" }),
      setSaveState: (saveState) => set({ saveState }),
      toggleCheck: (index) =>
        set((state) => ({
          checks: state.checks.map((check, i) => (i === index ? { ...check, done: !check.done } : check)),
        })),
    }),
    {
      name: "autolyrics-job-link",
      storage: createJSONStorage(() => localStorage),
      partialize: ({ jobId, title, checks }) => ({ jobId, title, checks }),
    },
  ),
);

// -- Exports ------------------------------------------------------------------

export { useJobLinkStore };
export type { ReviewCheck, SaveState };
