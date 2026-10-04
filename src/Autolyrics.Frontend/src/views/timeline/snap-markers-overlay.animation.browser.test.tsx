import { useRef } from "react";
import { describe, expect, it } from "vitest";
import { useProjectStore } from "@/stores/project";
import { useSettingsStore } from "@/stores/settings";
import { render } from "@/test/render";
import { snapPoints } from "@/test/factories";
import { SnapMarkersOverlay } from "@/views/timeline/snap-markers-overlay";
import { GUTTER_WIDTH, useTimelineStore } from "@/views/timeline/timeline-store";

// -- Harness -------------------------------------------------------------------

const Harness: React.FC = () => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  return (
    <div ref={scrollContainerRef} style={{ width: 600, height: 200, position: "relative" }}>
      <SnapMarkersOverlay scrollContainerRef={scrollContainerRef} />
    </div>
  );
};

const customMarkers = (container: HTMLElement): NodeListOf<HTMLElement> =>
  container.querySelectorAll<HTMLElement>("[data-snap-marker='custom']");

const pinAtTime = (container: HTMLElement, time: number): HTMLElement | null =>
  container.querySelector<HTMLElement>(`[data-snap-marker='custom'][data-snap-marker-time='${time}']`);

const headOf = (marker: HTMLElement): HTMLElement => {
  const head = marker.querySelector<HTMLElement>("[data-snap-marker-head]");
  if (!head) throw new Error("pin head not found");
  return head;
};

// -- Tests ---------------------------------------------------------------------

describe("SnapMarkersOverlay placement animation", () => {
  it("keeps a single pin mounted across a drag (stable id reuses the DOM node)", async () => {
    useSettingsStore.setState({ timelineSnapThreshold: 12 });
    useTimelineStore.setState({
      zoom: 100,
      scrollLeft: 0,
    });
    useProjectStore.setState({ customSnapPoints: snapPoints([2]) });

    const screen = await render(<Harness />);
    const pinBefore = customMarkers(screen.container)[0];

    const head = headOf(pinBefore);
    const rect = screen.container.firstElementChild?.getBoundingClientRect();
    if (!rect) throw new Error("scroll container rect missing");

    head.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerId: 1 }));
    for (const targetTime of [3, 4, 5, 6]) {
      const clientX = rect.left + GUTTER_WIDTH + targetTime * 100;
      head.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX, pointerId: 1 }));
    }

    await expect.poll(() => useProjectStore.getState().customSnapPoints[0].time).toBeCloseTo(6, 5);
    // The pin's id is stable across every move, so AnimatePresence keeps the same
    // DOM node mounted: count stays 1 and the node identity is preserved.
    expect(customMarkers(screen.container)).toHaveLength(1);
    expect(customMarkers(screen.container)[0]).toBe(pinBefore);

    head.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, pointerId: 1 }));
  });
});

describe("SnapMarkersOverlay AnimatePresence enter/exit", () => {
  it("renders a new pin element when a point is appended after first render", async () => {
    useSettingsStore.setState({ timelineSnapThreshold: 12 });
    useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
    useProjectStore.setState({ customSnapPoints: snapPoints([1, 3]) });

    const screen = await render(<Harness />);
    await expect.poll(() => customMarkers(screen.container)).toHaveLength(2);

    useProjectStore.getState().addCustomSnapPoint(5);

    await expect.poll(() => customMarkers(screen.container)).toHaveLength(3);
    await expect.poll(() => pinAtTime(screen.container, 5)).not.toBeNull();
    expect(pinAtTime(screen.container, 5)?.style.left).toBe("500px");
  });

  it("renders a new pin element when a point is inserted in the middle after first render", async () => {
    useSettingsStore.setState({ timelineSnapThreshold: 12 });
    useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
    useProjectStore.setState({ customSnapPoints: snapPoints([1, 3]) });

    const screen = await render(<Harness />);
    await expect.poll(() => customMarkers(screen.container)).toHaveLength(2);

    useProjectStore.getState().addCustomSnapPoint(2);

    await expect.poll(() => customMarkers(screen.container)).toHaveLength(3);
    await expect.poll(() => pinAtTime(screen.container, 2)).not.toBeNull();
    expect(pinAtTime(screen.container, 2)?.style.left).toBe("200px");
  });

  it("removes a pin from the DOM after delete while the overlay stays mounted", async () => {
    useSettingsStore.setState({ timelineSnapThreshold: 12 });
    useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
    useProjectStore.setState({ customSnapPoints: snapPoints([1, 2, 3]) });

    const screen = await render(<Harness />);
    await expect.poll(() => customMarkers(screen.container)).toHaveLength(3);

    const targetId = useProjectStore.getState().customSnapPoints[1].id; // the 2 pin
    useProjectStore.getState().removeCustomSnapPoint(targetId);

    // The deleted pin eventually leaves the DOM; the overlay stays mounted because
    // two pins remain, so AnimatePresence keeps animating the survivors.
    await expect.poll(() => pinAtTime(screen.container, 2)).toBeNull();
    await expect.poll(() => customMarkers(screen.container)).toHaveLength(2);
    expect(screen.container.querySelector("[data-snap-markers-overlay]")).not.toBeNull();
  });

  it("does not change the pin count on a move (same ids, one time changed)", async () => {
    useSettingsStore.setState({ timelineSnapThreshold: 12 });
    useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
    useProjectStore.setState({ customSnapPoints: snapPoints([2, 4]) });

    const screen = await render(<Harness />);
    await expect.poll(() => customMarkers(screen.container)).toHaveLength(2);
    const movedId = useProjectStore.getState().customSnapPoints[0].id;

    useProjectStore.getState().moveCustomSnapPoint(movedId, 6);

    await expect.poll(() => useProjectStore.getState().customSnapPoints.map((p) => p.time)).toEqual([4, 6]);
    expect(customMarkers(screen.container)).toHaveLength(2);
  });
});
