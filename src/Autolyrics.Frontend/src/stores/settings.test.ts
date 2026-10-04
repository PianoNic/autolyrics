import { DEFAULTS, useSettingsStore } from "@/stores/settings";
import { useTimelineStore } from "@/views/timeline/timeline-store";
import { beforeEach, describe, expect, it } from "vitest";

describe("audio scrub preview settings", () => {
  beforeEach(() => {
    useSettingsStore.setState({ ...DEFAULTS });
  });

  it("defaults audioScrubPreview to true", () => {
    expect(useSettingsStore.getState().audioScrubPreview).toBe(true);
  });
});

describe("audio pitch settings", () => {
  beforeEach(() => {
    useSettingsStore.setState({ ...DEFAULTS });
  });

  it("preserves pitch by default and restores that default on reset", () => {
    expect(useSettingsStore.getState().preservePitch).toBe(true);
    useSettingsStore.getState().set("preservePitch", false);
    useSettingsStore.getState().resetToDefaults();
    expect(useSettingsStore.getState().preservePitch).toBe(true);
  });
});

describe("background vocal extraction settings", () => {
  beforeEach(() => {
    useSettingsStore.setState({ ...DEFAULTS });
  });

  it("defaults autoExtractBackgroundVocals to true", () => {
    expect(DEFAULTS.autoExtractBackgroundVocals).toBe(true);
    expect(useSettingsStore.getState().autoExtractBackgroundVocals).toBe(true);
  });

  it("defaults mergeStandaloneBackgroundLines to true", () => {
    expect(DEFAULTS.mergeStandaloneBackgroundLines).toBe(true);
    expect(useSettingsStore.getState().mergeStandaloneBackgroundLines).toBe(true);
  });

  it("defaults preserveBracketsOnExtraction to true", () => {
    expect(DEFAULTS.preserveBracketsOnExtraction).toBe(true);
    expect(useSettingsStore.getState().preserveBracketsOnExtraction).toBe(true);
  });

  it("allows toggling preserveBracketsOnExtraction via set()", () => {
    useSettingsStore.getState().set("preserveBracketsOnExtraction", true);
    expect(useSettingsStore.getState().preserveBracketsOnExtraction).toBe(true);
    useSettingsStore.getState().set("preserveBracketsOnExtraction", false);
    expect(useSettingsStore.getState().preserveBracketsOnExtraction).toBe(false);
  });

  it("allows toggling autoExtractBackgroundVocals via set()", () => {
    useSettingsStore.getState().set("autoExtractBackgroundVocals", false);
    expect(useSettingsStore.getState().autoExtractBackgroundVocals).toBe(false);
    useSettingsStore.getState().set("autoExtractBackgroundVocals", true);
    expect(useSettingsStore.getState().autoExtractBackgroundVocals).toBe(true);
  });

  it("allows disabling mergeStandaloneBackgroundLines via set()", () => {
    useSettingsStore.getState().set("mergeStandaloneBackgroundLines", false);
    expect(useSettingsStore.getState().mergeStandaloneBackgroundLines).toBe(false);
  });

  it("resetToDefaults restores the background vocal toggles", () => {
    useSettingsStore.getState().set("autoExtractBackgroundVocals", false);
    useSettingsStore.getState().set("mergeStandaloneBackgroundLines", false);
    useSettingsStore.getState().resetToDefaults();
    expect(useSettingsStore.getState().autoExtractBackgroundVocals).toBe(true);
    expect(useSettingsStore.getState().mergeStandaloneBackgroundLines).toBe(true);
  });
});

describe("snap playhead to points settings", () => {
  beforeEach(() => {
    useSettingsStore.setState({ ...DEFAULTS });
  });

  it("defaults snapPlayheadToPoints to true", () => {
    expect(DEFAULTS.snapPlayheadToPoints).toBe(true);
    expect(useSettingsStore.getState().snapPlayheadToPoints).toBe(true);
  });

  it("allows toggling snapPlayheadToPoints via set()", () => {
    useSettingsStore.getState().set("snapPlayheadToPoints", false);
    expect(useSettingsStore.getState().snapPlayheadToPoints).toBe(false);
    useSettingsStore.getState().set("snapPlayheadToPoints", true);
    expect(useSettingsStore.getState().snapPlayheadToPoints).toBe(true);
  });

  it("resetToDefaults restores snapPlayheadToPoints to true", () => {
    useSettingsStore.getState().set("snapPlayheadToPoints", false);
    useSettingsStore.getState().resetToDefaults();
    expect(useSettingsStore.getState().snapPlayheadToPoints).toBe(true);
  });
});

