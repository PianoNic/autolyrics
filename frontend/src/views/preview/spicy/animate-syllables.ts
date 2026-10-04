// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Animator/Lyrics/LyricsAnimator.ts (fcc5f83), the per-word, per-letter
// and per-dot spring animation inside Animate(). Simple-lyrics-mode branches are not ported.

import {
  DOT_GLOW_SPLINE,
  DOT_OPACITY_SPLINE,
  DOT_SCALE_SPLINE,
  DOT_Y_OFFSET_SPLINE,
  GLOW_SPLINE,
  LETTER_GLOW_OPACITY_MULTIPLIER,
  LETTER_SCALE_SPLINE,
  LETTER_Y_OFFSET_SPLINE,
  SCALE_SPLINE,
  SUNG_LETTER_GLOW,
  Y_OFFSET_SPLINE,
} from "@/views/preview/spicy/curves";
import {
  type ElementState,
  type SpicyDot,
  type SpicyLetterGroup,
  type SpicySyllable,
  type SpicyWord,
  getElementState,
  getProgress,
} from "@/views/preview/spicy/model";
import { easeSinOut } from "@/views/preview/spicy/spline";
import type { Spring } from "@/views/preview/spicy/spring";
import { setStyleIfChanged } from "@/views/preview/spicy/style-writer";

// -- Types --------------------------------------------------------------------

interface FrameContext {
  /** Playback position in milliseconds. */
  time: number;
  /** Seconds since the previous frame. */
  dt: number;
  /** Jump every spring straight to its goal instead of animating there. */
  snap: boolean;
  /** Set when any spring stepped this frame is still moving. */
  awake: boolean;
}

// -- Helpers ------------------------------------------------------------------

function drive(spring: Spring, goal: number, ctx: FrameContext): number {
  spring.setGoal(goal, ctx.snap);
  const value = spring.step(ctx.dt);
  if (!spring.canSleep()) ctx.awake = true;
  return value;
}

function writeTransform(el: HTMLElement, scale: number, yOffset: number): void {
  setStyleIfChanged(el, "scale", `${scale}`, 0.001);
  setStyleIfChanged(el, "transform", `translate3d(0, calc(var(--DefaultLyricsSize) * ${yOffset}), 0)`, 0.0001, yOffset);
}

function writeGlow(el: HTMLElement, blurRadius: number, opacity: number): void {
  setStyleIfChanged(el, "--text-shadow-blur-radius", `${blurRadius}px`, 0.5);
  setStyleIfChanged(el, "--text-shadow-opacity", `${opacity}%`, 1);
}

function progressPoint(state: ElementState, percentage: number): number {
  if (state === "Active") return percentage;
  return state === "NotSung" ? 0 : 1;
}

function gradientFor(state: ElementState, percentage: number): number {
  if (state === "Active") return -20 + 120 * percentage;
  return state === "NotSung" ? -20 : 100;
}

// -- Words --------------------------------------------------------------------

function animateWord(word: SpicyWord | SpicyLetterGroup, state: ElementState, percentage: number, ctx: FrameContext) {
  const point = progressPoint(state, percentage);
  const scale = drive(word.springs.scale, SCALE_SPLINE.at(point), ctx);
  const yOffset = drive(word.springs.yOffset, Y_OFFSET_SPLINE.at(point), ctx);
  const glow = drive(word.springs.glow, GLOW_SPLINE.at(point), ctx);
  writeTransform(word.element, scale, yOffset);
  if (word.kind === "letterGroup") return;
  setStyleIfChanged(word.element, "--gradient-position", `${gradientFor(state, percentage)}%`);
  writeGlow(word.element, 4 + 2 * glow, Math.min(glow * 35, 100));
}

function animateDot(dot: SpicyDot, state: ElementState, percentage: number, ctx: FrameContext): void {
  const point = progressPoint(state, percentage);
  const scale = drive(dot.springs.scale, DOT_SCALE_SPLINE.at(point), ctx);
  const yOffset = drive(dot.springs.yOffset, DOT_Y_OFFSET_SPLINE.at(point), ctx);
  const glow = drive(dot.springs.glow, DOT_GLOW_SPLINE.at(point), ctx);
  const opacity = drive(dot.springs.opacity, DOT_OPACITY_SPLINE.at(point), ctx);
  writeTransform(dot.element, scale, yOffset);
  setStyleIfChanged(dot.element, "opacity", `${opacity}`, 0.001);
  writeGlow(dot.element, 4 + 6 * glow, glow * 90);
}

