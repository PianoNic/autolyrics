import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useAudioStore } from "@/stores/audio";
import type { SimpleTab } from "@/stores/project";

interface GlobalShortcutActions {
  setActiveTab: (tab: SimpleTab) => void;
  setHelpOpen: (open: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
}

function togglePlayback(): void {
  const { isPlaying, setIsPlaying } = useAudioStore.getState();
  setIsPlaying(!isPlaying);
}

function useGlobalShortcuts(actions: GlobalShortcutActions): void {
  const { setActiveTab, setHelpOpen, setSettingsOpen } = actions;

  useKeyboardShortcuts({
    "global.goToEdit": () => setActiveTab("edit"),
    "global.goToTimeline": () => setActiveTab("timeline"),
    "global.goToPreview": () => setActiveTab("preview"),
    "global.playPause": togglePlayback,
    "global.help": () => setHelpOpen(true),
    "global.settings": () => setSettingsOpen(true),
  });
}

export { useGlobalShortcuts };
