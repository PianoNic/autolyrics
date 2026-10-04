import { instanceBounds } from "@/domain/instance/bounds";
import { linesOfInstance } from "@/domain/instance/enumerate";
import { isLinked } from "@/domain/instance/predicates";
import { effectiveBounds } from "@/domain/line/bounds";
import type { LyricLine } from "@/domain/line/model";
import { useProjectStore } from "@/stores/project";
import { GROUP_HEADER_HEIGHT } from "@/views/timeline/group-header-row";
import { GUTTER_WIDTH, useTimelineStore, WAVEFORM_HEIGHT } from "@/views/timeline/timeline-store";
import { centerTimeScrollLeft } from "@/views/timeline/coords";
import { computeRowLayout } from "@/views/timeline/utils";

// -- Functions -----------------------------------------------------------------

function scrollToInstanceHeader(groupId: string, instanceIdx: number): void {
  const container = document.querySelector<HTMLDivElement>("[data-scroll-container]");
  if (!container) return;
  const { rowHeights, defaultRowHeight, collapsedInstances, zoom } = useTimelineStore.getState();
  const projectLines = useProjectStore.getState().lines;
  const layout = computeRowLayout({
    lines: projectLines,
    rowHeights,
    defaultRowHeight,
    collapsedInstances,
    waveformHeight: WAVEFORM_HEIGHT,
    groupHeaderHeight: GROUP_HEADER_HEIGHT,
  });
  const target = layout.headerTops.get(`${groupId}:${instanceIdx}`);
  if (!target) return;

  const instanceLines = linesOfInstance(projectLines, groupId, instanceIdx);
  const bounds = instanceBounds(instanceLines);

  const viewportWidth = container.clientWidth;
  const viewportHeight = container.clientHeight;
  const scrollLeft = bounds
    ? Math.max(0, bounds.begin * zoom - viewportWidth / 2 + GUTTER_WIDTH)
    : container.scrollLeft;

  const rowCenter = target.top + target.height / 2;
  const scrollTop = Math.max(0, Math.min(container.scrollHeight - viewportHeight, rowCenter - viewportHeight / 2));

  container.scrollTo({ left: scrollLeft, top: scrollTop, behavior: "smooth" });
}

// -- Exports -------------------------------------------------------------------

// Centers the timeline on `time` and scrolls the line playing at that time into view (or its
// group header when that instance is collapsed).
function revealTimeInTimeline(container: HTMLElement, lines: readonly LyricLine[], time: number): void {
  const { zoom, rowHeights, defaultRowHeight, collapsedInstances } = useTimelineStore.getState();
  container.scrollLeft = centerTimeScrollLeft(time, zoom, container.clientWidth);

  const line = lines.find((candidate) => {
    const timing = effectiveBounds(candidate);
    return timing !== null && time >= timing.begin && time < timing.end;
  });
  if (!line) return;

  const layout = computeRowLayout({
    lines: [...lines],
    rowHeights,
    defaultRowHeight,
    collapsedInstances,
    waveformHeight: WAVEFORM_HEIGHT,
    groupHeaderHeight: GROUP_HEADER_HEIGHT,
  });
  const instanceKey = isLinked(line) ? `${line.groupId}:${line.instanceIdx}` : null;
  const pos =
    instanceKey && collapsedInstances[instanceKey] ? layout.headerTops.get(instanceKey) : layout.lineTops.get(line.id);
  if (!pos) return;

  const viewportHeight = container.clientHeight;
  const rowCenter = pos.top + pos.height / 2;
  const targetTop = Math.max(0, Math.min(container.scrollHeight - viewportHeight, rowCenter - viewportHeight / 2));
  container.scrollTo({ top: targetTop, behavior: "instant" });
}

// The same, for callers outside the timeline (it finds the mounted timeline itself).
function revealTimeInMountedTimeline(time: number): void {
  const container = document.querySelector<HTMLDivElement>("[data-scroll-container]");
  if (!container) return;
  revealTimeInTimeline(container, useProjectStore.getState().lines, time);
}

export { revealTimeInMountedTimeline, revealTimeInTimeline, scrollToInstanceHeader };
