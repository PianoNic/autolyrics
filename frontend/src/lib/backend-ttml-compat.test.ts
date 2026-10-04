import { readFileSync } from "node:fs";
import { parseTtml } from "@/utils/lyrics-parsers/ttml";
import { generateTTML } from "@/utils/ttml";
import { describe, expect, it } from "vitest";

// The Python backend writes TTML that this editor must load unchanged.
describe("backend TTML compat", () => {
  it("parses backend output identically", () => {
    const xml = readFileSync("../backend/tests/fixtures/golden-rick-output.ttml", "utf-8");
    const parsed = parseTtml(xml);
    expect(parsed.issues).toEqual([]);
    expect(parsed.lines.length).toBeGreaterThan(40);
    expect(parsed.lines.every((l) => l.words && l.words.length > 0)).toBe(true);
    const regenerated = generateTTML({
      metadata: { title: "", artists: [], ...parsed.metadata } as never,
      agents: parsed.agents ?? [],
      lines: parsed.lines,
    });
    const body = (s: string) => s.slice(s.indexOf("<body"));
    expect(body(regenerated).replace(/ dur="[^"]*"/, "")).toBe(body(xml).replace(/ dur="[^"]*"/, ""));
  });
});
