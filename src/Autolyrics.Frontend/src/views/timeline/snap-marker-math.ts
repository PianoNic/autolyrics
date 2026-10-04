// -- Functions -----------------------------------------------------------------

function snapTimeToNearest(time: number, anchors: number[], zoom: number, thresholdPx: number): number {
  let best = time;
  let bestDistPx = thresholdPx;
  for (const anchor of anchors) {
    const distPx = Math.abs(anchor - time) * zoom;
    if (distPx <= bestDistPx) {
      bestDistPx = distPx;
      best = anchor;
    }
  }
  return best;
}

const ADJACENT_EPSILON = 1e-4;

function adjacentSnapPoint(points: number[], current: number, direction: 1 | -1): number | null {
  if (direction > 0) {
    for (const point of points) if (point > current + ADJACENT_EPSILON) return point;
    return null;
  }
  for (let index = points.length - 1; index >= 0; index--) {
    if (points[index] < current - ADJACENT_EPSILON) return points[index];
  }
  return null;
}

// -- Exports -------------------------------------------------------------------

export { snapTimeToNearest, adjacentSnapPoint };
