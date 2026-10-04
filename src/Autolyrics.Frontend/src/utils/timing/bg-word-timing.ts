import { manualBackgroundWordEdit } from "@/domain/line/background";
import { createWordTimingOps } from "@/utils/timing/word-timing-ops";

const { setBegin, setBoundary } = createWordTimingOps({
  getWords: (line) => line.backgroundWords,
  writeWords: (_line, words) => ({ backgroundWords: words }),
  buildBoundaryUpdate: manualBackgroundWordEdit,
});

export { setBegin as setBgWordBegin, setBoundary as setBgWordBoundary };
