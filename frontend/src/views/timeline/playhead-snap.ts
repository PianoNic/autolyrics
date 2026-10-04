import { snapPointTimes } from "@/domain/snap-point/model";
import { useProjectStore } from "@/stores/project";
import { useSettingsStore } from "@/stores/settings";
import { snapTimeToNearest } from "@/views/timeline/snap-marker-math";
import { useTimelineStore } from "@/views/timeline/timeline-store";

function snapPlayheadTime(time: number, bypass: boolean): number {
  if (bypass) return time;
  const { snapPlayheadToPoints, timelineSnapThreshold } = useSettingsStore.getState();
  if (!snapPlayheadToPoints) return time;
  const pins = snapPointTimes(useProjectStore.getState().customSnapPoints);
  if (pins.length === 0) return time;
  return snapTimeToNearest(time, pins, useTimelineStore.getState().zoom, timelineSnapThreshold);
}

export { snapPlayheadTime };
