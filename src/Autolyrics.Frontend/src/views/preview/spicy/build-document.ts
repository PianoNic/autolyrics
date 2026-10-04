// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Applyer/Synced/Syllable.ts and src/utils/Lyrics/Applyer/Synced/Line.ts
// (fcc5f83). Spicy's credits, provider badge, virtualizer and Simplebar mounting are left out.

import { createDotLine, hasInterludeBetween } from "@/views/preview/spicy/build-dots";
import { createSyllableLine } from "@/views/preview/spicy/build-syllables";
import { createLineGlowSpring } from "@/views/preview/spicy/curves";
import type { LineSyncedData, SpicyLyricsData, SyllableLineData } from "@/views/preview/spicy/lyrics-data";
import type { SpicyDocument, SpicyLine } from "@/views/preview/spicy/model";
import { isRtl } from "@/views/preview/spicy/text-direction";

// -- Helpers ------------------------------------------------------------------

function seconds(value: number): number {
  return value * 1000;
}

function createLineSyncedLine(data: LineSyncedData): SpicyLine {
  const element = document.createElement("div");
  element.textContent = data.text;
  element.classList.add("line");
  if (isRtl(data.text)) element.classList.add("rtl");
  if (data.oppositeAligned) element.classList.add("OppositeAligned");
  return {
    element,
    start: seconds(data.start),
    end: seconds(data.end),
    syllables: [],
    isDotLine: false,
    isBackground: false,
    seekTime: seconds(data.start),
    glow: createLineGlowSpring(),
    settledAs: "NotSung",
  };
}

function buildSyllableLines(lines: SyllableLineData[]): SpicyLine[] {
  const built: SpicyLine[] = [];
  lines.forEach((line, index) => {
    built.push(createSyllableLine(line.lead, line.oppositeAligned, false));
    for (const background of line.background) built.push(createSyllableLine(background, line.oppositeAligned, true));
    const next = lines[index + 1];
    if (next && hasInterludeBetween(line.lead.end, next.lead.start)) {
      built.push(createDotLine(seconds(line.lead.end), seconds(next.lead.start), next.oppositeAligned));
    }
  });
  return built;
}

function buildLineSyncedLines(lines: LineSyncedData[]): SpicyLine[] {
  const built: SpicyLine[] = [];
  lines.forEach((line, index) => {
    built.push(createLineSyncedLine(line));
    const next = lines[index + 1];
    if (next && hasInterludeBetween(line.end, next.start)) {
      built.push(createDotLine(seconds(line.end), seconds(next.start), next.oppositeAligned));
    }
  });
  return built;
}

function hasRtlText(data: SpicyLyricsData): boolean {
  if (data.kind === "Line") return data.lines.some((line) => isRtl(line.text));
  return data.lines.some((line) =>
    [line.lead, ...line.background].some((vocal) => vocal.syllables.some((syllable) => isRtl(syllable.text))),
  );
}

// -- Builder ------------------------------------------------------------------

/** Builds the lyric lines into a fresh scroll container; nothing is attached to the page yet. */
function buildSpicyDocument(data: SpicyLyricsData): SpicyDocument {
  const container = document.createElement("div");
  container.classList.add("SpicyLyricsScrollContainer");
  container.dataset.lyricsType = data.kind;
  container.classList.toggle(
    "HasDuetLines",
    data.lines.some((line) => line.oppositeAligned),
  );
  container.classList.toggle("HasRtlLines", hasRtlText(data));

  const lines: SpicyLine[] = [];
  const first = data.lines[0];
  if (first && hasInterludeBetween(0, data.start)) {
    lines.push(createDotLine(0, seconds(data.start), first.oppositeAligned));
  }
  lines.push(...(data.kind === "Syllable" ? buildSyllableLines(data.lines) : buildLineSyncedLines(data.lines)));

  for (const line of lines) {
    line.element.classList.add("NotSung");
    if (line.isDotLine) line.element.classList.add("pre-hidden");
    container.appendChild(line.element);
  }

  return { kind: data.kind, container, lines };
}

// -- Exports ------------------------------------------------------------------

export { buildSpicyDocument };
