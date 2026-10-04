import { useJobAutosave } from "@/auto/editor/job-autosave";
import { useImportFromJob } from "@/auto/editor/use-import-from-job";
import { AudioEngine } from "@/audio/audio-engine";
import { AudioPlayer } from "@/audio/audio-player";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useGlobalShortcuts } from "@/hooks/useGlobalShortcuts";
import { usePanicRecovery } from "@/hooks/usePanicRecovery";
import { usePersistence } from "@/hooks/usePersistence";
import { wireFrameLoop } from "@/lib/frame-loop-wiring";
import { useAudioStore } from "@/stores/audio";
import { useProjectStore } from "@/stores/project";
import { useUIStore } from "@/stores/ui";
import { AppHeader } from "@/ui/app-header";
import { ConfirmModalHost } from "@/ui/confirm-modal";
import { DivergenceModalHost } from "@/ui/divergence-modal";
import { HelpModal } from "@/ui/help-modal";
import { SettingsModal } from "@/ui/settings-modal";
import { APP_SETTING_LINK_HOST, SettingLinkContext } from "@/ui/setting-link-context";
import { TabBar } from "@/ui/tab-bar";
import { EditPanel } from "@/views/edit";
import { PreviewPanel } from "@/views/preview";
import { TimelinePanel } from "@/views/timeline/timeline-panel";
import { LazyMotion, domAnimation } from "motion/react";
import { Activity, useCallback, useEffect } from "react";
import { Toaster } from "sonner";

const AppContent: React.FC = () => {
  const activeTab = useProjectStore((s) => s.activeTab);
  const setActiveTab = useProjectStore((s) => s.setActiveTab);
  const source = useAudioStore((s) => s.source);
  const helpOpen = useUIStore((s) => s.helpOpen);
  const helpLocation = useUIStore((s) => s.helpLocation);
  const openHelp = useUIStore((s) => s.openHelp);
  const closeHelp = useUIStore((s) => s.closeHelp);
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const openSettings = useUIStore((s) => s.openSettings);
  const closeSettings = useUIStore((s) => s.closeSettings);

  useEffect(() => wireFrameLoop(), []);

  usePersistence();
  usePanicRecovery();
  useImportFromJob();
  useJobAutosave();
  useDocumentTitle();

  const setHelpOpenCb = useCallback((open: boolean) => (open ? openHelp() : closeHelp()), [openHelp, closeHelp]);
  const setSettingsOpenCb = useCallback(
    (open: boolean) => (open ? openSettings() : closeSettings()),
    [openSettings, closeSettings],
  );

  useGlobalShortcuts({
    setActiveTab,
    setHelpOpen: setHelpOpenCb,
    setSettingsOpen: setSettingsOpenCb,
  });

  return (
    <div className="flex flex-col h-screen bg-composer-bg text-composer-text">
      <AppHeader onSettingsOpen={() => openSettings()} onHelpOpen={() => openHelp()} />
      <HelpModal
        key={
          helpOpen
            ? `help-${helpLocation.section}-${helpLocation.scrollTop}-${helpLocation.query ?? ""}`
            : "help-closed"
        }
        isOpen={helpOpen}
        initialSection={helpLocation.section}
        initialScrollTop={helpLocation.scrollTop}
        initialQuery={helpLocation.query}
        onClose={closeHelp}
      />
      <SettingsModal
        key={settingsOpen ? "settings-open" : "settings-closed"}
        isOpen={settingsOpen}
        onClose={closeSettings}
      />
      <TabBar />
      <main className="relative flex-1 overflow-hidden">
        <Activity mode={activeTab === "edit" ? "visible" : "hidden"}>
          <div className="absolute inset-0 flex flex-col">
            <EditPanel />
          </div>
        </Activity>
        <Activity mode={activeTab === "timeline" ? "visible" : "hidden"}>
          <div className="absolute inset-0 flex flex-col">
            <TimelinePanel />
          </div>
        </Activity>
        <Activity mode={activeTab === "preview" ? "visible" : "hidden"}>
          <div className="absolute inset-0 flex flex-col">
            <PreviewPanel />
          </div>
        </Activity>
      </main>
      {source && <AudioEngine />}
      {source && <AudioPlayer />}
    </div>
  );
};

const App: React.FC = () => {
  return (
    <LazyMotion features={domAnimation} strict>
      <SettingLinkContext value={APP_SETTING_LINK_HOST}>
        <AppContent />
        <ConfirmModalHost />
        <DivergenceModalHost />
        <Toaster
          theme="dark"
          position="bottom-center"
          toastOptions={{
            style: {
              background: "var(--color-composer-bg-elevated)",
              border: "1px solid var(--color-composer-border)",
              color: "var(--color-composer-text)",
            },
          }}
        />
      </SettingLinkContext>
    </LazyMotion>
  );
};

export { App };
