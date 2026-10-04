import { IconButton } from "@/ui/icon-button";
import { AutolyricsBar } from "@/auto/editor/autolyrics-bar";
import { IconHelp, IconSettings } from "@tabler/icons-react";

interface AppHeaderProps {
  onSettingsOpen: () => void;
  onHelpOpen: () => void;
}

const AppHeader: React.FC<AppHeaderProps> = ({ onSettingsOpen, onHelpOpen }) => (
  <header className="flex items-center justify-between p-4 border-b select-none border-composer-border">
    <h1 className="text-xl font-semibold">
      <img src="/logo.svg" alt="" className="inline-block size-6 mr-2 -mt-1" />
      autolyrics
    </h1>
    <div className="flex items-center gap-1">
      <AutolyricsBar />
      <IconButton
        label="Settings"
        icon={<IconSettings className="size-5" />}
        variant="ghost"
        onClick={onSettingsOpen}
      />
      <IconButton
        label="Keyboard shortcuts (?)"
        icon={<IconHelp className="size-5" />}
        variant="ghost"
        onClick={onHelpOpen}
      />
    </div>
  </header>
);

export { AppHeader };
