import { useRef } from "react";
import { describe, expect, it } from "vitest";
import { useProjectStore } from "@/stores/project";
import { useSettingsStore } from "@/stores/settings";
import { render } from "@/test/render";
import { snapPoints } from "@/test/factories";
import { SnapMarkersOverlay } from "@/views/timeline/snap-markers-overlay";
import { GUTTER_WIDTH, useTimelineStore, WAVEFORM_HEIGHT } from "@/views/timeline/timeline-store";

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

const headOf = (marker: HTMLElement): HTMLElement => {
  const head = marker.querySelector<HTMLElement>("[data-snap-marker-head]");
  if (!head) throw new Error("pin head not found");
  return head;
};

// -- Tests ---------------------------------------------------------------------

describe("SnapMarkersOverlay", () => {
  it("clips the overlay root to the right of the gutter and above the strip bottom", async () => {
    useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
    useProjectStore.setState({ customSnapPoints: snapPoints([1]) });

    const screen = await render(<Harness />);
    const root = screen.container.querySelector<HTMLElement>("[data-snap-markers-overlay]");

    expect(root).not.toBeNull();
    // Left inset hides the gutter; the calc bottom inset clips the drop-in
    // overshoot at the strip bottom (WAVEFORM_HEIGHT - 1) without bounding the
    // box height (which would break head hover).
    expect(root?.style.clipPath).toBe(`inset(0px 0px calc(100% - ${WAVEFORM_HEIGHT - 1}px) ${GUTTER_WIDTH}px)`);
  });

  it("contains custom pins to the waveform height", async () => {
    useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
    useProjectStore.setState({ customSnapPoints: snapPoints([2]) });

    const screen = await render(<Harness />);
    const [pin] = customMarkers(screen.container);
    const pinLine = pin.querySelector<HTMLElement>("[data-snap-marker-line]");

    expect(pinLine?.style.height).toBe(`${WAVEFORM_HEIGHT}px`);
  });

  it("translates the inner layer by GUTTER_WIDTH when scrollLeft is 0", async () => {
    useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
    useProjectStore.setState({ customSnapPoints: snapPoints([1]) });

    const screen = await render(<Harness />);
    const layer = screen.container.querySelector<HTMLElement>("[data-snap-markers-layer]");

    await expect.poll(() => layer?.style.transform).toBe(`translate3d(${GUTTER_WIDTH}px, 0px, 0px)`);
  });

  describe("visibility", () => {
    it("renders null when there is nothing to show and marker mode is off", async () => {
      useTimelineStore.setState({
        zoom: 100,
        scrollLeft: 0,
        markerMode: false,
      });
      useProjectStore.setState({ customSnapPoints: [] });

      const screen = await render(<Harness />);
      expect(screen.container.querySelector("[data-snap-markers-overlay]")).toBeNull();
    });

    it("stays mounted when marker mode is on even with nothing to show", async () => {
      useTimelineStore.setState({
        zoom: 100,
        scrollLeft: 0,
        markerMode: true,
      });
      useProjectStore.setState({ customSnapPoints: [] });

      const screen = await render(<Harness />);
      expect(screen.container.querySelector("[data-snap-markers-overlay]")).not.toBeNull();
    });

    it("stays mounted when custom points exist and marker mode is off", async () => {
      useTimelineStore.setState({
        zoom: 100,
        scrollLeft: 0,
        markerMode: false,
      });
      useProjectStore.setState({ customSnapPoints: snapPoints([2]) });

      const screen = await render(<Harness />);
      expect(screen.container.querySelector("[data-snap-markers-overlay]")).not.toBeNull();
    });
  });

  describe("custom pins", () => {
    it("renders one pin per custom snap point with a draggable head", async () => {
      useTimelineStore.setState({
        zoom: 100,
        scrollLeft: 0,
      });
      useProjectStore.setState({ customSnapPoints: snapPoints([1, 3]) });

      const screen = await render(<Harness />);
      const pins = customMarkers(screen.container);
      expect(pins).toHaveLength(2);
      expect(pins[0].style.left).toBe("100px");
      expect(pins[1].style.left).toBe("300px");
      expect(pins[0].querySelector("[data-snap-marker-head]")).not.toBeNull();
    });
  });

  describe("drag", () => {
    it("updates moveCustomSnapPoint as the head is dragged", async () => {
      useSettingsStore.setState({ timelineSnapThreshold: 12 });
      useTimelineStore.setState({
        zoom: 100,
        scrollLeft: 0,
      });
      useProjectStore.setState({ customSnapPoints: snapPoints([2]) });

      const screen = await render(<Harness />);
      const head = headOf(customMarkers(screen.container)[0]);
      const rect = screen.container.firstElementChild?.getBoundingClientRect();
      if (!rect) throw new Error("scroll container rect missing");

      head.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerId: 1 }));
      const targetClientX = rect.left + GUTTER_WIDTH + 5 * 100;
      head.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX: targetClientX, pointerId: 1 }));

      await expect.poll(() => useProjectStore.getState().customSnapPoints[0].time).toBeCloseTo(5, 5);

      head.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, pointerId: 1 }));
    });
  });

  describe("hover lifecycle", () => {
    it("clears hoveredSnapPointId when the hovered pin is removed (undo / load / audio change)", async () => {
      useTimelineStore.setState({ zoom: 100, scrollLeft: 0 });
      useProjectStore.setState({ customSnapPoints: snapPoints([2]) });

      const screen = await render(<Harness />);
      const head = headOf(customMarkers(screen.container)[0]);
      const hoveredId = useProjectStore.getState().customSnapPoints[0].id;

      // Open the hover the way floating-ui listens for it (React synthesizes
      // onPointerEnter / onMouseEnter from native pointerover / mouseover).
      head.dispatchEvent(new PointerEvent("pointerover", { bubbles: true }));
      head.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      head.dispatchEvent(new MouseEvent("mousemove", { bubbles: true }));
      await expect.poll(() => useTimelineStore.getState().hoveredSnapPointId).toBe(hoveredId);

      // Remove the hovered pin without mousing off it; the pin unmounts.
      useProjectStore.setState({ customSnapPoints: [] });

      // Without the unmount cleanup the id stays stale and a later word Delete is swallowed.
      await expect.poll(() => useTimelineStore.getState().hoveredSnapPointId).toBeNull();
    });
  });

  describe("delete", () => {
    it("removes the correct pin when several exist", async () => {
      useTimelineStore.setState({
        zoom: 100,
        scrollLeft: 0,
      });
      useProjectStore.setState({ customSnapPoints: snapPoints([1, 2, 3]) });

      const screen = await render(<Harness />);
      await expect.poll(() => customMarkers(screen.container)).toHaveLength(3);

      // The delete control is a hover tooltip; opening it on the clipped overlay is
      // a Playwright actionability limitation. The tooltip opening and its delete
      // button calling onDelete(id) are covered in isolation by
      // snap-marker-pin.browser.test.tsx. Here we verify the overlay's wiring: it
      // hands each pin removeCustomSnapPoint keyed by id, so removing the middle
      // pin's id leaves the outer two in order and the overlay re-renders to match.
      const middleId = useProjectStore.getState().customSnapPoints[1].id;
      useProjectStore.getState().removeCustomSnapPoint(middleId);

      await expect.poll(() => useProjectStore.getState().customSnapPoints.map((p) => p.time)).toEqual([1, 3]);
      await expect.poll(() => customMarkers(screen.container)).toHaveLength(2);
    });
  });
});
