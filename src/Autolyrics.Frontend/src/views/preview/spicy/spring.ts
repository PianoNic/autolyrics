// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/modules/Spring.ts (fcc5f83), itself a port of https://github.com/Fraktality/spr
// (Copyright (c) Fraktality, MIT License).

// -- Constants ----------------------------------------------------------------

const SLEEP_OFFSET_SQ_LIMIT = (1 / 3840) ** 2;
const SLEEP_VELOCITY_SQ_LIMIT = 1e-2 ** 2;
const EPS = 1e-5;

// -- Spring -------------------------------------------------------------------

/** An analytic damped spring: stepping by any dt lands exactly where the physics would. */
class Spring {
  private readonly damping: number;
  private readonly frequency: number;
  private goal: number;
  private position: number;
  private velocity = 0;

  constructor(startPosition: number, frequency: number, dampingRatio: number) {
    this.damping = dampingRatio;
    this.frequency = frequency;
    this.goal = startPosition;
    this.position = startPosition;
  }

  step(dt: number): number {
    const d = this.damping;
    const f = this.frequency * 2 * Math.PI;
    const g = this.goal;
    const offset = this.position - g;
    const v = this.velocity;

    if (d === 1) {
      const q = Math.exp(-f * dt);
      const w = dt * q;
      this.position = offset * (q + w * f) + v * w + g;
      this.velocity = v * (q - w * f) - offset * (w * f * f);
    } else if (d < 1) {
      this.stepUnderdamped(dt, d, f, offset, v);
    } else {
      const c = Math.sqrt(d * d - 1);
      const r1 = -f * (d + c);
      const r2 = -f * (d - c);
      const co2 = (v - offset * r1) / (2 * f * c);
      const co1 = Math.exp(r1 * dt) * (offset - co2);
      const ec2 = Math.exp(r2 * dt);
      this.position = co1 + co2 * ec2 + g;
      this.velocity = co1 * r1 + co2 * ec2 * r2;
    }

    return this.position;
  }

  private stepUnderdamped(dt: number, d: number, f: number, offset: number, v: number): void {
    const q = Math.exp(-d * f * dt);
    const c = Math.sqrt(1 - d * d);
    const i = Math.cos(dt * f * c);
    const j = Math.sin(dt * f * c);

    let z: number;
    if (c > EPS) {
      z = j / c;
    } else {
      const a = dt * f;
      z = a + (((a * a * (c * c) * (c * c)) / 20 - c * c) * (a * a * a)) / 6;
    }

    let y: number;
    if (f * c > EPS) {
      y = j / (f * c);
    } else {
      const b = f * c;
      y = dt + (((dt * dt * (b * b) * (b * b)) / 20 - b * b) * (dt * dt * dt)) / 6;
    }

    this.position = (offset * (i + z * d) + v * y) * q + this.goal;
    this.velocity = (v * (i - z * d) - offset * (z * f)) * q;
  }

  canSleep(): boolean {
    if (this.velocity * this.velocity > SLEEP_VELOCITY_SQ_LIMIT) return false;
    const offset = this.position - this.goal;
    return offset * offset <= SLEEP_OFFSET_SQ_LIMIT;
  }

  setGoal(goal: number, replacePosition = false): void {
    this.goal = goal;
    if (!replacePosition) return;
    this.position = goal;
    this.velocity = 0;
  }
}

// -- Exports ------------------------------------------------------------------

export { Spring };
