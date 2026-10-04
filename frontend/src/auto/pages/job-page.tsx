import { type JobDetail, autolyrics } from "@/auto/api/autolyrics-client";
import { type StageView, stageViews, useJobEvents } from "@/auto/api/use-job-events";
import { JobStatusBadge } from "@/auto/ui/job-status-badge";
import { ProgressBar } from "@/auto/ui/progress-bar";
import { cn } from "@/utils/cn";
import {
  IconArrowLeft,
  IconCircle,
  IconCircleCheck,
  IconCircleMinus,
  IconCircleX,
  IconLoader2,
} from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

// -- Constants ----------------------------------------------------------------

const STAGE_LABELS: Record<StageView["stage"], string> = {
  resolve: "Find the song",
  audio: "Download audio",
  lyrics: "Search lyrics",
  polish: "DeepSeek clean-up",
  align: "Time every word",
  export: "Check and export",
};

// -- Components ---------------------------------------------------------------

const StageIcon: React.FC<{ status: StageView["status"] }> = ({ status }) => {
  switch (status) {
    case "running":
      return <IconLoader2 size={18} className="animate-spin text-composer-accent" aria-label="running" />;
    case "done":
      return <IconCircleCheck size={18} className="text-composer-positive" aria-label="done" />;
    case "skipped":
      return <IconCircleMinus size={18} className="text-composer-text-faint" aria-label="skipped" />;
    case "failed":
      return <IconCircleX size={18} className="text-composer-negative" aria-label="failed" />;
    default:
      return <IconCircle size={18} className="text-composer-text-disabled" aria-label="pending" />;
  }
};

/** The live bar of a running stage: its current step's share, or a stripe while it cannot tell. */
const StageProgressRow: React.FC<{ stage: StageView }> = ({ stage }) => {
  const progress = stage.progress;
  const label = progress?.label ?? STAGE_LABELS[stage.stage];
  const percent = progress?.fraction == null ? null : `${Math.round(progress.fraction * 100)}%`;
  const caption = [progress?.label, progress?.detail, percent].filter(Boolean).join(" · ");
  return (
    <div className="mt-1.5 flex flex-col gap-1">
      <ProgressBar fraction={progress?.fraction ?? null} label={label} />
      {caption && <span className="text-xs tabular-nums text-composer-text-faint">{caption}</span>}
    </div>
  );
};

const StageList: React.FC<{ stages: StageView[] }> = ({ stages }) => (
  <ol className="flex flex-col gap-2" aria-label="Progress">
    {stages.map((stage) => (
      <li key={stage.stage} data-stage={stage.stage} data-status={stage.status} className="flex items-start gap-3">
        <span className="mt-0.5">
          <StageIcon status={stage.status} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span
            className={cn("text-sm", stage.status === "pending" ? "text-composer-text-faint" : "text-composer-text")}
          >
            {STAGE_LABELS[stage.stage]}
            {stage.started !== null && stage.finished !== null && (
              <span className="ml-2 text-xs text-composer-text-faint">
                {Math.max(0, stage.finished - stage.started).toFixed(1)}s
              </span>
            )}
          </span>
          {stage.message && <span className="text-xs text-composer-text-muted">{stage.message}</span>}
          {stage.status === "running" && <StageProgressRow stage={stage} />}
        </div>
      </li>
    ))}
  </ol>
);

const JobPage: React.FC = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const live = useJobEvents(jobId);
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // The detail (report, title) is fetched once and again when the job finishes.
  // biome-ignore lint/correctness/useExhaustiveDependencies: live.status is the refetch trigger
  useEffect(() => {
    if (!jobId) return;
    autolyrics
      .getJob(jobId)
      .then(setJob)
      .catch((cause: unknown) => setLoadError(String(cause)));
  }, [jobId, live.status]);

  const navigate = useNavigate();
  const status = live.status ?? job?.status ?? null;

  // A finished song opens in the editor: its timeline already holds every aligned word.
  useEffect(() => {
    if (status === "done" && jobId) navigate(`/editor?job=${encodeURIComponent(jobId)}`, { replace: true });
  }, [status, jobId, navigate]);
  const stages = stageViews(live.events.length > 0 ? live.events : (job?.events ?? []), live.progress);
  const error = live.error ?? job?.error ?? null;

  return (
    <main className="min-h-screen bg-composer-bg text-composer-text">
      <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8">
        <nav>
          <Link
            to="/"
            className="inline-flex items-center gap-1 text-sm text-composer-text-muted hover:text-composer-text"
          >
            <IconArrowLeft size={16} /> All songs
          </Link>
        </nav>

        <header className="flex items-center gap-4">
          {job?.cover_url && <img src={job.cover_url} alt="" className="size-16 rounded-md object-cover" />}
          <div className="flex min-w-0 flex-1 flex-col">
            <h1 className="truncate text-xl font-semibold">{job?.title ?? "Working on it…"}</h1>
            <p className="truncate text-sm text-composer-text-muted">{job?.artists.join(", ") || job?.url}</p>
          </div>
          {status && <JobStatusBadge status={status} />}
        </header>

        {loadError && !job && (
          <p role="alert" className="text-sm text-composer-error-text">
            Could not load this job: {loadError}
          </p>
        )}

        <StageList stages={stages} />

        {status === "failed" && error && (
          <p role="alert" className="rounded-md bg-composer-error/25 px-3 py-2 text-sm text-composer-negative">
            {error}
          </p>
        )}
      </div>
    </main>
  );
};

// -- Exports ------------------------------------------------------------------

export default JobPage;
export { JobPage, StageList };
