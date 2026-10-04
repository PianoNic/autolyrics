import { AnimatePresence } from "motion/react";
import { useRef } from "react";
import { useFrameLoop } from "@/hooks/use-frame-loop";
import { useProjectStore } from "@/stores/project";
import { SnapMarkerPin } from "@/views/timeline/snap-marker-pin";
import { useSnapMarkerDrag } from "@/views/timeline/use-snap-marker-drag";
import { GUTTER_WIDTH, useTimelineStore, WAVEFORM_HEIGHT } from "@/views/timeline/timeline-store";

// -- Types ---------------------------------------------------------------------

interface SnapMarkersOverlayProps {
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
}

// -- Constants -----------------------------------------------------------------

// -- Helpers -------------------------------------------------------------------

// Module-scope so its identity is stable across renders, otherwise a fresh
// closure per pin would defeat SnapMarkerPin's memo and re-render every pin on
// each drag frame.
function handleSnapPinHoverChange(id: string, hovering: boolean): void {
  const store = useTimelineStore.getState();
  if (hovering) store.setHoveredSnapPointId(id);
  else if (store.hoveredSnapPointId === id) store.setHoveredSnapPointId(null);
}

// -- Component -----------------------------------------------------------------

const SnapMarkersOverlay: React.FC<SnapMarkersOverlayProps> = ({ scrollContainerRef }) => {
  const zoom = useTimelineStore((s) => s.zoom);
  const customSnapPoints = useProjectStore((s) => s.customSnapPoints);
  const removeCustomSnapPoint = useProjectStore((s) => s.removeCustomSnapPoint);
  const markerMode = useTimelineStore((s) => s.markerMode);

  const { draggingId, onHeadPointerDown } = useSnapMarkerDrag({ scrollContainerRef });

  const layerRef = useRef<HTMLDivElement>(null);

  const isVisible = customSnapPoints.length > 0 || markerMode;

  useFrameLoop(
    () => {
      const layer = layerRef.current;
      if (layer) {
        const scrollLeft = scrollContainerRef.current?.scrollLeft ?? useTimelineStore.getState().scrollLeft;
        layer.style.transform = `translate3d(${GUTTER_WIDTH - scrollLeft}px, 0, 0)`;
      }
    },
    "snap-markers-overlay",
    isVisible,
  );

  if (!isVisible) return null;

  return (
    <div
      data-snap-markers-overlay
      className="absolute inset-0 pointer-events-none overflow-hidden select-none z-40"
      style={{ clipPath: `inset(0 0 calc(100% - ${WAVEFORM_HEIGHT - 1}px) ${GUTTER_WIDTH}px)` }}
    >
      <div
        ref={layerRef}
        data-snap-markers-layer
        className="absolute inset-0 pointer-events-none"
        style={{ transform: `translate3d(${GUTTER_WIDTH}px, 0, 0)` }}
      >
        <div className="absolute inset-0 pointer-events-none z-20">
          <AnimatePresence initial={false}>
            {customSnapPoints.map((point) => (
              <SnapMarkerPin
                key={point.id}
                id={point.id}
                time={point.time}
                zoom={zoom}
                fadeExtent={WAVEFORM_HEIGHT}
                isDragging={draggingId === point.id}
                onHeadPointerDown={onHeadPointerDown}
                onDelete={removeCustomSnapPoint}
                onHoverChange={handleSnapPinHoverChange}
              />
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

// -- Exports -------------------------------------------------------------------

export { SnapMarkersOverlay };
