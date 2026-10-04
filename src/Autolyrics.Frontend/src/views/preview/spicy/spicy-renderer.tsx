// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/lyrics.ts (fcc5f83), the per-frame driver and the line click listener.
// Spicy reads the clock from Spotify's player; here the editor's audio element drives it.

import { useFrameLoop } from "@/hooks/use-frame-loop";
import { holdFrames, wake } from "@/lib/frame-loop";
import { useAudioStore } from "@/stores/audio";
import { cn } from "@/utils/cn";
import { LYRICS_ELEMENT_CLASS, type LyricsLayout } from "@/views/preview/lyrics-layout";
import { type AnimatorState, animateDocument, createAnimatorState } from "@/views/preview/spicy/animate";
import { buildSpicyDocument } from "@/views/preview/spicy/build-document";
import { type SpicyLyricsData, parseSpicyLyrics } from "@/views/preview/spicy/lyrics-data";
import type { SpicyDocument } from "@/views/preview/spicy/model";
import { type ScrollState, createScrollState, followActiveLine, noteUserScroll } from "@/views/preview/spicy/scroll";
import spicyCss from "@/views/preview/spicy/spicy-lyrics.css?raw";
import { useCallback, useEffect, useMemo, useRef } from "react";

// -- Interfaces ---------------------------------------------------------------

interface SpicyRendererProps {
  ttmlString: string;
  layout?: LyricsLayout;
}

interface BuiltDocument {
  data: SpicyLyricsData;
  doc: SpicyDocument;
}

// -- Constants ----------------------------------------------------------------

const SPRINGS_HOLD_LABEL = "spicy-springs";

/** A frame after an idle stretch animates one ordinary step instead of jumping the springs. */
const MAX_FRAME_SECONDS = 1 / 30;

// -- Helpers ------------------------------------------------------------------

function playbackTimeMs(audio: HTMLAudioElement | null): number {
  return (audio ? audio.currentTime : useAudioStore.getState().currentTime) * 1000;
}

// -- Component ----------------------------------------------------------------

const SpicyRenderer: React.FC<SpicyRendererProps> = ({ ttmlString, layout = "page" }) => {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const builtRef = useRef<BuiltDocument | null>(null);
  const animatorRef = useRef<AnimatorState>(createAnimatorState());
  const scrollStateRef = useRef<ScrollState>(createScrollState());
  const lastFrameRef = useRef<number | null>(null);
  const releaseHoldRef = useRef<(() => void) | null>(null);
  const data = useMemo(() => parseSpicyLyrics(ttmlString), [ttmlString]);

  const setSpringsHeld = useCallback((held: boolean) => {
    if (held === (releaseHoldRef.current !== null)) return;
    if (held) {
      releaseHoldRef.current = holdFrames(SPRINGS_HOLD_LABEL);
      return;
    }
    releaseHoldRef.current?.();
    releaseHoldRef.current = null;
  }, []);

  // Activity re-runs this on every reveal; the lines built for the same lyrics are kept.
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    if (builtRef.current?.data !== data) {
      builtRef.current?.doc.container.remove();
      builtRef.current = { data, doc: buildSpicyDocument(data) };
      animatorRef.current = createAnimatorState();
    }
    const { container } = builtRef.current.doc;
    if (container.parentElement !== scroller) scroller.appendChild(container);
    scrollStateRef.current = createScrollState();
    wake();
  }, [data]);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const handleUserScroll = () => noteUserScroll(scroller, scrollStateRef.current);
    const resizeObserver = new ResizeObserver(() => {
      scrollStateRef.current.lastLine = null;
      wake();
    });
    scroller.addEventListener("wheel", handleUserScroll, { passive: true });
    scroller.addEventListener("touchmove", handleUserScroll, { passive: true });
    resizeObserver.observe(scroller);
    return () => {
      scroller.removeEventListener("wheel", handleUserScroll);
      scroller.removeEventListener("touchmove", handleUserScroll);
      resizeObserver.disconnect();
      setSpringsHeld(false);
    };
  }, [setSpringsHeld]);

  const handleClick = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const lineElement = (event.target as HTMLElement).closest(".line");
    const line = builtRef.current?.doc.lines.find((candidate) => candidate.element === lineElement);
    if (!line) return;
    const audio = useAudioStore.getState();
    audio.seekTo(line.seekTime / 1000);
    audio.setIsPlaying(true);
    scrollStateRef.current.lastLine = null;
  }, []);

  useFrameLoop((now) => {
    const built = builtRef.current;
    const scroller = scrollerRef.current;
    if (!built || !scroller?.isConnected) {
      setSpringsHeld(false);
      return;
    }
    const audio = useAudioStore.getState().audioElement;
    const time = playbackTimeMs(audio);
    const previous = lastFrameRef.current;
    lastFrameRef.current = now;
    const dt = previous === null ? 0 : Math.min(Math.max((now - previous) / 1000, 0), MAX_FRAME_SECONDS);

    const awake = animateDocument(built.doc, animatorRef.current, { time, dt, snap: false, awake: false });
    setSpringsHeld(awake);
    followActiveLine(built.doc, scroller, scrollStateRef.current, time, audio ? !audio.paused : false);
  }, "spicy-renderer");

  return (
    <div data-lyrics-layout={layout} className="spicy-lyrics-root relative flex flex-col flex-1 min-h-0">
      <style>{spicyCss}</style>
      <div
        ref={scrollerRef}
        data-testid="spicy-lyrics"
        onClick={handleClick}
        className={cn("spicy-lyrics LyricsContent", LYRICS_ELEMENT_CLASS[layout])}
      />
    </div>
  );
};

// -- Exports ------------------------------------------------------------------

export { SpicyRenderer };
