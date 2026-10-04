// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/lyrics.ts (fcc5f83), the LyricsObject line / syllable records.

import type { DotSprings, WordSprings } from "@/views/preview/spicy/curves";
import type { Spring } from "@/views/preview/spicy/spring";

// -- Types --------------------------------------------------------------------

type LyricsKind = "Syllable" | "Line";

type ElementState = "NotSung" | "Active" | "Sung";

/** Every time here is in milliseconds, like Spicy's runtime records. */
interface TimedElement {
  element: HTMLElement;
  start: number;
  end: number;
}

interface SpicyLetter extends TimedElement {
  springs: WordSprings;
}

interface SpicyWord extends TimedElement {
  kind: "word";
  springs: WordSprings;
}

interface SpicyLetterGroup extends TimedElement {
  kind: "letterGroup";
  springs: WordSprings;
  letters: SpicyLetter[];
}

interface SpicyDot extends TimedElement {
  kind: "dot";
  springs: DotSprings;
}

type SpicySyllable = SpicyWord | SpicyLetterGroup | SpicyDot;

interface SpicyLine extends TimedElement {
  syllables: SpicySyllable[];
  isDotLine: boolean;
  isBackground: boolean;
  /** Where a click on the line seeks to: its first syllable, or the line start. */
  seekTime: number;
  /** Line-synced lyrics glow the whole line instead of single words. */
  glow: Spring | null;
  /** The resting state the syllables last settled into; null while they still move. */
  settledAs: ElementState | null;
}

interface SpicyDocument {
  kind: LyricsKind;
  container: HTMLElement;
  lines: SpicyLine[];
}

// -- Helpers ------------------------------------------------------------------

function getElementState(time: number, start: number, end: number): ElementState {
  if (time < start) return "NotSung";
  if (time >= end) return "Sung";
  return "Active";
}

function getProgress(time: number, start: number, end: number): number {
  if (time <= start) return 0;
  if (time >= end) return 1;
  return (time - start) / (end - start);
}

// -- Exports ------------------------------------------------------------------

export { getElementState, getProgress };
export type {
  ElementState,
  SpicyDocument,
  SpicyDot,
  SpicyLetter,
  SpicyLetterGroup,
  SpicyLine,
  SpicySyllable,
  SpicyWord,
};
