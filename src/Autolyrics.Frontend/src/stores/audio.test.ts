import { useAudioStore } from "@/stores/audio";
import { useSettingsStore } from "@/stores/settings";
import { beforeEach, describe, expect, it } from "vitest";

beforeEach(() => {
  useAudioStore.getState().reset();
});

describe("useAudioStore - setSource", () => {
  it("sets a file source", () => {
    const file = new File([new Uint8Array([1, 2, 3])], "song.m4a", { type: "audio/mp4" });
    useAudioStore.getState().setSource({ type: "file", file });
    expect(useAudioStore.getState().source).toEqual({ type: "file", file });
  });

  it("resets currentTime, duration, and isPlaying", () => {
    useAudioStore.setState({ currentTime: 42, duration: 200, isPlaying: true });
    useAudioStore.getState().setSource({ type: "file", file: new File(["audio"], "song.mp3") });
    const state = useAudioStore.getState();
    expect(state.currentTime).toBe(0);
    expect(state.duration).toBe(0);
    expect(state.isPlaying).toBe(false);
  });
});

describe("useAudioStore - reset", () => {
  it("clears the source", () => {
    useAudioStore.getState().setSource({ type: "file", file: new File(["audio"], "song.mp3") });
    useAudioStore.getState().reset();
    expect(useAudioStore.getState().source).toBeNull();
  });
});

describe("useAudioStore - seekTo", () => {
  it("ignores non-finite times", () => {
    useAudioStore.setState({ currentTime: 12 });
    useAudioStore.getState().seekTo(Number.POSITIVE_INFINITY);
    expect(useAudioStore.getState().currentTime).toBe(12);
    useAudioStore.getState().seekTo(Number.NaN);
    expect(useAudioStore.getState().currentTime).toBe(12);
  });

  it("ignores negative times", () => {
    useAudioStore.setState({ currentTime: 12 });
    useAudioStore.getState().seekTo(-1);
    expect(useAudioStore.getState().currentTime).toBe(12);
  });

  it("accepts a valid time", () => {
    useAudioStore.getState().seekTo(5);
    expect(useAudioStore.getState().currentTime).toBe(5);
  });
});

describe("useAudioStore - setPlaybackRate", () => {
  it("persists the selected playback rate as the default", () => {
    useAudioStore.getState().setPlaybackRate(1.5);
    expect(useAudioStore.getState().playbackRate).toBe(1.5);
    expect(useSettingsStore.getState().defaultPlaybackRate).toBe(1.5);
  });

  it("ignores invalid playback rates", () => {
    useAudioStore.setState({ playbackRate: 1 });
    useSettingsStore.getState().set("defaultPlaybackRate", 1);
    useAudioStore.getState().setPlaybackRate(0);
    useAudioStore.getState().setPlaybackRate(Number.NaN);
    expect(useAudioStore.getState().playbackRate).toBe(1);
    expect(useSettingsStore.getState().defaultPlaybackRate).toBe(1);
  });
});
