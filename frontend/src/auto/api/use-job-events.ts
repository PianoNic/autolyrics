import {
  type JobEvent,
  type JobStatus,
  type Stage,
  type StageProgress,
  type StreamPayload,
  autolyrics,
} from "@/auto/api/autolyrics-client";
import { useEffect, useState } from "react";

// -- Types --------------------------------------------------------------------

interface StageView {
  stage: Stage;
  status: JobEvent["status"] | "pending";
  message: string;
  started: number | null;
  finished: number | null;
  progress: StageProgress | null;
}

interface JobEventsState {
  status: JobStatus | null;
  error: string | null;
  events: JobEvent[];
  progress: Partial<Record<Stage, StageProgress>>;
}

// -- Constants ----------------------------------------------------------------

const STAGES: Stage[] = ["resolve", "audio", "lyrics", "polish", "align", "export"];
const FINAL: ReadonlySet<JobStatus> = new Set(["done", "failed"]);

// -- Helpers ------------------------------------------------------------------

function stageViews(events: JobEvent[], progress: JobEventsState["progress"] = {}): StageView[] {
  return STAGES.map((stage) => {
    const own = events.filter((event) => event.stage === stage);
    const last = own.at(-1);
    const done = own.find((event) => event.status !== "running");
    const status = last?.status ?? "pending";
    return {
      stage,
      status,
      message: last?.message ?? "",
      started: own[0]?.at ?? null,
      finished: done?.at ?? null,
      progress: status === "running" ? (progress[stage] ?? null) : null,
    };
  });
}

// -- Hook ---------------------------------------------------------------------

// The server replays a job's history on every connection (status first, then the events) before
// streaming live ones, so the event list restarts whenever the stream (re)opens. The server ends
// the stream once the job is finished; EventSource reports that as an error and would reconnect,
// so a final status closes it there instead.
function useJobEvents(jobId: string | undefined): JobEventsState {
  const [state, setState] = useState<JobEventsState>({ status: null, error: null, events: [], progress: {} });

  useEffect(() => {
    if (!jobId) return;
    let finished = false;
    const source = new EventSource(autolyrics.eventsUrl(jobId));
    source.onopen = () => setState((previous) => ({ ...previous, events: [], progress: {} }));
    source.onmessage = (message) => {
      const payload = JSON.parse(message.data) as StreamPayload;
      if (payload.type === "status") {
        finished = FINAL.has(payload.status);
        setState((previous) => ({ ...previous, status: payload.status, error: payload.error }));
      } else if (payload.type === "progress") {
        const { type: _, ...progress } = payload;
        setState((previous) => ({ ...previous, progress: { ...previous.progress, [progress.stage]: progress } }));
      } else {
        setState((previous) => ({ ...previous, events: [...previous.events, payload.event] }));
      }
    };
    source.onerror = () => {
      if (finished) source.close();
    };
    return () => source.close();
  }, [jobId]);

  return state;
}

// -- Exports ------------------------------------------------------------------

export { stageViews, useJobEvents };
export type { StageView };
