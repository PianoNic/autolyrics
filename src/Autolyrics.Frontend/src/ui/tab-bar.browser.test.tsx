import { useProjectStore } from "@/stores/project";
import { useSettingsStore } from "@/stores/settings";
import { render } from "@/test/render";
import { TabBar } from "@/ui/tab-bar";
import { beforeEach, describe, expect, it } from "vitest";

const TAB_NAME_REGEX = {
  Edit: /^Edit/,
  Timeline: /^Timeline/,
  Preview: /^Preview/,
} as const;

describe("TabBar", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
    useSettingsStore.getState().resetToDefaults();
  });

  it("renders one button per tab", async () => {
    const screen = await render(<TabBar />);
    await Promise.all(
      Object.values(TAB_NAME_REGEX).map((nameRegex) =>
        expect.element(screen.getByRole("button", { name: nameRegex })).toBeInTheDocument(),
      ),
    );
    expect(screen.container.querySelectorAll("button")).toHaveLength(3);
  });

  it("opens on the Timeline tab", async () => {
    const screen = await render(<TabBar />);
    const timelineButton = screen.getByRole("button", { name: /^Timeline/ }).element();
    expect(timelineButton.className).toContain("border-composer-accent");
  });

  it("highlights the currently active tab from the project store", async () => {
    useProjectStore.setState({ activeTab: "preview" });
    const screen = await render(<TabBar />);
    const previewButton = screen.getByRole("button", { name: /^Preview/ }).element();
    expect(previewButton.className).toContain("border-composer-accent");
  });

  it("dispatches setActiveTab on the project store when a tab is clicked", async () => {
    useProjectStore.setState({ activeTab: "edit" });
    const screen = await render(<TabBar />);
    await screen.getByRole("button", { name: /^Timeline/ }).click();
    expect(useProjectStore.getState().activeTab).toBe("timeline");
  });

  it("hides shortcut hints when settings.showShortcutHints is false", async () => {
    useSettingsStore.setState({ showShortcutHints: false });
    const screen = await render(<TabBar />);
    expect(screen.container.querySelector("svg")).toBeNull();
  });

  it("shows shortcut hints when settings.showShortcutHints is true", async () => {
    useSettingsStore.setState({ showShortcutHints: true });
    const screen = await render(<TabBar />);
    expect(screen.container.querySelectorAll("[data-inline-key-badge]")).toHaveLength(3);
  });
});
