// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Applyer/Synced/Syllable.ts and Line.ts (fcc5f83), the musical-line
// ("interlude dots") blocks, plus getLyricsBetweenShow / getInterludeTimePadding from lyrics.ts.

import { createDotSprings } from "@/views/preview/spicy/curves";
import type { SpicyDot, SpicyLine } from "@/views/preview/spicy/model";

// -- Constants ----------------------------------------------------------------

/** A gap this long (seconds) between two lines gets interlude dots. */
const INTERLUDE_MIN_GAP_SECONDS = 3;

/** The dot line starts collapsing this long (ms) before the next line starts. */
const PRE_HIDDEN_DOT_LINE_MS = 500;

/** Upstream finishes the dots slightly before the gap ends, so the last one lands before the collapse. */
const INTERLUDE_TIME_PADDING_MS = -(PRE_HIDDEN_DOT_LINE_MS + 50);

const DOT_COUNT = 3;

// -- Builders -----------------------------------------------------------------

function createDot(start: number, end: number): SpicyDot {
  const element = document.createElement("span");
  element.classList.add("word", "dot");
  element.textContent = "\u2022";
  return { kind: "dot", element, start, end, springs: createDotSprings() };
}

/** A collapsed line of three dots that fill one after another across a gap (ms). */
function createDotLine(gapStart: number, gapEnd: number, oppositeAligned: boolean): SpicyLine {
  const element = document.createElement("div");
  element.classList.add("line", "musical-line");
  if (oppositeAligned) element.classList.add("OppositeAligned");

  const total = gapEnd - gapStart;
  const base = total / DOT_COUNT;
  const padding = INTERLUDE_TIME_PADDING_MS / DOT_COUNT;
  const dot1End = Math.max(gapStart, gapStart + base + padding);
  const dot2End = Math.max(dot1End, gapStart + base * 2 + padding * 2);
  const dot3End = Math.max(dot2End, gapStart + total + INTERLUDE_TIME_PADDING_MS);
  const dots = [createDot(gapStart, dot1End), createDot(dot1End, dot2End), createDot(dot2End, dot3End)];

  const group = document.createElement("div");
  group.classList.add("dotGroup");
  for (const dot of dots) group.appendChild(dot.element);
  element.appendChild(group);

  return {
    element,
    start: gapStart,
    end: gapEnd,
    syllables: dots,
    isDotLine: true,
    isBackground: false,
    seekTime: gapStart,
    glow: null,
    settledAs: "NotSung",
  };
}

function hasInterludeBetween(endSeconds: number, nextStartSeconds: number): boolean {
  return nextStartSeconds - endSeconds >= INTERLUDE_MIN_GAP_SECONDS;
}

// -- Exports ------------------------------------------------------------------

export { PRE_HIDDEN_DOT_LINE_MS, createDotLine, hasInterludeBetween };
