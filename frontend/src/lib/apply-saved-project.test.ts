import { beforeEach, describe, expect, it } from "vitest";
import type { Agent } from "@/domain/agent/model";
import { applySavedProject } from "@/lib/apply-saved-project";
import type { SavedProject } from "@/lib/persistence";
import { useProjectStore } from "@/stores/project";
import { createGroup, createLine, createProjectSaveInput } from "@/test/factories";
import { resetAllStores } from "@/test/stores";

const SAVED_AGENTS: Agent[] = [
  { id: "v1", type: "person", name: "Saved Lead" },
  { id: "v2", type: "person", name: "Saved Duet" },
];

function savedProject(overrides: Partial<SavedProject> = {}): SavedProject {
  return {
    version: 3,
    savedAt: 0,
    ...createProjectSaveInput({
      agents: SAVED_AGENTS,
      lines: [createLine({ id: "b1", text: "saved line", groupId: "gb", instanceIdx: 0, templateLineIdx: 0 })],
      groups: [createGroup({ id: "gb", label: "Saved group" })],
    }),
    ...overrides,
  };
}

describe("applySavedProject", () => {
  beforeEach(resetAllStores);

  it("restores the saved lines, groups and agents", () => {
    applySavedProject(savedProject());

    const state = useProjectStore.getState();
    expect(state.lines.map((line) => line.id)).toEqual(["b1"]);
    expect(state.groups.map((group) => group.id)).toEqual(["gb"]);
    expect(state.agents.map((agent) => agent.name)).toEqual(["Saved Lead", "Saved Duet"]);
  });

  it("restores the priming flag the timings were saved against", () => {
    applySavedProject(savedProject({ primingStripped: true }));
    expect(useProjectStore.getState().primingStripped).toBe(true);
  });

  it("leaves the restored project clean", () => {
    applySavedProject(savedProject());
    expect(useProjectStore.getState().isDirty).toBe(false);
  });

  it("reports malformed fields and falls back to safe defaults", () => {
    const issues = applySavedProject(savedProject({ agents: [] }));
    expect(issues).toEqual(["missing or empty agents"]);
    expect(useProjectStore.getState().agents.length).toBeGreaterThan(0);
  });

  describe("regressions", () => {
    it("regression: drops imported metadata keys a hand-edited record does not know", () => {
      const keys = JSON.parse('["isrc", "producer"]');

      applySavedProject(savedProject({ importedMetadataKeys: keys }));

      expect(useProjectStore.getState().importedMetadataKeys).toEqual(["isrc"]);
    });
  });
});
