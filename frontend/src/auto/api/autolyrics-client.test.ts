import { ApiError, type JobEvent, autolyrics } from "@/auto/api/autolyrics-client";
import { stageViews } from "@/auto/api/use-job-events";
import { afterEach, describe, expect, it, vi } from "vitest";

// -- Helpers ------------------------------------------------------------------

function respond(status: number, body?: unknown) {
  const response = new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
}

function event(stage: JobEvent["stage"], status: JobEvent["status"], at: number, message = ""): JobEvent {
  return { stage, status, message, data: {}, at };
}

// -- Tests --------------------------------------------------------------------

describe("autolyrics client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts new jobs as JSON", async () => {
    const fetch = respond(201, { id: "job-1" });
    await expect(autolyrics.createJob({ url: "https://x" })).resolves.toEqual({ id: "job-1" });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/jobs");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ url: "https://x" });
  });

  it("turns the backend's error detail into an ApiError", async () => {
    respond(409, { detail: "the job has not finished" });
    const failure = autolyrics.realignLine("job-1", 0);
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 409, message: "the job has not finished" });
  });

  it("returns nothing for 204 answers", async () => {
    respond(204);
    await expect(autolyrics.deleteJob("job-1")).resolves.toBeUndefined();
  });

  it("sends editor TTML as XML", async () => {
    const fetch = respond(200, { sync: "word" });
    await autolyrics.saveTtml("a b", "<tt/>");
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/jobs/a%20b/ttml");
    expect(new Headers(init?.headers).get("content-type")).toBe("application/ttml+xml");
  });
});

describe("stageViews", () => {
  it("shows every stage with its latest status and its duration once finished", () => {
    const views = stageViews([
      event("resolve", "running", 1),
      event("resolve", "done", 2.5, "Artist – Song"),
      event("audio", "running", 3, "Downloading"),
    ]);
    expect(views.map((v) => [v.stage, v.status])).toEqual([
      ["resolve", "done"],
      ["audio", "running"],
      ["lyrics", "pending"],
      ["polish", "pending"],
      ["align", "pending"],
      ["export", "pending"],
    ]);
    expect(views[0]).toMatchObject({ message: "Artist – Song", started: 1, finished: 2.5 });
    expect(views[1].finished).toBeNull();
  });

  it("shows live progress only on a running stage", () => {
    const progress = {
      audio: { stage: "audio" as const, label: "Downloading", fraction: 0.4, detail: "1.0 MB" },
      resolve: { stage: "resolve" as const, label: "Old", fraction: 1, detail: "" },
    };
    const views = stageViews([event("resolve", "done", 1), event("audio", "running", 2)], progress);
    expect(views[1].progress).toEqual(progress.audio);
    expect(views[0].progress).toBeNull();
    expect(views[2].progress).toBeNull();
  });
});
