import type { JobStatus } from "@/auto/api/autolyrics-client";
import { cn } from "@/utils/cn";

// -- Constants ----------------------------------------------------------------

const LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Working",
  done: "Done",
  failed: "Failed",
};

const STYLES: Record<JobStatus, string> = {
  queued: "bg-composer-button text-composer-text-muted",
  running: "bg-composer-accent/15 text-composer-accent-text",
  done: "bg-composer-positive/10 text-composer-positive",
  failed: "bg-composer-error/25 text-composer-negative",
};

// -- Component ----------------------------------------------------------------

const JobStatusBadge: React.FC<{ status: JobStatus; className?: string }> = ({ status, className }) => (
  <span
    data-status={status}
    className={cn("inline-flex h-5 items-center rounded-md px-1.5 text-[11px] font-medium", STYLES[status], className)}
  >
    {LABELS[status]}
  </span>
);

// -- Exports ------------------------------------------------------------------

export { JobStatusBadge };
