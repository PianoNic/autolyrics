import type { LyricLine, LyricWord } from "@/auto/api/autolyrics-client";

// -- Constants ----------------------------------------------------------------

// Flags the backend sets on words, phrased for a reviewer. Only these count as "needs a look";
// "interpolated" alone is informational (a word with no letters, such as a dash, gets a guessed
// time) and so is a DeepSeek edit the reviewer can see in the change list.
const FLAG_LABELS: Record<string, string> = {
  "low-confidence": "The aligner was unsure about this word",
  reanchored: "Moved next to its neighbour; check the timing",
  "llm-note": "DeepSeek asked for a second look at this line",
  transcribed: "Heard by Whisper; no lyrics source had this song",
  "line-timing": "The aligner could not hear this line; timed from the lyrics source's line",
  "llm-insert": "Line added from other lyrics sources",
  "llm-edit": "Text changed by DeepSeek",
  interpolated: "Time estimated from the neighbouring words",
  "too-long": "Held unusually long",
  "too-short": "Unusually short",
  overlap: "Overlaps the previous word",
  "big-gap": "Long pause before this word",
  "out-of-order": "Starts before the previous line",
  "past-end": "Ends after the song",
};

const REVIEW_FLAGS: ReadonlySet<string> = new Set([
  "low-confidence",
  "transcribed",
  "line-timing",
  "reanchored",
  "llm-note",
  "llm-insert",
  "too-long",
  "too-short",
  "overlap",
  "big-gap",
  "out-of-order",
  "past-end",
]);

// -- Helpers ------------------------------------------------------------------

function needsReview(word: LyricWord): boolean {
  return word.flags.some((flag) => REVIEW_FLAGS.has(flag));
}

function lineNeedsReview(line: LyricLine): boolean {
  return [...line.words, ...line.background].some(needsReview);
}

function describeFlags(word: LyricWord): string {
  return word.flags.map((flag) => FLAG_LABELS[flag] ?? flag).join(" · ");
}

function lineBounds(line: LyricLine): { begin: number; end: number } | null {
  const timed = [...line.words, ...line.background].filter(
    (word): word is LyricWord & { begin: number; end: number } => word.begin !== null && word.end !== null,
  );
  if (timed.length > 0) {
    return { begin: Math.min(...timed.map((w) => w.begin)), end: Math.max(...timed.map((w) => w.end)) };
  }
  if (line.begin !== null && line.end !== null) return { begin: line.begin, end: line.end };
  return null;
}

function lineDisplay(line: LyricLine): string {
  const main = line.words.map((word) => word.text).join("").trim();
  if (line.background.length === 0) return main;
  const background = line.background.map((word) => word.text).join("").trim().replace(/^\((.*)\)$/, "$1");
  return `${main} (${background})`.trim();
}

// -- Exports ------------------------------------------------------------------

export { FLAG_LABELS, describeFlags, lineBounds, lineDisplay, lineNeedsReview, needsReview };
