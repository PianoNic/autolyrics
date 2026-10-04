import { wireFrameLoop } from "@/lib/frame-loop-wiring";
import { useAudioStore } from "@/stores/audio";
import { useProjectStore } from "@/stores/project";
import { createLine } from "@/test/factories";
import { type FrameProbe, createFrameProbe } from "@/test/frame-probe";
import { render } from "@/test/render";
import { buildBackgroundVocalTtml, buildSyncedTtml } from "@/test/ttml-fixtures";
import { generateTTML } from "@/utils/ttml";
import { SpicyRenderer } from "@/views/preview/spicy/spicy-renderer";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

// -- Fixtures ------------------------------------------------------------------

// Clock values are SS.mmm: Composer's TTML parser has no offset-time (`2.5s`) support.
const TTML_HEAD =
  '<tt xmlns="http://www.w3.org/ns/ttml" xmlns:ttm="http://www.w3.org/ns/ttml#metadata" xml:lang="en"><head><metadata><ttm:agent type="person" xml:id="v1"/><ttm:agent type="person" xml:id="v2"/></metadata></head><body dur="10.000"><div>';
const TTML_TAIL = "</div></body></tt>";

/** Two duet lines of short words (plain words, no letter emphasis): v1 at 1-2s, v2 at 2-3s. */
const DUET_TTML = `${TTML_HEAD}<p begin="1.000" end="2.000" ttm:agent="v1"><span begin="1.000" end="1.500">left</span> <span begin="1.500" end="2.000">side</span></p><p begin="2.000" end="3.000" ttm:agent="v2"><span begin="2.000" end="2.500">right</span> <span begin="2.500" end="3.000">side</span></p>${TTML_TAIL}`;

/** Two line-synced lines with no word timing: 1-3s and 4-6s. */
const LINE_SYNCED_TTML = `${TTML_HEAD}<p begin="1.000" end="3.000" ttm:agent="v1">first line</p><p begin="4.000" end="6.000" ttm:agent="v1">second line</p>${TTML_TAIL}`;

/** Twenty back-to-back two-second lines, far more than fit in the panel. */
function buildLongTtml(): string {
  const lines = Array.from({ length: 20 }, (_, index) =>
    createLine({
      id: `line-${index}`,
      text: `line ${index}`,
      words: [{ text: `line ${index}`, begin: index * 2, end: index * 2 + 2 }],
    }),
  );
  const { metadata, agents } = useProjectStore.getState();
  return generateTTML({ metadata, agents, lines, groups: [] });
}

// PreviewPanel hands the renderer a bounded flex column.
const PANEL_STYLE = { display: "flex", flexDirection: "column", height: 600 } as const;

// -- Helpers ------------------------------------------------------------------

function useAudioAt(seconds: number): HTMLAudioElement {
  const audio = new Audio();
  audio.currentTime = seconds;
  useAudioStore.setState({ audioElement: audio, isPlaying: false });
  return audio;
}

async function renderSpicy(ttml: string): Promise<HTMLElement> {
  const screen = await render(
    <div style={PANEL_STYLE}>
      <SpicyRenderer ttmlString={ttml} />
    </div>,
  );
  const root = screen.container.querySelector<HTMLElement>("[data-testid='spicy-lyrics']");
  if (!root) throw new Error("spicy lyrics scroller not rendered");
  await expect.poll(() => root.querySelectorAll(".line").length).toBeGreaterThan(0);
  return root;
}

function leadLines(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(".line:not(.musical-line, .bg-line)")];
}

function activeLeadText(root: HTMLElement): string {
  return root.querySelector(".line.Active:not(.musical-line, .bg-line)")?.textContent ?? "";
}

function gradientOf(el: Element | null | undefined): string {
  return (el as HTMLElement | null)?.style.getPropertyValue("--gradient-position") ?? "";
}

let disposeWiring: (() => void) | null = null;
let probe: FrameProbe;

beforeEach(() => {
  disposeWiring = wireFrameLoop();
  probe = createFrameProbe();
});

afterEach(() => {
  probe.dispose();
  disposeWiring?.();
  disposeWiring = null;
});

// -- Tests --------------------------------------------------------------------

