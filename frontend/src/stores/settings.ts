import { PREVIEW_SIDEBAR_WIDTH } from "@/utils/preview-sidebar-width";
import { DEFAULT_MIN_WORD_DURATION } from "@/utils/word-spaces";
import { create } from "zustand";
import { persist } from "zustand/middleware";

// -- Types --------------------------------------------------------------------

type GranularityDefault = "word" | "line";
type LinkedDivergenceAction = "ask" | "apply" | "detach";

interface SettingsState {
  defaultPlaybackRate: number;
  preservePitch: boolean;
  rememberVolume: boolean;
  lastVolume: number;
  audioScrubPreview: boolean;

  defaultZoom: number;
  defaultRowHeight: number;
  followPlayhead: boolean;
  defaultRollingEdit: boolean;
  defaultPreviewSidebar: boolean;
  previewSidebarWidth: number;
  timelineSnap: boolean;
  timelineSnapThreshold: number;
  snapPlayheadToPoints: boolean;
  syllablesFollowRolling: boolean;
  timelineHorizontalScroll: boolean;

  nudgeAmount: number;
  defaultWordDuration: number;
  minWordDuration: number;
  defaultGranularity: GranularityDefault;

  autoSaveDelay: number;

  showShortcutHints: boolean;
  showSyllableIndicators: boolean;
  splitCharacter: string;
  autoExtractBackgroundVocals: boolean;
  mergeStandaloneBackgroundLines: boolean;
  preserveBracketsOnExtraction: boolean;

  confirmResetSettings: boolean;
  confirmResetShortcuts: boolean;
  confirmGroupDissolution: boolean;
  confirmApplyToAllSyllableSplit: boolean;
  confirmConformToGroup: boolean;
  linkedDivergenceAction: LinkedDivergenceAction;
}

interface SettingsActions {
  set: <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => void;
  resetToDefaults: () => void;
}

// -- Defaults -----------------------------------------------------------------

const DEFAULTS: SettingsState = {
  defaultPlaybackRate: 0.75,
  preservePitch: true,
  rememberVolume: true,
  lastVolume: 1,
  audioScrubPreview: true,

  defaultZoom: 100,
  defaultRowHeight: 44,
  followPlayhead: true,
  defaultRollingEdit: false,
  defaultPreviewSidebar: false,
  previewSidebarWidth: PREVIEW_SIDEBAR_WIDTH.default,
  timelineSnap: true,
  timelineSnapThreshold: 12,
  snapPlayheadToPoints: true,
  syllablesFollowRolling: false,
  timelineHorizontalScroll: false,

  nudgeAmount: 0.05,
  defaultWordDuration: 0.3,
  minWordDuration: DEFAULT_MIN_WORD_DURATION,
  defaultGranularity: "word",

  autoSaveDelay: 2000,

  showShortcutHints: true,
  showSyllableIndicators: true,
  splitCharacter: "|",
  autoExtractBackgroundVocals: true,
  mergeStandaloneBackgroundLines: true,
  preserveBracketsOnExtraction: true,

  confirmResetSettings: true,
  confirmResetShortcuts: true,
  confirmGroupDissolution: true,
  confirmApplyToAllSyllableSplit: true,
  confirmConformToGroup: true,
  linkedDivergenceAction: "ask",
};

const SETTINGS_PERSIST_VERSION = 8;

// Settings of features this build no longer has (YouTube import, vocal separation, the other
// preview renderers, the Sync tab, URL and file imports). Older blobs still carry them.
const RETIRED_SETTING_KEYS = [
  "previewRenderer",
  "autoSeparateOnImport",
  "vocalModelVariant",
  "vocalOnsetSnap",
  "cobaltInstances",
  "selectedCobaltInstanceId",
  "cobaltInstanceStatus",
  "experiments",
  "composerBridgeUrl",
  "redoPreroll",
  "confirmReplaceProjectFromHash",
  "confirmReplaceLyrics",
  "confirmSyncReset",
  "confirmClearProject",
  "confirmClearImportedSongDetails",
] as const;

function migrateSettings(persistedState: unknown, version: number): unknown {
  if (!persistedState || typeof persistedState !== "object") return persistedState;
  // The store merges a persisted blob over the defaults as is, so a retired key would otherwise
  // ride along in state and be written back on every save.
  const raw: Record<string, unknown> = { ...persistedState };
  for (const key of RETIRED_SETTING_KEYS) delete raw[key];
  const next = raw as Partial<SettingsState>;
  if (next.defaultRollingEdit === undefined) next.defaultRollingEdit = false;
  if (next.defaultPreviewSidebar === undefined) next.defaultPreviewSidebar = false;
  if (next.snapPlayheadToPoints === undefined) next.snapPlayheadToPoints = true;
  // The key predates the default flip, so every old blob carries an explicit
  // false that a plain undefined guard would never reach.
  if (version < 6) next.preserveBracketsOnExtraction = true;
  return next;
}

// -- Store --------------------------------------------------------------------

const useSettingsStore = create<SettingsState & SettingsActions>()(
  persist(
    (set) => ({
      ...DEFAULTS,

      set: (key, value) => set({ [key]: value }),
      resetToDefaults: () =>
        set((state) => ({
          ...DEFAULTS,
          confirmResetSettings: state.confirmResetSettings,
          confirmResetShortcuts: state.confirmResetShortcuts,
          confirmGroupDissolution: state.confirmGroupDissolution,
          confirmApplyToAllSyllableSplit: state.confirmApplyToAllSyllableSplit,
          confirmConformToGroup: state.confirmConformToGroup,
          linkedDivergenceAction: state.linkedDivergenceAction,
        })),
    }),
    { name: "composer-settings", version: SETTINGS_PERSIST_VERSION, migrate: migrateSettings },
  ),
);

// -- Exports ------------------------------------------------------------------

export { useSettingsStore, DEFAULTS, migrateSettings as migrateSettingsForTest };
export type { SettingsState, LinkedDivergenceAction };
