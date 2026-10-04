// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Applyer/Synced/Syllable.ts, src/utils/Lyrics/Applyer/Utils/Emphasize.ts
// and src/utils/Lyrics/Applyer/Utils/IsLetterCapable.ts (fcc5f83).

import { IDLE_LYRICS_SCALE, createLetterSprings, createWordSprings } from "@/views/preview/spicy/curves";
import type { SyllableData, VocalData } from "@/views/preview/spicy/lyrics-data";
import type { SpicyLetter, SpicyLetterGroup, SpicyLine, SpicySyllable, SpicyWord } from "@/views/preview/spicy/model";
import { isRtl } from "@/views/preview/spicy/text-direction";

// -- Constants ----------------------------------------------------------------

/** A syllable held at least this long (ms) is split into letters that light up one by one. */
const LETTER_CAPABLE_MIN_DURATION_MS = 1000;

/** Emphasized words finish their letter sweep this much (ms) before the syllable ends. */
const EMPHASIS_END_TRIM_MS = 250;

// -- Helpers ------------------------------------------------------------------

function seconds(value: number): number {
  return value * 1000;
}

function applyIdleStyles(element: HTMLElement, yOffset: number, withGradient: boolean): void {
  if (withGradient) element.style.setProperty("--gradient-position", "-20%");
  element.style.setProperty("--text-shadow-opacity", "0%");
  element.style.setProperty("--text-shadow-blur-radius", "4px");
  element.style.scale = String(IDLE_LYRICS_SCALE);
  element.style.transform = `translateY(calc(var(--DefaultLyricsSize) * ${yOffset}))`;
}

function markPosition(element: HTMLElement, syllable: SyllableData, isLast: boolean): void {
  if (isLast) element.classList.add("LastWordInLine");
  else if (syllable.isPartOfWord) element.classList.add("PartOfWord");
}

function createLetterGroup(syllable: SyllableData, isBackground: boolean): SpicyLetterGroup {
  const element = document.createElement("div");
  const start = seconds(syllable.start);
  const end = seconds(syllable.end) - EMPHASIS_END_TRIM_MS;
  const characters = [...syllable.text];
  const letterDuration = (end - start) / characters.length;

  const letters: SpicyLetter[] = characters.map((character, index) => {
    const letter = document.createElement("span");
    letter.textContent = character;
    letter.classList.add("letter", "Emphasis");
    // Whitespace inside an inline-block collapses to a 0px box; CSS gives it a width.
    if (character.trim().length === 0) letter.classList.add("SpaceLetter");
    if (index === characters.length - 1) letter.classList.add("LastLetterInWord");
    applyIdleStyles(letter, 0.02, true);
    element.appendChild(letter);
    const letterStart = start + index * letterDuration;
    return { element: letter, start: letterStart, end: letterStart + letterDuration, springs: createLetterSprings() };
  });

  element.classList.add("letterGroup");
  if (isBackground) element.classList.add("bg-word");
  applyIdleStyles(element, 0.02, false);
  return { kind: "letterGroup", element, start, end, springs: createWordSprings(), letters };
}

function createWord(syllable: SyllableData, isBackground: boolean): SpicyWord {
  const element = document.createElement("span");
  element.textContent = syllable.text;
  element.classList.add("word");
  if (isBackground) element.classList.add("bg-word");
  applyIdleStyles(element, 0.01, true);
  return {
    kind: "word",
    element,
    start: seconds(syllable.start),
    end: seconds(syllable.end),
    springs: createWordSprings(),
  };
}

function createSyllable(syllable: SyllableData, isBackground: boolean): SpicySyllable {
  const duration = seconds(syllable.end) - seconds(syllable.start);
  const letterCapable = duration >= LETTER_CAPABLE_MIN_DURATION_MS && !isRtl(syllable.text);
  return letterCapable ? createLetterGroup(syllable, isBackground) : createWord(syllable, isBackground);
}

/** Appends syllables to the line, wrapping runs of word parts in one unbreakable group. */
function appendSyllables(lineElement: HTMLElement, vocal: VocalData, isBackground: boolean): SpicySyllable[] {
  const syllables: SpicySyllable[] = [];
  let wordGroup: HTMLSpanElement | null = null;

  vocal.syllables.forEach((data, index, all) => {
    if (isRtl(data.text)) lineElement.classList.add("rtl");
    const syllable = createSyllable(data, isBackground);
    markPosition(syllable.element, data, index === all.length - 1);
    syllables.push(syllable);

    const previous = all[index - 1];
    if (data.isPartOfWord || (previous?.isPartOfWord && wordGroup)) {
      if (!wordGroup) {
        wordGroup = document.createElement("span");
        wordGroup.classList.add("word-group");
        lineElement.appendChild(wordGroup);
      }
      wordGroup.appendChild(syllable.element);
      if (!data.isPartOfWord) wordGroup = null;
      return;
    }
    wordGroup = null;
    lineElement.appendChild(syllable.element);
  });

  return syllables;
}

// -- Builders -----------------------------------------------------------------

function createSyllableLine(vocal: VocalData, oppositeAligned: boolean, isBackground: boolean): SpicyLine {
  const element = document.createElement("div");
  element.classList.add("line");
  if (isBackground) element.classList.add("bg-line");
  if (oppositeAligned) element.classList.add("OppositeAligned");
  const syllables = appendSyllables(element, vocal, isBackground);
  return {
    element,
    start: seconds(vocal.start),
    end: seconds(vocal.end),
    syllables,
    isDotLine: false,
    isBackground,
    seekTime: syllables[0]?.start ?? seconds(vocal.start),
    glow: null,
    settledAs: "NotSung",
  };
}

// -- Exports ------------------------------------------------------------------

export { createSyllableLine };
