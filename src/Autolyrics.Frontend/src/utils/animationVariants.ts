import { hexToRgba } from "@/utils/colors";
import type { Variants } from "motion/react";

// -- Group Ping ---------------------------------------------------------------

function buildGroupPingVariants(color: string): Variants {
  const transparent = hexToRgba(color, 0);
  const visible = hexToRgba(color, 0.55);
  return {
    idle: {
      boxShadow: `0 0 0 0 ${transparent}`,
      transition: { duration: 0 },
    },
    ping: {
      boxShadow: [`0 0 0 0 ${visible}`, `0 0 0 8px ${transparent}`],
      transition: { type: "spring", stiffness: 120, damping: 20, mass: 0.6 },
    },
  };
}

// -- Snap Markers -------------------------------------------------------------

const pinDropInVariants: Variants = {
  initial: { opacity: 0, y: -8, scale: 0.6 },
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring", stiffness: 600, damping: 20, mass: 0.8 },
  },
  exit: {
    opacity: 0,
    y: -8,
    scale: 0.6,
    transition: { type: "spring", stiffness: 500, damping: 28, mass: 0.7 },
  },
};

// -- Exports ------------------------------------------------------------------

export { buildGroupPingVariants, pinDropInVariants };
