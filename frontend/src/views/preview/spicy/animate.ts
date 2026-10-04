// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Animator/Lyrics/LyricsAnimator.ts (fcc5f83), Animate() and applyBlur().
// Upstream only eased the sung line right before the active one back to rest; here every line that
// left its resting state settles again, so seeking backwards un-sings the words too.

import { type FrameContext, animateSyllable } from "@/views/preview/spicy/animate-syllables";
import { PRE_HIDDEN_DOT_LINE_MS } from "@/views/preview/spicy/build-dots";
import { BLUR_MULTIPLIER, LINE_GLOW_SPLINE } from "@/views/preview/spicy/curves";
import {
  type ElementState,
  type SpicyDocument,
  type SpicyLine,
  getElementState,
  getProgress,
} from "@/views/preview/spicy/model";
import { flushStyleBatch, setClass, setStyleIfChanged } from "@/views/preview/spicy/style-writer";

// -- Types --------------------------------------------------------------------

interface AnimatorState {
  /** The line index the blur ramp was last centred on. */
  blurredAround: number | null;
}

// -- Constants ----------------------------------------------------------------

const MAX_BLUR = BLUR_MULTIPLIER * 5 + BLUR_MULTIPLIER * 0.465;

/** Lines further than this from the focus jump to rest instead of animating there off screen. */
const ANIMATED_SETTLE_RADIUS = 3;

// -- Helpers ------------------------------------------------------------------

function applyBlur(doc: SpicyDocument, activeIndex: number, time: number): void {
  doc.lines.forEach((line, index) => {
    const distance = Math.abs(index - activeIndex);
    const isActive = distance === 0 || getElementState(time, line.start, line.end) === "Active";
    const blur = isActive ? 0 : Math.min(BLUR_MULTIPLIER * distance, MAX_BLUR);
    setStyleIfChanged(line.element, "--BlurAmount", `${blur}px`, 0.25);
  });
}

function applyLineClasses(line: SpicyLine, state: ElementState, time: number): void {
  setClass(line.element, "Active", state === "Active");
  setClass(line.element, "NotSung", state === "NotSung");
  setClass(line.element, "Sung", state === "Sung");
  if (!line.isDotLine) return;
  // The dots collapse shortly before the next line starts, and stay collapsed while not playing.
  const preHidden = state === "NotSung" || (state === "Active" && time > line.end - PRE_HIDDEN_DOT_LINE_MS);
  setClass(line.element, "pre-hidden", preHidden);
}

function animateLineGlow(line: SpicyLine, state: ElementState, ctx: FrameContext): void {
  const glow = line.glow;
  if (!glow) return;
  const percentage = getProgress(ctx.time, line.start, line.end);
  const point = state === "Active" ? percentage : state === "NotSung" ? 0 : 1;
  glow.setGoal(LINE_GLOW_SPLINE.at(point), ctx.snap);
  const value = glow.step(ctx.dt);
  if (!glow.canSleep()) ctx.awake = true;
  const gradient = state === "Active" ? percentage * 100 : state === "NotSung" ? -20 : 100;
  setStyleIfChanged(line.element, "--gradient-position", `${gradient}%`);
  setStyleIfChanged(line.element, "--text-shadow-blur-radius", `${4 + 8 * value}px`, 0.5);
  setStyleIfChanged(line.element, "--text-shadow-opacity", `${value * 50}%`, 1);
}

function settleLine(line: SpicyLine, state: ElementState, ctx: FrameContext, far: boolean): void {
  if (line.settledAs === state) return;
  const settleCtx: FrameContext = { ...ctx, snap: ctx.snap || far, awake: false };
  for (const syllable of line.syllables) animateSyllable(syllable, settleCtx, state);
  if (line.glow) animateLineGlow(line, state, settleCtx);
  if (settleCtx.awake) ctx.awake = true;
  else line.settledAs = state;
}

/** The first active line, else the next line to be sung, else the last line. */
function focusIndex(doc: SpicyDocument, time: number): number {
  const active = doc.lines.findIndex((line) => getElementState(time, line.start, line.end) === "Active");
  if (active !== -1) return active;
  const upcoming = doc.lines.findIndex((line) => time < line.start);
  return upcoming === -1 ? doc.lines.length - 1 : upcoming;
}

// -- Animator -----------------------------------------------------------------

/** Advances every line by one frame. Returns true while any spring still moves. */
function animateDocument(doc: SpicyDocument, state: AnimatorState, ctx: FrameContext): boolean {
  const focus = focusIndex(doc, ctx.time);

  doc.lines.forEach((line, index) => {
    const lineState = getElementState(ctx.time, line.start, line.end);
    applyLineClasses(line, lineState, ctx.time);

    if (lineState !== "Active") {
      settleLine(line, lineState, ctx, Math.abs(index - focus) > ANIMATED_SETTLE_RADIUS);
      return;
    }

    line.settledAs = null;
    if (state.blurredAround !== index) {
      applyBlur(doc, index, ctx.time);
      state.blurredAround = index;
    }
    for (const syllable of line.syllables) animateSyllable(syllable, ctx);
    animateLineGlow(line, lineState, ctx);
  });

  flushStyleBatch();
  return ctx.awake;
}

function createAnimatorState(): AnimatorState {
  return { blurredAround: null };
}

// -- Exports ------------------------------------------------------------------

export { animateDocument, createAnimatorState };
export type { AnimatorState };
