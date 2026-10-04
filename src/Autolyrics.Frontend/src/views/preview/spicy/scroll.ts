// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Scrolling/ScrollToActiveLine.ts and src/utils/ScrollIntoView/Center.ts (fcc5f83).
// Simplebar, the virtualizer, compact-mode "Top" scrolling and the scroll-lead setting are left out.

import type { SpicyDocument, SpicyLine } from "@/views/preview/spicy/model";

// -- Types --------------------------------------------------------------------

interface ScrollState {
  lastLine: HTMLElement | null;
  lastPosition: number;
  lastUserScrollTime: number;
}

// -- Constants ----------------------------------------------------------------

/** How long (ms) a wheel or touch scroll holds auto-scroll off. */
const USER_SCROLL_COOLDOWN_MS = 750;

/** A position change bigger than this (ms) between frames is a seek, not playback. */
const DRASTIC_POSITION_CHANGE_MS = 1000;

/** Lines looked ahead (background lines excluded) before the highest active line may keep the anchor. */
const PIN_LOOKAHEAD = 2;

/** The active line sits this far (px) above the centre. */
const CENTER_OFFSET = 30;

/** Minimum visible height (px) for the active line to count as on screen. */
const MIN_VISIBLE_HEIGHT = 5;

// -- Line picking -------------------------------------------------------------

function resolveToLeadIndex(lines: SpicyLine[], index: number): number {
  let i = index;
  while (i > 0 && lines[i].isBackground) i--;
  return i;
}

function groupEndTime(lines: SpicyLine[], leadIndex: number): number {
  let end = lines[leadIndex].end;
  for (let i = leadIndex + 1; i < lines.length && lines[i].isBackground; i++) end = Math.max(end, lines[i].end);
  return end;
}

function lookaheadLine(lines: SpicyLine[], leadIndex: number): SpicyLine | null {
  let remaining = PIN_LOOKAHEAD;
  for (let i = leadIndex + 1; i < lines.length; i++) {
    if (lines[i].isBackground) continue;
    remaining -= 1;
    if (remaining === 0) return lines[i];
  }
  return null;
}

/** Index of the line to keep centred, collapsing active background lines onto their lead line. */
function scrollLineIndex(lines: SpicyLine[], time: number): number | null {
  const activeIndices: number[] = [];
  lines.forEach((line, index) => {
    if (line.start <= time && line.end >= time) activeIndices.push(index);
  });
  if (activeIndices.length === 0) return null;

  const frontLead = Math.max(...activeIndices.map((index) => resolveToLeadIndex(lines, index)));
  const activeLeads: number[] = [];
  for (const index of activeIndices) {
    const lead = resolveToLeadIndex(lines, index);
    // A background vocal outliving its own lead line must not drag the anchor back up.
    if (lines[index].isBackground && lead < frontLead) continue;
    if (activeLeads[activeLeads.length - 1] !== lead) activeLeads.push(lead);
  }

  const anchor = activeLeads[0];
  const lookahead = lookaheadLine(lines, anchor);
  if (lookahead === null || groupEndTime(lines, anchor) <= lookahead.start) return anchor;
  const last = activeLeads[activeLeads.length - 1];
  return last - anchor <= 1 ? anchor : last;
}

// -- Scrolling ----------------------------------------------------------------

function isInViewport(scroller: HTMLElement, line: HTMLElement): boolean {
  const top = Math.max(line.offsetTop, scroller.scrollTop);
  const bottom = Math.min(line.offsetTop + line.clientHeight, scroller.scrollTop + scroller.clientHeight);
  return bottom - top >= MIN_VISIBLE_HEIGHT;
}

function scrollIntoCenter(scroller: HTMLElement, line: HTMLElement, instant: boolean): void {
  const top = line.offsetTop - (scroller.clientHeight / 2 - line.clientHeight / 2) + CENTER_OFFSET;
  scroller.scrollTo({ top, behavior: instant ? "instant" : "smooth" });
}

/** Keeps the active line centred, unless the reader scrolled away from it. */
function followActiveLine(
  doc: SpicyDocument,
  scroller: HTMLElement,
  state: ScrollState,
  time: number,
  playing: boolean,
): void {
  const lines = doc.lines;
  if (lines.length === 0) return;
  const allSung = lines.every((line) => time >= line.end);
  const index = allSung ? lines.length - 1 : scrollLineIndex(lines, time);
  const target = index === null ? null : lines[index].element;

  const drastic = state.lastPosition !== 0 && Math.abs(time - state.lastPosition) > DRASTIC_POSITION_CHANGE_MS;
  const force = state.lastLine === null || drastic;
  const scrubbing = !playing && state.lastPosition !== time;
  state.lastPosition = time;
  if (!target) return;

  if (force || scrubbing) {
    scroller.classList.remove("HideLineBlur");
    state.lastLine = target;
    scrollIntoCenter(scroller, target, force);
    return;
  }

  if (target === state.lastLine) return;
  const cooledDown = performance.now() - state.lastUserScrollTime > USER_SCROLL_COOLDOWN_MS;
  if (!cooledDown || !isInViewport(scroller, target)) return;
  scroller.classList.remove("HideLineBlur");
  state.lastLine = target;
  scrollIntoCenter(scroller, target, false);
}

/** A wheel or touch scroll: unblur the lines so the reader can read ahead, and hold auto-scroll off. */
function noteUserScroll(scroller: HTMLElement, state: ScrollState): void {
  scroller.classList.add("HideLineBlur");
  state.lastUserScrollTime = performance.now();
}

function createScrollState(): ScrollState {
  return { lastLine: null, lastPosition: 0, lastUserScrollTime: 0 };
}

// -- Exports ------------------------------------------------------------------

export { createScrollState, followActiveLine, noteUserScroll };
export type { ScrollState };