describe("SpicyRenderer", () => {
  it("renders one line per lyric line from the TTML", async () => {
    useAudioAt(0);
    const root = await renderSpicy(buildSyncedTtml());

    expect(leadLines(root).map((line) => line.textContent)).toEqual([
      "firstlinehere",
      "secondlinenow",
      "thirdlineends",
    ]);
    expect(root.querySelector("[data-lyrics-type]")?.getAttribute("data-lyrics-type")).toBe("Syllable");
  });

  it("marks the line under the current audio time active, earlier lines sung and later ones not yet sung", async () => {
    useAudioAt(14);
    const root = await renderSpicy(buildSyncedTtml());

    await expect.poll(() => activeLeadText(root)).toBe("secondlinenow");
    const [first, , third] = leadLines(root);
    expect(first.classList).toContain("Sung");
    expect(third.classList).toContain("NotSung");
  });

  it("moves the active line as the audio time changes", async () => {
    useAudioAt(14);
    const root = await renderSpicy(buildSyncedTtml());
    await expect.poll(() => activeLeadText(root)).toBe("secondlinenow");

    useAudioStore.getState().seekTo(26);

    await expect.poll(() => activeLeadText(root)).toBe("thirdlineends");
    expect(leadLines(root)[1].classList).toContain("Sung");
  });

  it("fills the sung part of the active word with the gradient", async () => {
    useAudioAt(2.25);
    const root = await renderSpicy(DUET_TTML);
    await expect.poll(() => activeLeadText(root)).toBe("rightside");

    const [right, side] = root.querySelectorAll(".line.Active .word");
    await expect.poll(() => gradientOf(right)).toBe("40%");
    expect(gradientOf(side)).toBe("-20%");
  });

  it("lights a long syllable letter by letter", async () => {
    // "second " is held 12-14s, long enough to be split into letters.
    useAudioAt(13);
    const root = await renderSpicy(buildSyncedTtml());
    await expect.poll(() => activeLeadText(root)).toBe("secondlinenow");

    const letters = [...root.querySelectorAll(".line.Active .letterGroup")[0].querySelectorAll(".letter")];
    expect(letters.map((letter) => letter.textContent).join("")).toBe("second");
    await expect.poll(() => letters.slice(0, 3).map(gradientOf)).toEqual(["100%", "100%", "100%"]);
    expect(letters.slice(4).map(gradientOf)).toEqual(["-20%", "-20%"]);
    const activeFill = Number.parseFloat(gradientOf(letters[3]));
    expect(activeFill).toBeGreaterThan(-20);
    expect(activeFill).toBeLessThan(100);
  });

  it("renders background vocals as a smaller line under their lead line", async () => {
    useAudioAt(4.5);
    const root = await renderSpicy(buildBackgroundVocalTtml());

    const background = root.querySelector<HTMLElement>(".line.bg-line");
    expect(background?.textContent).toBe("oohahh");
    expect(background?.previousElementSibling?.textContent).toBe("firstlinehere");
    expect(leadLines(root)[0].textContent).not.toContain("ooh");
    await expect.poll(() => background?.classList.contains("Active")).toBe(true);
  });

  it("puts the second voice of a duet on the opposite side", async () => {
    useAudioAt(0);
    const root = await renderSpicy(DUET_TTML);

    const [left, right] = leadLines(root);
    expect(left.classList).not.toContain("OppositeAligned");
    expect(right.classList).toContain("OppositeAligned");
    expect(root.querySelector(".SpicyLyricsScrollContainer")?.classList).toContain("HasDuetLines");
  });

  it("renders line-synced lyrics as whole lines", async () => {
    useAudioAt(5);
    const root = await renderSpicy(LINE_SYNCED_TTML);

    expect(root.querySelector("[data-lyrics-type]")?.getAttribute("data-lyrics-type")).toBe("Line");
    expect(root.querySelectorAll(".word")).toHaveLength(0);
    await expect.poll(() => activeLeadText(root)).toBe("second line");
  });

  it("shows interlude dots across a long gap between lines", async () => {
    // "first line here" ends at 6s and "second line now" starts at 12s.
    useAudioAt(8);
    const root = await renderSpicy(buildSyncedTtml());

    const interludes = root.querySelectorAll(".line.musical-line");
    expect(interludes.length).toBeGreaterThan(0);
    await expect.poll(() => root.querySelector(".line.musical-line.Active")?.querySelectorAll(".dot").length).toBe(3);
  });

  it("seeks to the clicked line's start and starts playback", async () => {
    useAudioAt(0);
    const root = await renderSpicy(buildSyncedTtml());

    leadLines(root)[2].click();

    await expect.poll(() => useAudioStore.getState().currentTime).toBe(24);
    expect(useAudioStore.getState().isPlaying).toBe(true);
  });

  it("seeks from a click on a word inside the line too", async () => {
    useAudioAt(0);
    const root = await renderSpicy(DUET_TTML);

    root.querySelectorAll<HTMLElement>(".line .word")[3].click();

    await expect.poll(() => useAudioStore.getState().currentTime).toBe(2);
  });

  it("lets the frame loop go idle once the springs settle while paused", async () => {
    useAudioAt(14);
    const root = await renderSpicy(buildSyncedTtml());
    await expect.poll(() => activeLeadText(root)).toBe("secondlinenow");

    await probe.quiesce();
    expect(await probe.wokeAfter(() => useAudioStore.getState().seekTo(26))).toBe(true);
    await expect.poll(() => activeLeadText(root)).toBe("thirdlineends");
    await probe.quiesce();
  });

  it("scrolls the active line into the middle of the panel", async () => {
    useAudioAt(1);
    const root = await renderSpicy(buildLongTtml());
    await expect.poll(() => activeLeadText(root)).toBe("line 0");

    useAudioStore.getState().seekTo(31);

    await expect.poll(() => activeLeadText(root)).toBe("line 15");
    const active = root.querySelector<HTMLElement>(".line.Active");
    if (!active) throw new Error("no active line");
    await expect
      .poll(() => {
        const view = root.getBoundingClientRect();
        const line = active.getBoundingClientRect();
        return line.top > view.top && line.bottom < view.bottom;
      })
      .toBe(true);
    expect(root.scrollTop).toBeGreaterThan(0);
  });

  it("rebuilds the lines when the TTML changes", async () => {
    useAudioAt(0);
    const screen = await render(<SpicyRenderer ttmlString={buildSyncedTtml()} />);
    await expect.poll(() => screen.container.querySelectorAll(".line:not(.musical-line)").length).toBe(3);

    await screen.rerender(<SpicyRenderer ttmlString={LINE_SYNCED_TTML} />);

    await expect
      .poll(() => [...screen.container.querySelectorAll(".line:not(.musical-line)")].map((line) => line.textContent))
      .toEqual(["first line", "second line"]);
    expect(screen.container.querySelectorAll(".SpicyLyricsScrollContainer")).toHaveLength(1);
  });
});
