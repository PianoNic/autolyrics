import type { Agent } from "@/domain/agent/model";
import type { LinkGroup } from "@/domain/group/template";
import type { LyricLine } from "@/domain/line/model";
import type { ProjectMetadata } from "@/domain/project/metadata";

// -- Types --------------------------------------------------------------------

interface ParseIssue {
  line: number;
  text: string;
  reason: "empty-document";
}

interface ParseResult {
  lines: LyricLine[];
  metadata: Partial<ProjectMetadata>;
  hasTimingData: boolean;
  issues: ParseIssue[];
  agents?: Agent[];
  groups?: LinkGroup[];
}

// -- Helpers ------------------------------------------------------------------

function generateLineId(): string {
  return crypto.randomUUID();
}

// -- Exports ------------------------------------------------------------------

export { generateLineId };
export type { ParseResult };
