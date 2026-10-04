import { ApiError, autolyrics } from "@/auto/api/autolyrics-client";
import { useJobLinkStore } from "@/auto/editor/job-link-store";
import { nextFrame } from "@/lib/frame-loop";
import { useAudioStore } from "@/stores/audio";
import { useProjectStore } from "@/stores/project";
import { Button } from "@/ui/button";
import { buttonClassName } from "@/ui/button-class-name";
import { Popover } from "@/ui/popover";
import { cn } from "@/utils/cn";
import { formatTime } from "@/utils/format-time";
import { generateTTML } from "@/utils/ttml";
import { revealTimeInMountedTimeline } from "@/views/timeline/scroll-helpers";
import {
  IconArrowLeft,
  IconCircleCheck,
  IconCircleDashed,
  IconDeviceFloppy,
  IconDownload,
  IconListCheck,
  IconLoader2,
} from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

// -- Constants ----------------------------------------------------------------

const DOWNLOADS: { name: string; label: string }[] = [
  { name: "lyrics.ttml", label: "TTML" },
  { name: "lyrics.word.lrc", label: "Word-synced LRC" },
  { name: "lyrics.lrc", label: "Line-synced LRC" },
  { name: "lyrics.srt", label: "SRT" },
  { name: "lyrics.qrc", label: "QRC" },
];

const JUMP_LEAD_IN = 0.75;

// -- Components ---------------------------------------------------------------

// Lines the backend flagged: jump the playhead there on the timeline and tick them off.
const ChecksMenu: React.FC = () => {
  const checks = useJobLinkStore((s) => s.checks);
  const toggleCheck = useJobLinkStore((s) => s.toggleCheck);
  const open = checks.filter((check) => !check.done).length;
  if (checks.length === 0) return null;

  const jump = (begin: number) => {
    useProjectStore.getState().setActiveTab("timeline");
    useAudioStore.getState().seekTo(Math.max(0, begin - JUMP_LEAD_IN));
    // The playhead only moves the view while playing; bring the line's word blocks on screen.
    nextFrame(() => revealTimeInMountedTimeline(begin));
  };

  return (
    <Popover
      placement="bottom-end"
      trigger={
        <button
          type="button"
          className={buttonClassName({ size: "sm", hasIcon: true, variant: open > 0 ? "secondary" : "ghost" })}
        >
          <IconListCheck size={14} className={open > 0 ? "text-composer-warning" : "text-composer-positive"} />
          {open > 0 ? `${open} to check` : "All checked"}
        </button>
      }
    >
      <ul className="flex max-h-96 w-96 flex-col overflow-y-auto p-1.5" aria-label="Lines to check">
        {checks.map((check, index) => (
          <li key={`${check.begin}-${check.label}`} className="flex items-start gap-1 rounded-lg hover:bg-composer-button">
            <button
              type="button"
              aria-label={check.done ? "Mark as not checked" : "Mark as checked"}
              onClick={() => toggleCheck(index)}
              className="p-2 text-composer-text-faint hover:text-composer-text"
            >
              {check.done ? (
                <IconCircleCheck size={16} className="text-composer-positive" />
              ) : (
                <IconCircleDashed size={16} />
              )}
            </button>
            <button
              type="button"
              onClick={() => jump(check.begin)}
              className="flex min-w-0 flex-1 flex-col py-1.5 pr-2 text-left"
            >
              <span className={cn("truncate text-sm", check.done ? "text-composer-text-faint line-through" : "text-composer-text")}>
                <span className="mr-2 text-xs tabular-nums text-composer-text-faint">{formatTime(check.begin, 0)}</span>
                {check.label}
              </span>
              <span className="truncate text-xs text-composer-text-muted">{check.reason}</span>
            </button>
          </li>
        ))}
      </ul>
    </Popover>
  );
};

const DownloadsMenu: React.FC<{ jobId: string }> = ({ jobId }) => (
  <Popover
    placement="bottom-end"
    hasPopup="menu"
    trigger={
      <button type="button" className={buttonClassName({ size: "sm", hasIcon: true, variant: "ghost" })}>
        <IconDownload size={14} />
        Files
      </button>
    }
  >
    <ul className="flex w-48 flex-col p-1.5">
      {DOWNLOADS.map(({ name, label }) => (
        <li key={name}>
          <a
            href={autolyrics.fileUrl(jobId, name)}
            download
            className="block rounded-lg px-2.5 py-1.5 text-sm text-composer-text hover:bg-composer-button"
          >
            {label}
          </a>
        </li>
      ))}
      <li className="px-2.5 pt-1.5 text-xs text-composer-text-faint">Save first to include your edits.</li>
    </ul>
  </Popover>
);

// Shown in the editor header when the project came from an autolyrics job.
const AutolyricsBar: React.FC = () => {
  const jobId = useJobLinkStore((s) => s.jobId);
  const title = useJobLinkStore((s) => s.title);
  const [saving, setSaving] = useState(false);
  if (!jobId) return null;

  // Writes the editor's TTML back to the job, which re-exports every format.
  const save = async () => {
    setSaving(true);
    try {
      const { metadata, agents, lines, groups } = useProjectStore.getState();
      const result = await autolyrics.saveTtml(jobId, generateTTML({ metadata, agents, lines, groups }));
      useProjectStore.getState().markClean();
      toast.success(`Saved to autolyrics (${result.sync} sync)`);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save to autolyrics");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <Link to="/" className={buttonClassName({ size: "sm", variant: "ghost", hasIcon: true })} title="All songs">
        <IconArrowLeft size={14} />
        <span className="max-w-48 truncate">{title ?? "Songs"}</span>
      </Link>
      <ChecksMenu />
      <DownloadsMenu jobId={jobId} />
      <Button size="sm" variant="primary" hasIcon disabled={saving} onClick={() => void save()}>
        {saving ? <IconLoader2 size={14} className="animate-spin" /> : <IconDeviceFloppy size={14} />}
        Save to autolyrics
      </Button>
    </div>
  );
};

// -- Exports ------------------------------------------------------------------

export { AutolyricsBar };
