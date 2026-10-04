// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/ttml/parser.ts and src/utils/Lyrics/EmptyLines.ts (fcc5f83).
// Builds the shapes Spicy's appliers consume (Lead / Background / OppositeAligned) from
// Composer's own parsed lines instead of Spicy's TTML parser.

import type { LyricLine } from "@/domain/line/model";
import { mainBounds } from "@/domain/line/bounds";
import { isWordSynced } from "@/domain/line/predicates";
import { timingGranularityOf } from "@/domain/project/timing-granularity";
import type { WordTiming } from "@/domain/word/timing";
import { firstBegin, lastEnd } from "@/domain/word/bounds";
import { parseTtml } from "@/utils/lyrics-parsers/ttml";

// -- Types --------------------------------------------------------------------

/** Times are in seconds, like Spicy's parsed lyrics. */
interface SyllableData {
  text: string;
  start: number;
  end: number;
  isPartOfWord: boolean;
}

interface VocalData {
  start: number;
  end: number;
  syllables: SyllableData[];
}

interface SyllableLineData {
  lead: VocalData;
  background: VocalData[];
  oppositeAligned: boolean;
}

interface LineSyncedData {
  text: string;
  start: number;
  end: number;
  oppositeAligned: boolean;
}

type SpicyLyricsData =
  | { kind: "Syllable"; start: number; lines: SyllableLineData[] }
  | { kind: "Line"; start: number; lines: LineSyncedData[] };

// -- Constants ----------------------------------------------------------------

// Spicy's TTML parser puts v2 and v2000 on the opposite side; v1 and every other voice stay put.
const OPPOSITE_ALIGNED_AGENTS = new Set(["v2", "v2000"]);

// -- Helpers ------------------------------------------------------------------

function stripZeroWidth(text: string): string {
  return text.replace(/\u200B|\u200C|\u200D|\uFEFF/g, "");
}

function hasRenderableText(text: string): boolean {
  return stripZeroWidth(text).trim() !== "";
}

function toSyllables(words: readonly WordTiming[]): SyllableData[] {
  const renderable = words.filter((word) => hasRenderableText(word.text));
  return renderable.map((word, index) => ({
    text: stripZeroWidth(word.text).trim(),
    start: word.begin,
    end: word.end,
    // A syllable that runs straight into the next one (no trailing space) is part of a longer word.
    isPartOfWord: index < renderable.length - 1 && !/\s$/.test(word.text),
  }));
}

function toVocal(words: readonly WordTiming[]): VocalData | null {
  const syllables = toSyllables(words);
  if (syllables.length === 0) return null;
  return { start: firstBegin(words), end: lastEnd(words), syllables };
}

function toSyllableLine(line: LyricLine): SyllableLineData | null {
  const bounds = mainBounds(line);
  if (!bounds) return null;
  const lead = isWordSynced(line)
    ? toVocal(line.words ?? [])
    : toVocal([{ text: line.text, begin: bounds.begin, end: bounds.end }]);
  if (!lead) return null;
  const background = line.backgroundWords ? toVocal(line.backgroundWords) : null;
  return {
    lead,
    background: background ? [background] : [],
    oppositeAligned: OPPOSITE_ALIGNED_AGENTS.has(line.agentId),
  };
}

function toLineSynced(line: LyricLine): LineSyncedData | null {
  const bounds = mainBounds(line);
  if (!bounds || !hasRenderableText(line.text)) return null;
  return {
    text: stripZeroWidth(line.text).trim(),
    start: bounds.begin,
    end: bounds.end,
    oppositeAligned: OPPOSITE_ALIGNED_AGENTS.has(line.agentId),
  };
}

function isPresent<T>(value: T | null): value is T {
  return value !== null;
}

// -- Conversion ---------------------------------------------------------------

function buildSpicyLyrics(lines: readonly LyricLine[]): SpicyLyricsData {
  if (timingGranularityOf(lines) === "word") {
    const syllableLines = lines.map(toSyllableLine).filter(isPresent);
    return { kind: "Syllable", start: syllableLines[0]?.lead.start ?? 0, lines: syllableLines };
  }
  const lineSynced = lines.map(toLineSynced).filter(isPresent);
  return { kind: "Line", start: lineSynced[0]?.start ?? 0, lines: lineSynced };
}

function parseSpicyLyrics(ttml: string): SpicyLyricsData {
  return buildSpicyLyrics(parseTtml(ttml).lines);
}

// -- Exports ------------------------------------------------------------------

export { buildSpicyLyrics, parseSpicyLyrics };
export type { LineSyncedData, SpicyLyricsData, SyllableData, SyllableLineData, VocalData };
