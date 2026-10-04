import { wireFrameLoop } from "@/lib/frame-loop-wiring";
import { useAudioStore } from "@/stores/audio";
import { useProjectStore } from "@/stores/project";
import { addGlobalAllowedConsolePattern } from "@/test/console-guard";
import { createLine } from "@/test/factories";
import { render } from "@/test/render";
import { TimelinePreviewSidebar } from "@/views/timeline/timeline-preview-sidebar";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

// -- Helpers ------------------------------------------------------------------

function seedThreeLines(): void {
  useProjectStore.setState({
    granularity: "word",
    lines: [
      createLine({ id: "a", text: "first line here", words: [{ text: "first line here", begin: 2, end: 6 }] }),
      createLine({ id: "b", text: "second line now", words: [{ text: "second line now", begin: 12, end: 18 }] }),
      createLine({ id: "c", text: "third line ends", words: [{ text: "third line ends", begin: 24, end: 30 }] }),
    ],
  });
}

async function sidebarLines(root: Element): Promise<HTMLElement[]> {
  const sidebar = root.querySelector("aside");
  if (!sidebar) throw new Error("sidebar not rendered");
  await expect.poll(() => sidebar.querySelectorAll(".spicy-lyrics .line").length).toBeGreaterThan(0);
  return [...sidebar.querySelectorAll<HTMLElement>(".spicy-lyrics .line")];
}

function lineTexts(root: Element): string {
  return [...root.querySelectorAll(".spicy-lyrics .line")].map((line) => line.textContent ?? "").join(" ");
}

let disposeWiring: (() => void) | null = null;

beforeAll(() => {
  addGlobalAllowedConsolePattern(/dev mode/i);
});

beforeEach(() => {
  disposeWiring = wireFrameLoop();
});

afterEach(() => {
  disposeWiring?.();
  disposeWiring = null;
});

// -- Tests --------------------------------------------------------------------

describe("TimelinePreviewSidebar", () => {
  it("shows the 'No synced content' fallback for an empty project", async () => {
    useProjectStore.setState({ lines: [] });
    const screen = await render(<TimelinePreviewSidebar />);
    await expect.element(screen.getByText("No synced content")).toBeInTheDocument();
    expect(screen.container.querySelector(".spicy-lyrics")).toBeNull();
  });

  it("renders the preview header and the lyrics through Spicy Lyrics in the sidebar layout", async () => {
    seedThreeLines();
    const screen = await render(<TimelinePreviewSidebar />);

    await expect.element(screen.getByText("Preview", { exact: true })).toBeInTheDocument();
    await sidebarLines(screen.container);
    const sidebar = screen.container.querySelector("aside");
    expect(sidebar?.querySelector("[data-lyrics-layout='sidebar'] .spicy-lyrics")).not.toBeNull();
    expect(lineTexts(screen.container)).toContain("second line now");
  });

  it("shows a Timeline edit", async () => {
    seedThreeLines();
    const screen = await render(<TimelinePreviewSidebar />);
    await sidebarLines(screen.container);

    useProjectStore
      .getState()
      .updateLineWithHistory("b", { text: "edited line", words: [{ text: "edited line", begin: 12, end: 18 }] });

    await expect.poll(() => lineTexts(screen.container)).toContain("edited line");
    expect(lineTexts(screen.container)).not.toContain("second line now");
  });

  it("seeks the audio to a clicked line", async () => {
    useAudioStore.setState({ audioElement: new Audio() });
    seedThreeLines();
    const screen = await render(<TimelinePreviewSidebar />);
    const lines = await sidebarLines(screen.container);

    lines.find((line) => line.textContent?.includes("second line now"))?.click();

    await expect.poll(() => useAudioStore.getState().currentTime).toBe(12);
  });
});
