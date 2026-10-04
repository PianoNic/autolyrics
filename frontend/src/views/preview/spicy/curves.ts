// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Animator/Lyrics/LyricsAnimator.ts and src/utils/Lyrics/Animator/Shared.ts (fcc5f83).
// Only the default ("non simple") lyrics mode is ported, so the simple-mode curves are gone.

import { createSpline } from "@/views/preview/spicy/spline";
import { Spring } from "@/views/preview/spicy/spring";

// -- Types --------------------------------------------------------------------

interface WordSprings {
  scale: Spring;
  yOffset: Spring;
  glow: Spring;
}

interface DotSprings extends WordSprings {
  opacity: Spring;
}

// -- Curves -------------------------------------------------------------------

const SCALE_SPLINE = createSpline([
  { progress: 0, value: 0.95 },
  { progress: 0.7, value: 1.0505 },
  { progress: 1, value: 1 },
]);

const LETTER_SCALE_SPLINE = createSpline([
  { progress: 0, value: 0.95 },
  { progress: 0.7, value: 1.175 },
  { progress: 1, value: 1 },
]);

const Y_OFFSET_SPLINE = createSpline([
  { progress: 0, value: 1 / 100 },
  { progress: 0.9, value: -(1 / 60) },
  { progress: 1, value: 0 },
]);

const LETTER_Y_OFFSET_SPLINE = createSpline([
  { progress: 0, value: 1 / 100 },
  { progress: 0.9, value: -(1 / 56) },
  { progress: 1, value: 0 },
]);

const GLOW_SPLINE = createSpline([
  { progress: 0, value: 0 },
  { progress: 0.15, value: 1 },
  { progress: 0.6, value: 1 },
  { progress: 1, value: 0 },
]);

const DOT_SCALE_SPLINE = createSpline([
  { progress: 0, value: 0.75 },
  { progress: 0.7, value: 1.05 },
  { progress: 1, value: 1 },
]);

const DOT_Y_OFFSET_SPLINE = createSpline([
  { progress: 0, value: 0 },
  { progress: 0.9, value: -0.12 },
  { progress: 1, value: 0 },
]);

const DOT_GLOW_SPLINE = createSpline([
  { progress: 0, value: 0 },
  { progress: 0.6, value: 1 },
  { progress: 1, value: 1 },
]);

const DOT_OPACITY_SPLINE = createSpline([
  { progress: 0, value: 0.35 },
  { progress: 0.6, value: 1 },
  { progress: 1, value: 1 },
]);

const LINE_GLOW_SPLINE = createSpline([
  { progress: 0, value: 0 },
  { progress: 0.5, value: 1 },
  { progress: 1, value: 0 },
]);

// -- Constants ----------------------------------------------------------------

const Y_OFFSET_DAMPING = 0.4;
const Y_OFFSET_FREQUENCY = 1.45;
const SCALE_DAMPING = 0.64;
const SCALE_FREQUENCY = 0.88;
const GLOW_DAMPING = 0.56;
const GLOW_FREQUENCY = 1.18;

const DOT_Y_OFFSET_DAMPING = 0.4;
const DOT_Y_OFFSET_FREQUENCY = 1.25;
const DOT_SCALE_DAMPING = 0.6;
const DOT_SCALE_FREQUENCY = 0.7;
const DOT_GLOW_DAMPING = 0.5;
const DOT_GLOW_FREQUENCY = 1;
const DOT_OPACITY_DAMPING = 0.5;
const DOT_OPACITY_FREQUENCY = 1;

const LINE_GLOW_DAMPING = 0.5;
const LINE_GLOW_FREQUENCY = 1;

const LETTER_GLOW_OPACITY_MULTIPLIER = 185;
const SUNG_LETTER_GLOW = 0.2;

const IDLE_LYRICS_SCALE = 0.95;
const BLUR_MULTIPLIER = 1.25;

// -- Factories ----------------------------------------------------------------

function createWordSprings(): WordSprings {
  return {
    scale: new Spring(SCALE_SPLINE.at(0), SCALE_FREQUENCY, SCALE_DAMPING),
    yOffset: new Spring(Y_OFFSET_SPLINE.at(0), Y_OFFSET_FREQUENCY, Y_OFFSET_DAMPING),
    glow: new Spring(GLOW_SPLINE.at(0), GLOW_FREQUENCY, GLOW_DAMPING),
  };
}

function createLetterSprings(): WordSprings {
  return {
    scale: new Spring(LETTER_SCALE_SPLINE.at(0), SCALE_FREQUENCY, SCALE_DAMPING),
    yOffset: new Spring(LETTER_Y_OFFSET_SPLINE.at(0), Y_OFFSET_FREQUENCY, Y_OFFSET_DAMPING),
    glow: new Spring(GLOW_SPLINE.at(0), GLOW_FREQUENCY, GLOW_DAMPING),
  };
}

function createDotSprings(): DotSprings {
  return {
    scale: new Spring(DOT_SCALE_SPLINE.at(0), DOT_SCALE_FREQUENCY, DOT_SCALE_DAMPING),
    yOffset: new Spring(DOT_Y_OFFSET_SPLINE.at(0), DOT_Y_OFFSET_FREQUENCY, DOT_Y_OFFSET_DAMPING),
    glow: new Spring(DOT_GLOW_SPLINE.at(0), DOT_GLOW_FREQUENCY, DOT_GLOW_DAMPING),
    opacity: new Spring(DOT_OPACITY_SPLINE.at(0), DOT_OPACITY_FREQUENCY, DOT_OPACITY_DAMPING),
  };
}

function createLineGlowSpring(): Spring {
  return new Spring(LINE_GLOW_SPLINE.at(0), LINE_GLOW_FREQUENCY, LINE_GLOW_DAMPING);
}

// -- Exports ------------------------------------------------------------------

export {
  BLUR_MULTIPLIER,
  DOT_GLOW_SPLINE,
  DOT_OPACITY_SPLINE,
  DOT_SCALE_SPLINE,
  DOT_Y_OFFSET_SPLINE,
  GLOW_SPLINE,
  IDLE_LYRICS_SCALE,
  LETTER_GLOW_OPACITY_MULTIPLIER,
  LETTER_SCALE_SPLINE,
  LETTER_Y_OFFSET_SPLINE,
  LINE_GLOW_SPLINE,
  SCALE_SPLINE,
  SUNG_LETTER_GLOW,
  Y_OFFSET_SPLINE,
  createDotSprings,
  createLetterSprings,
  createLineGlowSpring,
  createWordSprings,
};
export type { DotSprings, WordSprings };
