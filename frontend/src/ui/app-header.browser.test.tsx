import { describe, expect, it } from "vitest";
import { AppHeader } from "@/ui/app-header";
import { render } from "@/test/render";

describe("AppHeader", () => {
  it("renders the autolyrics logo and brand text", async () => {
    const screen = await render(<AppHeader onSettingsOpen={() => {}} onHelpOpen={() => {}} />);
    expect(screen.container.querySelector('img[src="/logo.svg"]')).not.toBeNull();
    expect(screen.container.textContent).toContain("autolyrics");
  });

  it("calls onSettingsOpen when the settings button is clicked", async () => {
    let calls = 0;
    const screen = await render(
      <AppHeader onSettingsOpen={() => calls++} onHelpOpen={() => {}} />,
    );
    await screen.getByRole("button", { name: "Settings" }).click();
    expect(calls).toBe(1);
  });

  it("calls onHelpOpen when the help button is clicked", async () => {
    let calls = 0;
    const screen = await render(
      <AppHeader onSettingsOpen={() => {}} onHelpOpen={() => calls++} />,
    );
    await screen.getByRole("button", { name: /Keyboard shortcuts/ }).click();
    expect(calls).toBe(1);
  });

});
