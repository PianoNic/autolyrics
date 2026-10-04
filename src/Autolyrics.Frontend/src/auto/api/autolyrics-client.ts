// Typed client for the local autolyrics backend (`autolyrics serve`). The shapes mirror the
// backend's DTOs in backend/autolyrics/application/jobs/dtos.py and domain/lyrics.py.

// -- Types --------------------------------------------------------------------

type JobStatus = "queued" | "running" | "done" | "failed";
type Stage = "resolve" | "audio" | "lyrics" | "polish" | "align" | "export";
type StageStatus = "running" | "done" | "skipped" | "failed";

interface JobEvent {
  stage: Stage;
  status: StageStatus;
  message: string;
  data: Record<string, unknown>;
  at: number;
}

/** Live progress of one step of a running stage; `fraction` is null when it cannot tell. */
interface StageProgress {
  stage: Stage;
  label: string;
  fraction: number | null;
  detail: string;
}

interface JobSummary {
  id: string;
  status: JobStatus;
  created: number;
  error: string | null;
  url: string;
  title: string | null;
  artists: string[];
  cover_url: string | null;
  sync: string | null;
  flagged: number | null;
  words: number | null;
}

interface PolishChange {
  kind: "variant" | "insert" | "remove" | "spelling" | "note" | "rejected" | "language";
  line?: number;
  from?: string;
  to?: string;
  text?: string;
  note?: string;
  reason?: string | null;
  sources?: string[] | string;
  why?: string;
}

interface JobReport {
  chosen?: { label: string; sync: string; source: string } | null;
  polish?: { changes?: PolishChange[]; sources_compared?: string[]; error?: string };
  alignment?: Record<string, unknown>;
  offset_check?: Record<string, unknown>;
  validation?: { flagged_words: number; total_words: number; by_issue: Record<string, number> };
  output?: Record<string, string>;
  audio?: { duration: number };
}

interface JobDetail extends JobSummary {
  events: JobEvent[];
  report: JobReport;
}

interface LyricWord {
  text: string;
  begin: number | null;
  end: number | null;
  confidence: number | null;
  flags: string[];
}

interface LyricLine {
  words: LyricWord[];
  background: LyricWord[];
  agent: string;
  begin: number | null;
  end: number | null;
}

interface JobLyrics {
  lines: LyricLine[];
  agents: { id: string; type: string; name: string | null }[];
  metadata: {
    title: string | null;
    artists: string[];
    album: string | null;
    language: string | null;
    duration: number | null;
    songwriters: string[];
  };
}

interface CreateJobInput {
  url: string;
  title?: string;
  artist?: string;
  album?: string;
  skip_llm?: boolean;
}

interface SaveResult {
  validation: { flagged_words: number; total_words: number };
  sync: string;
  files: Record<string, string>;
}

interface RealignResult extends SaveResult {
  aligned: boolean;
  line: LyricLine;
}

interface Health {
  ok: boolean;
  version: string;
  llm: boolean;
  lyrics_api_key: boolean;
}

type StreamPayload =
  | { type: "status"; status: JobStatus; error: string | null }
  | { type: "event"; event: JobEvent }
  | ({ type: "progress" } & StageProgress);

// -- Errors -------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// -- Client -------------------------------------------------------------------

const API_ROOT = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Not JSON; keep the status text.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

const autolyrics = {
  health: () => request<Health>("/health"),
  listJobs: () => request<JobSummary[]>("/jobs"),
  getJob: (id: string) => request<JobDetail>(`/jobs/${encodeURIComponent(id)}`),
  createJob: (input: CreateJobInput) => request<JobSummary>("/jobs", json("POST", input)),
  deleteJob: (id: string) => request<void>(`/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  getLyrics: (id: string) => request<JobLyrics>(`/jobs/${encodeURIComponent(id)}/lyrics`),
  saveLyrics: (id: string, lyrics: JobLyrics) =>
    request<SaveResult>(`/jobs/${encodeURIComponent(id)}/lyrics`, json("PUT", lyrics)),
  saveTtml: (id: string, ttml: string) =>
    request<SaveResult>(`/jobs/${encodeURIComponent(id)}/ttml`, {
      method: "PUT",
      headers: { "content-type": "application/ttml+xml" },
      body: ttml,
    }),
  realignLine: (id: string, index: number, text?: string) =>
    request<RealignResult>(
      `/jobs/${encodeURIComponent(id)}/lines/${index}/realign`,
      json("POST", text === undefined ? {} : { text }),
    ),
  audioUrl: (id: string) => `${API_ROOT}/jobs/${encodeURIComponent(id)}/audio`,
  fileUrl: (id: string, name: string) => `${API_ROOT}/jobs/${encodeURIComponent(id)}/files/${name}`,
  eventsUrl: (id: string) => `${API_ROOT}/jobs/${encodeURIComponent(id)}/events`,
  ttmlUrl: (id: string) => `${API_ROOT}/jobs/${encodeURIComponent(id)}/ttml`,
};

// -- Exports ------------------------------------------------------------------

export { ApiError, autolyrics };
export type {
  Health,
  JobDetail,
  JobEvent,
  JobLyrics,
  JobStatus,
  JobSummary,
  LyricLine,
  LyricWord,
  Stage,
  StageProgress,
  StreamPayload,
};