describe("timeline header toggle defaults", () => {
  beforeEach(() => {
    useSettingsStore.setState({ ...DEFAULTS });
  });

  it("defaults defaultRollingEdit to false", () => {
    expect(DEFAULTS.defaultRollingEdit).toBe(false);
    expect(useSettingsStore.getState().defaultRollingEdit).toBe(false);
  });

  it("defaults defaultPreviewSidebar to false", () => {
    expect(DEFAULTS.defaultPreviewSidebar).toBe(false);
    expect(useSettingsStore.getState().defaultPreviewSidebar).toBe(false);
  });

  it("set() persists defaultRollingEdit", () => {
    useSettingsStore.getState().set("defaultRollingEdit", true);
    expect(useSettingsStore.getState().defaultRollingEdit).toBe(true);
  });

  it("set() persists defaultPreviewSidebar", () => {
    useSettingsStore.getState().set("defaultPreviewSidebar", true);
    expect(useSettingsStore.getState().defaultPreviewSidebar).toBe(true);
  });

  it("resetToDefaults restores both to false", () => {
    useSettingsStore.getState().set("defaultRollingEdit", true);
    useSettingsStore.getState().set("defaultPreviewSidebar", true);
    useSettingsStore.getState().resetToDefaults();
    expect(useSettingsStore.getState().defaultRollingEdit).toBe(false);
    expect(useSettingsStore.getState().defaultPreviewSidebar).toBe(false);
  });
});

describe("settings v2 -> v3 migration", () => {
  it("fills missing defaultRollingEdit with false", async () => {
    const { migrateSettingsForTest } = await import("@/stores/settings");
    const migrated = migrateSettingsForTest({ defaultZoom: 200 }, 2) as { defaultRollingEdit: boolean };
    expect(migrated.defaultRollingEdit).toBe(false);
  });

  it("fills missing defaultPreviewSidebar with false", async () => {
    const { migrateSettingsForTest } = await import("@/stores/settings");
    const migrated = migrateSettingsForTest({ defaultZoom: 200 }, 2) as { defaultPreviewSidebar: boolean };
    expect(migrated.defaultPreviewSidebar).toBe(false);
  });

  it("preserves user-set values when migrating from v3", async () => {
    const { migrateSettingsForTest } = await import("@/stores/settings");
    const migrated = migrateSettingsForTest({ defaultRollingEdit: true, defaultPreviewSidebar: true }, 3) as {
      defaultRollingEdit: boolean;
      defaultPreviewSidebar: boolean;
    };
    expect(migrated.defaultRollingEdit).toBe(true);
    expect(migrated.defaultPreviewSidebar).toBe(true);
  });
});

describe("settings v4 -> v5 migration (snapPlayheadToPoints)", () => {
  it("fills missing snapPlayheadToPoints with true", async () => {
    const { migrateSettingsForTest } = await import("@/stores/settings");
    const migrated = migrateSettingsForTest({ defaultZoom: 200 }, 4) as { snapPlayheadToPoints: boolean };
    expect(migrated.snapPlayheadToPoints).toBe(true);
  });

  it("preserves an explicitly disabled snapPlayheadToPoints", async () => {
    const { migrateSettingsForTest } = await import("@/stores/settings");
    const migrated = migrateSettingsForTest({ snapPlayheadToPoints: false }, 4) as { snapPlayheadToPoints: boolean };
    expect(migrated.snapPlayheadToPoints).toBe(false);
  });
});

describe("timeline store reads header-toggle defaults at init", () => {
  it("initial previewSidebarOpen matches settings.defaultPreviewSidebar at the moment the store was created", () => {
    expect(useTimelineStore.getState().previewSidebarOpen).toBe(useSettingsStore.getState().defaultPreviewSidebar);
  });

  it("initial rollingEditMode matches settings.defaultRollingEdit at the moment the store was created", () => {
    expect(useTimelineStore.getState().rollingEditMode).toBe(useSettingsStore.getState().defaultRollingEdit);
  });
});
