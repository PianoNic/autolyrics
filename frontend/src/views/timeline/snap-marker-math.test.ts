import { describe, expect, it } from "vitest";
import { adjacentSnapPoint, snapTimeToNearest } from "@/views/timeline/snap-marker-math";

// -- Tests ---------------------------------------------------------------------

describe("snapTimeToNearest", () => {
  it("snaps to an anchor within the pixel threshold", () => {
    expect(snapTimeToNearest(2.05, [2], 100, 12)).toBe(2);
  });

  it("leaves the time untouched when no anchor is within threshold", () => {
    expect(snapTimeToNearest(2.5, [2], 100, 12)).toBe(2.5);
  });

  it("snaps just inside the threshold", () => {
    expect(snapTimeToNearest(2.11, [2], 100, 12)).toBe(2);
  });

  it("does not snap just beyond the threshold", () => {
    expect(snapTimeToNearest(2.13, [2], 100, 12)).toBe(2.13);
  });

  it("snaps to the nearest of several anchors", () => {
    expect(snapTimeToNearest(2.04, [2, 2.1], 100, 20)).toBe(2);
    expect(snapTimeToNearest(2.07, [2, 2.1], 100, 20)).toBe(2.1);
  });

  it("scales the threshold by zoom (lower zoom = wider time window)", () => {
    expect(snapTimeToNearest(2.2, [2], 50, 12)).toBe(2);
    expect(snapTimeToNearest(2.2, [2], 100, 12)).toBe(2.2);
  });

  describe("edge cases", () => {
    it("returns the input when there are no anchors", () => {
      expect(snapTimeToNearest(2, [], 100, 12)).toBe(2);
    });

    it("handles the timeline origin", () => {
      expect(snapTimeToNearest(0.05, [0], 100, 12)).toBe(0);
    });
  });
});

describe("adjacentSnapPoint", () => {
  it("returns the smallest point strictly greater than current when going next", () => {
    expect(adjacentSnapPoint([1, 5, 12], 5, 1)).toBe(12);
  });

  it("returns the largest point strictly less than current when going prev", () => {
    expect(adjacentSnapPoint([1, 5, 12], 5, -1)).toBe(1);
  });

  it("finds the next point from a time between two points", () => {
    expect(adjacentSnapPoint([1, 5, 12], 4, 1)).toBe(5);
  });

  it("finds the prev point from a time between two points", () => {
    expect(adjacentSnapPoint([1, 5, 12], 6, -1)).toBe(5);
  });

  describe("edge cases", () => {
    it("returns null when there is no point ahead", () => {
      expect(adjacentSnapPoint([1, 5, 12], 12, 1)).toBeNull();
    });

    it("returns null when there is no point behind", () => {
      expect(adjacentSnapPoint([1, 5, 12], 1, -1)).toBeNull();
    });

    it("returns null for an empty array going next", () => {
      expect(adjacentSnapPoint([], 5, 1)).toBeNull();
    });

    it("returns null for an empty array going prev", () => {
      expect(adjacentSnapPoint([], 5, -1)).toBeNull();
    });

    it("skips a point exactly on current and returns the next distinct point", () => {
      expect(adjacentSnapPoint([1, 5, 12], 5, 1)).toBe(12);
    });

    it("skips a point exactly on current going prev and returns the previous distinct point", () => {
      expect(adjacentSnapPoint([1, 5, 12], 5, -1)).toBe(1);
    });

    it("skips a point within epsilon of current going next", () => {
      expect(adjacentSnapPoint([5, 12], 5.00005, 1)).toBe(12);
    });

    it("skips a point within epsilon of current going prev", () => {
      expect(adjacentSnapPoint([1, 5], 4.99995, -1)).toBe(1);
    });

    it("returns the first point for a current before all points going next", () => {
      expect(adjacentSnapPoint([1, 5, 12], 0, 1)).toBe(1);
    });

    it("returns the last point for a current after all points going prev", () => {
      expect(adjacentSnapPoint([1, 5, 12], 20, -1)).toBe(12);
    });

    it("returns null for a current after all points going next", () => {
      expect(adjacentSnapPoint([1, 5, 12], 20, 1)).toBeNull();
    });

    it("returns null for a current before all points going prev", () => {
      expect(adjacentSnapPoint([1, 5, 12], 0, -1)).toBeNull();
    });

    it("handles a single-element array going next", () => {
      expect(adjacentSnapPoint([5], 4, 1)).toBe(5);
      expect(adjacentSnapPoint([5], 6, 1)).toBeNull();
    });

    it("handles a single-element array going prev", () => {
      expect(adjacentSnapPoint([5], 6, -1)).toBe(5);
      expect(adjacentSnapPoint([5], 4, -1)).toBeNull();
    });

    it("returns the first point for a negative current going next", () => {
      expect(adjacentSnapPoint([0, 3, 8], -2, 1)).toBe(0);
    });

    it("handles the timeline origin as a target", () => {
      expect(adjacentSnapPoint([0, 3], -0.5, 1)).toBe(0);
    });
  });
});
