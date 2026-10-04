import { ApiError, autolyrics, type Health, type JobSummary } from "@/auto/api/autolyrics-client";
import { JobStatusBadge } from "@/auto/ui/job-status-badge";
import { Button } from "@/ui/button";
import { IconButton } from "@/ui/icon-button";
import { INPUT_STYLES } from "@/ui/input-styles";
import { cn } from "@/utils/cn";
import { IconLink, IconLoader2, IconPlayerPlay, IconTrash } from "@tabler/icons-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

// -- Helpers ------------------------------------------------------------------

function formatCreated(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// -- Components ---------------------------------------------------------------

const BackendStatus: React.FC<{ health: Health | null; error: string | null }> = ({ health, error }) => {
  if (error) {
    return (
      <p className="text-xs text-composer-error-text" role="alert">
        The autolyrics backend is not reachable. Start it with <code>autolyrics serve</code>.
      </p>
    );
  }
  if (!health) return null;
  return (
    <p className="text-xs text-composer-text-faint">
      Backend {health.version} · DeepSeek clean-up {health.llm ? "on" : "off (no API key)"}
      {health.lyrics_api_key ? "" : " · Better Lyrics: cached songs only (no API key)"}
    </p>
  );
};

const RecentJobs: React.FC<{ jobs: JobSummary[]; onDelete: (id: string) => void }> = ({ jobs, onDelete }) => {
  if (jobs.length === 0) return null;
  return (
    <section aria-labelledby="recent-heading" className="flex flex-col gap-2">
      <h2 id="recent-heading" className="text-sm font-medium text-composer-text-secondary">
        Recent songs
      </h2>
      <ul className="flex flex-col divide-y divide-composer-border rounded-lg border border-composer-border">
        {jobs.map((job) => (
          <li key={job.id} className="flex items-center gap-3 px-3 py-2">
            {job.cover_url ? (
              <img src={job.cover_url} alt="" className="size-9 rounded object-cover" />
            ) : (
              <div className="size-9 rounded bg-composer-button" />
            )}
            <Link to={`/jobs/${job.id}`} className="flex min-w-0 flex-1 flex-col hover:text-composer-text">
              <span className="truncate text-sm text-composer-text">{job.title ?? job.url}</span>
              <span className="truncate text-xs text-composer-text-muted">
                {job.artists.join(", ") || "Unknown artist"} · {formatCreated(job.created)}
              </span>
            </Link>
            {job.status === "done" && job.flagged !== null && job.flagged > 0 && (
              <span className="text-xs text-composer-warning">{job.flagged} to check</span>
            )}
            <JobStatusBadge status={job.status} />
            <IconButton
              variant="ghost"
              label={`Delete ${job.title ?? "job"}`}
              icon={<IconTrash size={16} />}
              disabled={job.status === "queued" || job.status === "running"}
              onClick={() => onDelete(job.id)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
};

const StartPage: React.FC = () => {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [skipLlm, setSkipLlm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    autolyrics
      .listJobs()
      .then(setJobs)
      .catch(() => setJobs([]));
  }, []);

  useEffect(() => {
    autolyrics
      .health()
      .then(setHealth)
      .catch((cause: unknown) => setHealthError(String(cause)));
    refresh();
  }, [refresh]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await autolyrics.createJob({
        url: url.trim(),
        title: title.trim() || undefined,
        artist: artist.trim() || undefined,
        skip_llm: skipLlm,
      });
      navigate(`/jobs/${job.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not start the job.");
      setSubmitting(false);
    }
  };

  const remove = async (id: string) => {
    await autolyrics.deleteJob(id).catch(() => undefined);
    refresh();
  };

  return (
    <main className="min-h-screen bg-composer-bg text-composer-text">
      <div className="mx-auto flex max-w-2xl flex-col gap-8 px-4 py-12">
        <header className="flex flex-col gap-1">
          <h1 className="flex items-center gap-2.5 text-2xl font-semibold">
            <img src="/logo.svg" alt="" className="size-8" />
            autolyrics
          </h1>
          <p className="text-sm text-composer-text-muted">
            Paste a song link and get word-synced lyrics. Fix anything you like afterwards, or open the full editor.
          </p>
        </header>

        <form onSubmit={submit} className="flex flex-col gap-3" aria-label="Start a song">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-composer-text-secondary">Song link</span>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <IconLink
                  size={16}
                  className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-composer-text-faint"
                />
                <input
                  type="url"
                  required
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://open.spotify.com/track/… or a YouTube link"
                  className={cn(INPUT_STYLES, "w-full pl-8")}
                />
              </div>
              <Button type="submit" variant="primary" hasIcon disabled={submitting || !url.trim()}>
                {submitting ? <IconLoader2 size={16} className="animate-spin" /> : <IconPlayerPlay size={16} />}
                Start
              </Button>
            </div>
          </label>

          <details className="text-sm">
            <summary className="cursor-pointer text-composer-text-muted hover:text-composer-text">
              Options
            </summary>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-composer-text-muted">Title (if detection gets it wrong)</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} className={INPUT_STYLES} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-composer-text-muted">Artist</span>
                <input value={artist} onChange={(event) => setArtist(event.target.value)} className={INPUT_STYLES} />
              </label>
              <label className="col-span-2 flex items-center gap-2 text-composer-text-secondary">
                <input type="checkbox" checked={skipLlm} onChange={(event) => setSkipLlm(event.target.checked)} />
                Skip the DeepSeek clean-up
              </label>
            </div>
          </details>

          {error && (
            <p role="alert" className="text-sm text-composer-error-text">
              {error}
            </p>
          )}
          <BackendStatus health={health} error={healthError} />
        </form>

        <RecentJobs jobs={jobs} onDelete={remove} />

        <footer className="text-xs text-composer-text-faint">
          Built on <a href="https://github.com/better-lyrics/composer" className="underline">Composer</a> by
          Better Lyrics. <Link to="/editor" className="underline">Open the editor</Link> without a song.
        </footer>
      </div>
    </main>
  );
};

// -- Exports ------------------------------------------------------------------

export default StartPage;
export { StartPage };
