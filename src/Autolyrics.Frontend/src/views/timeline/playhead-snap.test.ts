import { useProjectStore } from "@/stores/project";
import { useSettingsStore } from "@/stores/settings";
import { snapPoints } from "@/test/factories";
import { snapPlayheadTime } from "@/views/timeline/playhead-snap";
import { useTimelineStore } from "@/views/timeline/timeline-store";
import { beforeEach, describe, expect, it } from "vitest";

describe("snapPlayheadTime", () => {
  beforeEach(() => {
    useSettingsStore.setState({ snapPlayheadToPoints: true, timelineSnapThreshold: 12 });
    useTimelineStore.setState({ zoom: 100 });
    useProjectStore.setState({ customSnapPoints: snapPoints([5]) });
  });

  it("snaps to a pin when the time is within the pixel threshold", () => {
    expect(snapPlayheadTime(5.05, false)).toBe(5);
  });

  it("leaves the time unchanged when it is beyond the pixel threshold", () => {
    expect(snapPlayheadTime(5.2, false)).toBe(5.2);
  });

  it("returns the time unchanged when snapPlayheadToPoints is off", () => {
    useSettingsStore.setState({ snapPlayheadToPoints: false });
    expect(snapPlayheadTime(5.05, false)).toBe(5.05);
  });

  it("returns the time unchanged when bypass is true", () => {
    expect(snapPlayheadTime(5.05, true)).toBe(5.05);
  });

  describe("edge cases", () => {
    it("returns the time unchanged when there are no anchors at all", () => {
      useProjectStore.setState({ customSnapPoints: [] });
      expect(snapPlayheadTime(3.14, false)).toBe(3.14);
    });

    it("snaps to the timeline origin", () => {
      useProjectStore.setState({ customSnapPoints: snapPoints([0]) });
      expect(snapPlayheadTime(0.05, false)).toBe(0);
    });
  });
});
