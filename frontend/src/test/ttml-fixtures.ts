import type { LyricLine } from "@/domain/line/model";
import { useProjectStore } from "@/stores/project";
import { createLine } from "@/test/factories";
import { generateTTML } from "@/utils/ttml";

// -- Fixtures -----------------------------------------------------------------

function threeSyncedLines(): LyricLine[] {
  return [
    createLine({
      id: "line-a",
      text: "first line here",
      words: [
        { text: "first ", begin: 2, end: 3 },
        { text: "line ", begin: 3, end: 4 },
        { text: "here", begin: 4, end: 6 },
      ],
    }),
    createLine({
      id: "line-b",
      text: "second line now",
      words: [
        { text: "second ", begin: 12, end: 14 },
        { text: "line ", begin: 14, end: 16 },
        { text: "now", begin: 16, end: 18 },
      ],
    }),
    createLine({
      id: "line-c",
      text: "third line ends",
      words: [
        { text: "third ", begin: 24, end: 26 },
        { text: "line ", begin: 26, end: 28 },
        { text: "ends", begin: 28, end: 30 },
      ],
    }),
  ];
}

/**
 * Three word-synced lyric lines with wide, non-overlapping time windows,
 * rendered to a real TTML string via the production generator. Used by the
 * preview renderer tests to drive highlight and line-click behaviour.
 *
 * Windows: "first line here" 2-6s, "second line now" 12-18s, "third line ends"
 * 24-30s.
 *
 * `durationSeconds` becomes the document's `dur`, the only channel a song
 * duration reaches a lyrics parser through.
 */
function buildSyncedTtml(durationSeconds?: number): string {
  const { metadata, agents } = useProjectStore.getState();
  return generateTTML({ metadata, agents, lines: threeSyncedLines(), groups: [], duration: durationSeconds });
}

/** The three `buildSyncedTtml` lines, credited to `songwriters` the way Composer writes them. */

/** One timed line credited through Apple's `<iTunesMetadata><songwriters>` list, as an imported Apple TTML carries it. */

/** One word-synced line 2-6s carrying a background vocal over its second half. */
function buildBackgroundVocalTtml(): string {
  const lines = [
    createLine({
      id: "line-bg",
      text: "first line here",
      words: [
        { text: "first ", begin: 2, end: 3 },
        { text: "line ", begin: 3, end: 4 },
        { text: "here", begin: 4, end: 6 },
      ],
      backgroundText: "ooh ahh",
      backgroundWords: [
        { text: "ooh ", begin: 4, end: 5 },
        { text: "ahh", begin: 5, end: 6 },
      ],
    }),
  ];
  const { metadata, agents } = useProjectStore.getState();
  return generateTTML({ metadata, agents, lines, groups: [] });
}

/** One synced Korean line with a timed transliteration and an English translation. */

/** One synced Korean line whose alternate-language background vocal falls in a foreground pause. */

/** One synced line whose alternate tracks are identical to the main text. */

// -- Exports ------------------------------------------------------------------

export { buildBackgroundVocalTtml, buildSyncedTtml };
