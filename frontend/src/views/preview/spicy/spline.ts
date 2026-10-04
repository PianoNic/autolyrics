// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Animator/Lyrics/LyricsAnimator.ts (fcc5f83), GetSpline / easeSinOut.
// Upstream interpolates with the `cubic-spline` and `d3-ease` packages; this is a
// dependency-free natural cubic spline and the same sine ease-out.

// -- Types --------------------------------------------------------------------

interface AnimationPoint {
  /** Where along the animation (0 to 1) the value applies. */
  progress: number;
  value: number;
}

interface Spline {
  at: (progress: number) => number;
}

// -- Spline -------------------------------------------------------------------

/** Second derivatives of the natural cubic spline through the points (zero at both ends). */
function secondDerivatives(xs: number[], ys: number[]): number[] {
  const n = xs.length;
  const m = new Array<number>(n).fill(0);
  if (n < 3) return m;

  const c = new Array<number>(n).fill(0);
  const d = new Array<number>(n).fill(0);
  for (let i = 1; i < n - 1; i++) {
    const h0 = xs[i] - xs[i - 1];
    const h1 = xs[i + 1] - xs[i];
    const rhs = 6 * ((ys[i + 1] - ys[i]) / h1 - (ys[i] - ys[i - 1]) / h0);
    const diagonal = 2 * (h0 + h1) - h0 * c[i - 1];
    c[i] = h1 / diagonal;
    d[i] = (rhs - h0 * d[i - 1]) / diagonal;
  }
  for (let i = n - 2; i >= 1; i--) m[i] = d[i] - c[i] * m[i + 1];
  return m;
}

function createSpline(points: AnimationPoint[]): Spline {
  const xs = points.map((point) => point.progress);
  const ys = points.map((point) => point.value);
  const m = secondDerivatives(xs, ys);
  const last = xs.length - 1;

  return {
    at: (progress) => {
      const x = Math.min(Math.max(progress, xs[0]), xs[last]);
      let i = 0;
      while (i < last - 1 && x > xs[i + 1]) i++;
      const h = xs[i + 1] - xs[i];
      const a = (xs[i + 1] - x) / h;
      const b = (x - xs[i]) / h;
      return a * ys[i] + b * ys[i + 1] + (((a * a * a - a) * m[i] + (b * b * b - b) * m[i + 1]) * h * h) / 6;
    },
  };
}

function easeSinOut(t: number): number {
  return Math.sin((t * Math.PI) / 2);
}

// -- Exports ------------------------------------------------------------------

export { createSpline, easeSinOut };