// -- Letters ------------------------------------------------------------------

interface LetterTargets {
  scale: number;
  yOffset: number;
  glow: number;
  gradient: number;
}

function activeLetterTargets(group: SpicyLetterGroup, index: number, ctx: FrameContext): LetterTargets {
  const activeIndex = group.letters.findIndex(
    (letter) => getElementState(ctx.time, letter.start, letter.end) === "Active",
  );
  const letter = group.letters[index];
  const letterState = getElementState(ctx.time, letter.start, letter.end);
  const targets = {
    scale: LETTER_SCALE_SPLINE.at(0),
    yOffset: LETTER_Y_OFFSET_SPLINE.at(0),
    glow: GLOW_SPLINE.at(0),
    gradient: -20,
  };

  if (activeIndex !== -1) {
    const active = group.letters[activeIndex];
    const percentage = getProgress(ctx.time, active.start, active.end);
    // The active letter peaks; its neighbours follow with a steep falloff.
    const distance = Math.abs(index - activeIndex);
    const falloff = Math.max(0, 1 / (1 + distance ** 2.8));
    const glowFalloff = Math.max(0, 1 / (1 + distance * 0.9));
    targets.scale += (LETTER_SCALE_SPLINE.at(percentage) - targets.scale) * falloff;
    targets.yOffset += (LETTER_Y_OFFSET_SPLINE.at(percentage) - targets.yOffset) * falloff;
    targets.glow += (GLOW_SPLINE.at(percentage) - targets.glow) * glowFalloff;
    if (index === activeIndex) targets.gradient = -20 + 120 * easeSinOut(percentage);
  }

  if (letterState === "NotSung") {
    return {
      scale: LETTER_SCALE_SPLINE.at(0),
      yOffset: LETTER_Y_OFFSET_SPLINE.at(0),
      glow: GLOW_SPLINE.at(0),
      gradient: -20,
    };
  }
  if (letterState === "Sung") {
    targets.gradient = 100;
    if (activeIndex === -1) targets.glow = GLOW_SPLINE.at(SUNG_LETTER_GLOW);
  }
  return targets;
}

function restingLetterTargets(state: ElementState): LetterTargets {
  const point = state === "NotSung" ? 0 : 1;
  return {
    scale: LETTER_SCALE_SPLINE.at(point),
    yOffset: LETTER_Y_OFFSET_SPLINE.at(point),
    glow: GLOW_SPLINE.at(point),
    gradient: state === "NotSung" ? -20 : 100,
  };
}

function animateLetters(group: SpicyLetterGroup, state: ElementState, ctx: FrameContext): void {
  group.letters.forEach((letter, index) => {
    const targets = state === "Active" ? activeLetterTargets(group, index, ctx) : restingLetterTargets(state);
    const scale = drive(letter.springs.scale, targets.scale, ctx);
    const yOffset = drive(letter.springs.yOffset, targets.yOffset, ctx);
    const glow = drive(letter.springs.glow, targets.glow, ctx);
    setStyleIfChanged(letter.element, "--gradient-position", `${targets.gradient}%`);
    writeTransform(letter.element, scale, yOffset * 2);
    writeGlow(letter.element, 4 + 12 * glow, glow * LETTER_GLOW_OPACITY_MULTIPLIER);
  });
}

// -- Dispatch -----------------------------------------------------------------

/** Animates a syllable toward `forcedState`, or toward wherever the clock puts it. */
function animateSyllable(syllable: SpicySyllable, ctx: FrameContext, forcedState?: ElementState): void {
  const state = forcedState ?? getElementState(ctx.time, syllable.start, syllable.end);
  const percentage = getProgress(ctx.time, syllable.start, syllable.end);
  if (syllable.kind === "dot") {
    animateDot(syllable, state, percentage, ctx);
    return;
  }
  animateWord(syllable, state, percentage, ctx);
  if (syllable.kind === "letterGroup") animateLetters(syllable, state, ctx);
}

// -- Exports ------------------------------------------------------------------

export { animateSyllable };
export type { FrameContext };
