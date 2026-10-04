import { describe, expect, it } from "vitest";
import { usePersistence } from "@/hooks/usePersistence";

describe("hook exports", () => {
  const hooks: Array<[string, unknown]> = [["usePersistence", usePersistence]];

  for (const [name, hook] of hooks) {
    it(`${name} is a function`, () => {
      expect(typeof hook).toBe("function");
    });
  }
});
