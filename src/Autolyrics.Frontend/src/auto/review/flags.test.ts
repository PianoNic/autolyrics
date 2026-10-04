import type { LyricLine, LyricWord } from "@/auto/api/autolyrics-client";
import { describeFlags, lineBounds, lineDisplay, lineNeedsReview, needsReview } from "@/auto/review/flags";
import { describe, expect, it } from "vitest";

// -- Helpers ------------------------------------------------------------------

function word(text: string, begin: number | null, end: number | null, flags: string[] = []): LyricWord {
  return { text, begin, end, confidence: null, flags };
}

function line(words: LyricWord[], background: LyricWord[] = []): LyricLine {
  return { words, background, agent: "v1", begin: null, end: null };
}

// -- Tests --------------------------------------------------------------------

describe("review flags", () => {
  it("counts only flags a reviewer should act on", () => {
    expect(needsReview(word("a", 1, 2, ["low-confidence"]))).toBe(true);
    expect(needsReview(word("a", 1, 2, ["interpolated"]))).toBe(false);
    expect(needsReview(word("a", 1, 2, ["llm-edit"]))).toBe(false);
    expect(lineNeedsReview(line([word("a", 1, 2)], [word("b", 2, 3, ["overlap"])]))).toBe(true);
  });

  it("describes flags in reviewer language", () => {
    expect(describeFlags(word("a", 1, 2, ["low-confidence", "custom"]))).toBe(
      "The timing judge is not sure this word is placed right · custom",
    );
  });

  it("reads a line's span from its words, falling back to line timing", () => {
    expect(lineBounds(line([word("a ", 1, 2), word("b", 2, 3.5)], [word("(c)", 3, 4)]))).toEqual({ begin: 1, end: 4 });
    expect(lineBounds({ ...line([word("a", null, null)]), begin: 5, end: 6 })).toEqual({ begin: 5, end: 6 });
    expect(lineBounds(line([word("a", null, null)]))).toBeNull();
  });

  it("shows background vocals in one pair of parentheses", () => {
    expect(lineDisplay(line([word("Hi ", 1, 2), word("there", 2, 3)], [word("(oh ", 3, 4), word("yeah)", 4, 5)]))).toBe(
      "Hi there (oh yeah)",
    );
    expect(lineDisplay(line([word("Hi", 1, 2)], [word("oh", 3, 4)]))).toBe("Hi (oh)");
  });
});
