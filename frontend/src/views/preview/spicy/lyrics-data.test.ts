import { createLine } from "@/test/factories";
import { buildSpicyLyrics } from "@/views/preview/spicy/lyrics-data";
import { createSpline } from "@/views/preview/spicy/spline";
import { Spring } from "@/views/preview/spicy/spring";
import { describe, expect, it } from "vitest";

// -- Lyrics data ----------------------------------------------------------------

describe("buildSpicyLyrics", () => {
  it("turns word-synced lines into syllable lyrics with their lead timing", () => {
    const data = buildSpicyLyrics([
      createLine({
        text: "hello world",
        words: [
          { text: "hello ", begin: 1, end: 2 },
          { text: "world", begin: 2, end: 3 },
        ],
      }),
    ]);

    expect(data.kind).toBe("Syllable");
    if (data.kind !== "Syllable") return;
    expect(data.start).toBe(1);
    expect(data.lines[0].lead).toEqual({
      start: 1,
      end: 3,
      syllables: [
        { text: "hello", start: 1, end: 2, isPartOfWord: false },
        { text: "world", start: 2, end: 3, isPartOfWord: false },
      ],
    });
  });

  it("marks syllables that run into the next one as parts of one word", () => {
    const data = buildSpicyLyrics([
      createLine({
        text: "won-der ful",
        words: [
          { text: "won", begin: 0, end: 1 },
          { text: "der ", begin: 1, end: 2 },
          { text: "ful", begin: 2, end: 3 },
        ],
      }),
    ]);

    if (data.kind !== "Syllable") throw new Error("expected syllable lyrics");
    expect(data.lines[0].lead.syllables.map((syllable) => syllable.isPartOfWord)).toEqual([true, false, false]);
  });

  it("carries background vocals as their own vocal under the lead", () => {
    const data = buildSpicyLyrics([
      createLine({
        text: "lead",
        words: [{ text: "lead", begin: 0, end: 2 }],
        backgroundWords: [
          { text: "ooh ", begin: 1, end: 2 },
          { text: "ahh", begin: 2, end: 3 },
        ],
      }),
    ]);

    if (data.kind !== "Syllable") throw new Error("expected syllable lyrics");
    expect(data.lines[0].background).toHaveLength(1);
    expect(data.lines[0].background[0].syllables.map((syllable) => syllable.text)).toEqual(["ooh", "ahh"]);
  });

  it("puts v2 and v2000 on the opposite side like Spicy's duet layout", () => {
    const words = [{ text: "x", begin: 0, end: 1 }];
    const data = buildSpicyLyrics([
      createLine({ agentId: "v1", text: "x", words }),
      createLine({ agentId: "v2", text: "x", words }),
      createLine({ agentId: "v2000", text: "x", words }),
      createLine({ agentId: "v3", text: "x", words }),
    ]);

    if (data.kind !== "Syllable") throw new Error("expected syllable lyrics");
    expect(data.lines.map((line) => line.oppositeAligned)).toEqual([false, true, true, false]);
  });

  it("keeps a line-synced line inside word-synced lyrics as one syllable spanning the line", () => {
    const data = buildSpicyLyrics([
      createLine({ text: "word synced", words: [{ text: "word synced", begin: 0, end: 2 }] }),
      createLine({ text: "line synced", begin: 3, end: 5 }),
    ]);

    if (data.kind !== "Syllable") throw new Error("expected syllable lyrics");
    expect(data.lines[1].lead.syllables).toEqual([{ text: "line synced", start: 3, end: 5, isPartOfWord: false }]);
  });

  it("uses line lyrics when no line has word timing, skipping untimed lines", () => {
    const data = buildSpicyLyrics([
      createLine({ text: "first", begin: 4, end: 6 }),
      createLine({ text: "untimed" }),
      createLine({ text: "second", begin: 7, end: 9, agentId: "v2" }),
    ]);

    expect(data).toEqual({
      kind: "Line",
      start: 4,
      lines: [
        { text: "first", start: 4, end: 6, oppositeAligned: false },
        { text: "second", start: 7, end: 9, oppositeAligned: true },
      ],
    });
  });

  it("drops syllables that hold nothing but zero-width characters", () => {
    const data = buildSpicyLyrics([
      createLine({
        text: "a",
        words: [
          { text: "a ", begin: 0, end: 1 },
          { text: "\u200B", begin: 1, end: 2 },
        ],
      }),
    ]);

    if (data.kind !== "Syllable") throw new Error("expected syllable lyrics");
    expect(data.lines[0].lead.syllables.map((syllable) => syllable.text)).toEqual(["a"]);
  });
});

// -- Animation primitives -------------------------------------------------------

describe("createSpline", () => {
  it("passes through every control point and clamps outside them", () => {
    const spline = createSpline([
      { progress: 0, value: 0.95 },
      { progress: 0.7, value: 1.0505 },
      { progress: 1, value: 1 },
    ]);

    expect(spline.at(0)).toBeCloseTo(0.95);
    expect(spline.at(0.7)).toBeCloseTo(1.0505);
    expect(spline.at(1)).toBeCloseTo(1);
    expect(spline.at(-1)).toBeCloseTo(0.95);
    expect(spline.at(2)).toBeCloseTo(1);
  });
});

describe("Spring", () => {
  it("settles on its goal and then reports it can sleep", () => {
    const spring = new Spring(0, 0.88, 0.64);
    spring.setGoal(1);
    expect(spring.canSleep()).toBe(false);

    let value = 0;
    for (let frame = 0; frame < 600; frame++) value = spring.step(1 / 60);

    expect(value).toBeCloseTo(1, 3);
    expect(spring.canSleep()).toBe(true);
  });

  it("jumps straight to the goal when asked to replace its position", () => {
    const spring = new Spring(0, 1, 0.5);
    spring.setGoal(3, true);
    expect(spring.step(1 / 60)).toBe(3);
    expect(spring.canSleep()).toBe(true);
  });
});
