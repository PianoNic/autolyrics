import { wireFrameLoop } from "@/lib/frame-loop-wiring";
import { addGlobalAllowedConsolePattern } from "@/test/console-guard";
import { render } from "@/test/render";
import { buildSyncedTtml } from "@/test/ttml-fixtures";
import { SpicyRenderer } from "@/views/preview/spicy/spicy-renderer";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

// -- Helpers ------------------------------------------------------------------

async function waitForLyrics(container: Element): Promise<Element> {
  await expect.poll(() => container.querySelector(".spicy-lyrics")).not.toBeNull();
  const el = container.querySelector(".spicy-lyrics");
  if (!el) throw new Error(".spicy-lyrics element not rendered");
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

describe("lyrics layout", () => {
  it("centres a page-width column by default", async () => {
    const screen = await render(<SpicyRenderer ttmlString={buildSyncedTtml()} />);
    const el = await waitForLyrics(screen.container);

    expect(el.classList).toContain("max-w-3xl");
    expect(el.classList).toContain("px-6");
  });

  it("fills a narrow sidebar", async () => {
    const screen = await render(<SpicyRenderer ttmlString={buildSyncedTtml()} layout="sidebar" />);
    const el = await waitForLyrics(screen.container);

    expect(el.classList).not.toContain("max-w-3xl");
    expect(el.classList).not.toContain("px-6");
    expect(el.classList).toContain("w-full");
  });
});
