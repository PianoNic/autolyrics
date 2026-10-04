import { wireFrameLoop } from "@/lib/frame-loop-wiring";
import { DEFAULTS, useSettingsStore } from "@/stores/settings";
import { addGlobalAllowedConsolePattern } from "@/test/console-guard";
import { render } from "@/test/render";
import { buildSyncedTtml } from "@/test/ttml-fixtures";
import { LyricsRenderer } from "@/views/preview/lyrics-renderer";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

// -- Helpers ------------------------------------------------------------------

type Engine = "spicy" | "braccato" | "am-lyrics";

// The element each engine puts the layout classes on.
const ENGINE_SELECTOR: Record<Engine, string> = {
  spicy: ".spicy-lyrics",
  braccato: "braccato-lyrics",
  "am-lyrics": "am-lyrics",
};

async function waitForElement(container: Element, selector: string): Promise<Element> {
  await expect.poll(() => container.querySelector(selector)).not.toBeNull();
  const el = container.querySelector(selector);
  if (!el) throw new Error(`${selector} element not rendered`);
  return el;
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

describe("LyricsRenderer", () => {
  it("renders Spicy Lyrics by default", async () => {
    useSettingsStore.setState({ previewRenderer: DEFAULTS.previewRenderer });
    const screen = await render(<LyricsRenderer ttmlString={buildSyncedTtml()} durationSeconds={35} />);

    await waitForElement(screen.container, ".spicy-lyrics .line");
    expect(screen.container.querySelector("braccato-lyrics")).toBeNull();
    expect(screen.container.querySelector("am-lyrics")).toBeNull();
  });

  it("swaps from Spicy Lyrics to Braccato when the setting changes", async () => {
    useSettingsStore.setState({ previewRenderer: "spicy" });
    const screen = await render(<LyricsRenderer ttmlString={buildSyncedTtml()} durationSeconds={35} />);
    await waitForElement(screen.container, ".spicy-lyrics");

    useSettingsStore.setState({ previewRenderer: "braccato" });

    await waitForElement(screen.container, "braccato-lyrics");
    await expect.poll(() => screen.container.querySelector(".spicy-lyrics")).toBeNull();
  });

  it("renders Braccato when the preview renderer setting is braccato", async () => {
    useSettingsStore.setState({ previewRenderer: "braccato" });
    const screen = await render(<LyricsRenderer ttmlString={buildSyncedTtml()} durationSeconds={35} />);

    await waitForElement(screen.container, "braccato-lyrics");
    expect(screen.container.querySelector("am-lyrics")).toBeNull();
  });

  it("renders AM Lyrics when the preview renderer setting is am-lyrics", async () => {
    useSettingsStore.setState({ previewRenderer: "am-lyrics" });
    const screen = await render(<LyricsRenderer ttmlString={buildSyncedTtml()} durationSeconds={35} />);

    await waitForElement(screen.container, "am-lyrics");
    expect(screen.container.querySelector("braccato-lyrics")).toBeNull();
  });

  it("swaps the engine when the setting changes", async () => {
    useSettingsStore.setState({ previewRenderer: "braccato" });
    const screen = await render(<LyricsRenderer ttmlString={buildSyncedTtml()} durationSeconds={35} />);
    await waitForElement(screen.container, "braccato-lyrics");

    useSettingsStore.setState({ previewRenderer: "am-lyrics" });

    await waitForElement(screen.container, "am-lyrics");
    await expect.poll(() => screen.container.querySelector("braccato-lyrics")).toBeNull();
  });

  describe("layout", () => {
    it.each(["spicy", "braccato", "am-lyrics"] as const)("centres a page-width column by default with %s", async (engine) => {
      useSettingsStore.setState({ previewRenderer: engine });
      const screen = await render(<LyricsRenderer ttmlString={buildSyncedTtml()} durationSeconds={35} />);
      const el = await waitForElement(screen.container, ENGINE_SELECTOR[engine]);

      expect(el.classList).toContain("max-w-3xl");
      expect(el.classList).toContain("px-6");
    });

    it.each(["spicy", "braccato", "am-lyrics"] as const)("fills a narrow sidebar with %s", async (engine) => {
      useSettingsStore.setState({ previewRenderer: engine });
      const screen = await render(
        <LyricsRenderer ttmlString={buildSyncedTtml()} durationSeconds={35} layout="sidebar" />,
      );
      const el = await waitForElement(screen.container, ENGINE_SELECTOR[engine]);

      expect(el.classList).not.toContain("max-w-3xl");
      expect(el.classList).not.toContain("px-6");
      expect(el.classList).toContain("w-full");
    });
  });
});
