import { useAudioStore } from "@/stores/audio";
import { useProjectStore } from "@/stores/project";
import { useSettingsStore } from "@/stores/settings";
import { snapPoints } from "@/test/factories";
import { useTimelineStore } from "@/views/timeline/timeline-store";
import { useTimelineSnap } from "@/views/timeline/use-timeline-snap";
import { beforeEach, describe, expect, it } from "vitest";
import { renderHook } from "vitest-browser-react";

// -- Helpers ------------------------------------------------------------------

const ZOOM = 100;
const THRESHOLD = 12;
const SELF_IDS = new Set<string>();
const ALLOW_SHIFT = () => true;

function beginAt(result: { current: ReturnType<typeof useTimelineSnap> }): void {
  result.current.beginGesture({ selfIds: SELF_IDS, leaderKey: "leader", overlapCheck: ALLOW_SHIFT });
}

// -- Tests --------------------------------------------------------------------

describe("useTimelineSnap · custom snap points", () => {
  beforeEach(() => {
    useAudioStore.setState({ audioElement: null, currentTime: 0, duration: 30 });
    useProjectStore.setState({ lines: [], customSnapPoints: [] });
    useTimelineStore.setState({
      zoom: ZOOM,
      isBypassing: false,
      snappedBlockId: null,
      snappedAnchorTime: null,
    });
    useSettingsStore.setState({
      timelineSnap: false,
      timelineSnapThreshold: THRESHOLD,
    });
  });

  it("snaps a block to a custom point when timelineSnap is OFF", async () => {
    useProjectStore.setState({ customSnapPoints: snapPoints([1]) });
    const { result } = await renderHook(() => useTimelineSnap());

    beginAt(result);

    const edge = 0.95;
    const proposedDeltaPx = 0;
    const shiftPx = result.current.computeShiftPx(proposedDeltaPx, [edge]);

    expect(shiftPx).toBeCloseTo((1 - edge) * ZOOM, 4);
    expect(useTimelineStore.getState().snappedAnchorTime).toBeCloseTo(1, 4);
  });

  it("does not snap when there are no custom points and timelineSnap is OFF", async () => {
    useProjectStore.setState({ customSnapPoints: [] });
    const { result } = await renderHook(() => useTimelineSnap());

    beginAt(result);

    const shiftPx = result.current.computeShiftPx(0, [0.95]);

    expect(shiftPx).toBe(0);
    expect(useTimelineStore.getState().snappedAnchorTime).toBeNull();
  });

  it("does not emit timeline grid anchors when timelineSnap is OFF but a custom point exists", async () => {
    useProjectStore.setState({
      lines: [{ id: "g1", text: "grid", agentId: "v1", begin: 2, end: 3 }],
      customSnapPoints: snapPoints([1]),
    });
    const { result } = await renderHook(() => useTimelineSnap());

    beginAt(result);

    const nearGrid = result.current.computeShiftPx(0, [1.98]);
    expect(nearGrid).toBe(0);
    expect(useTimelineStore.getState().snappedAnchorTime).toBeNull();

    const nearCustom = result.current.computeShiftPx(0, [0.95]);
    expect(nearCustom).toBeCloseTo((1 - 0.95) * ZOOM, 4);
    expect(useTimelineStore.getState().snappedAnchorTime).toBeCloseTo(1, 4);
  });
});
