// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/Animator/Lyrics/LyricsAnimator.ts (fcc5f83), the cached and batched
// style writes (setStyleIfChanged / flushStyleBatch / setClass).

// -- State --------------------------------------------------------------------

// Last written value per property: a number when comparable, else the raw string.
const styleCache = new WeakMap<HTMLElement, Map<string, number | string>>();
const styleQueue = new Map<HTMLElement, Map<string, string>>();

// -- Writers ------------------------------------------------------------------

/**
 * Queues a style write unless the value moved less than `epsilon` since the last one.
 * `compareValue` is the number behind values parseFloat cannot read, like translate3d();
 * without it a spring's endless sub-pixel decay would rewrite the style every frame.
 */
function setStyleIfChanged(el: HTMLElement, prop: string, value: string, epsilon = 0, compareValue?: number): void {
  let cached = styleCache.get(el);
  if (!cached) {
    cached = new Map();
    styleCache.set(el, cached);
  }
  let next: number | string = compareValue ?? Number.parseFloat(value);
  if (Number.isNaN(next)) next = value;
  const previous = cached.get(prop);
  if (previous !== undefined) {
    if (typeof previous === "number" && typeof next === "number") {
      if (Math.abs(previous - next) <= epsilon) return;
    } else if (previous === next) {
      return;
    }
  }
  let queued = styleQueue.get(el);
  if (!queued) {
    queued = new Map();
    styleQueue.set(el, queued);
  }
  queued.set(prop, value);
  cached.set(prop, next);
}

function flushStyleBatch(): void {
  for (const [el, props] of styleQueue) {
    for (const [prop, value] of props) el.style.setProperty(prop, value);
  }
  styleQueue.clear();
}

/** classList.toggle queues a mutation record even when nothing changes, so check first. */
function setClass(el: HTMLElement, className: string, on: boolean): void {
  if (el.classList.contains(className) !== on) el.classList.toggle(className, on);
}

// -- Exports ------------------------------------------------------------------

export { flushStyleBatch, setClass, setStyleIfChanged };
