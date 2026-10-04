import { saveLinkedJob, startJobAutosave } from "@/auto/editor/job-autosave";
import { useJobLinkStore } from "@/auto/editor/job-link-store";
import { useProjectStore } from "@/stores/project";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// -- Helpers ------------------------------------------------------------------

function editLyrics(): void {
  useProjectStore.getState().setLines([{ id: "l1", text: "Hello there", agentId: "v1", begin: 1, end: 2 }]);
}

function okResponse() {
  return new Response(JSON.stringify({ sync: "line", validation: {}, files: {} }), { status: 200 });
}

// -- Tests --------------------------------------------------------------------

describe("job autosave", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useJobLinkStore.getState().link("job-1", "Song", []);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    useJobLinkStore.getState().unlink();
  });

  it("saves edits back to the song after a pause and marks the project clean", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse());
    const stop = startJobAutosave();

    editLyrics();
    expect(useJobLinkStore.getState().saveState).toBe("pending");
    expect(fetch).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1600);
    expect(fetch).toHaveBeenCalledOnce();
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/jobs/job-1/ttml");
    expect(String(init?.body)).toContain("Hello there");
    expect(useProjectStore.getState().isDirty).toBe(false);
    expect(useJobLinkStore.getState().saveState).toBe("saved");
    stop();
  });

  it("does nothing for a project that is not from autolyrics", async () => {
    useJobLinkStore.getState().unlink();
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse());
    const stop = startJobAutosave();
    editLyrics();
    await vi.advanceTimersByTimeAsync(1600);
    expect(fetch).not.toHaveBeenCalled();
    stop();
  });

  it("reports a failed save so it can be retried", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 500 }));
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    editLyrics();
    await saveLinkedJob();
    expect(useJobLinkStore.getState().saveState).toBe("error");
    expect(useProjectStore.getState().isDirty).toBe(true);
  });
});
