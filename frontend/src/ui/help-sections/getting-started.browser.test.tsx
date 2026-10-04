import { describe, expect, it } from "vitest";
import { render } from "@/test/render";
import { GettingStartedSection } from "@/ui/help-sections/getting-started";

describe("GettingStartedSection", () => {
  it("renders the section content", async () => {
    const screen = await render(<GettingStartedSection />);
    await expect.element(screen.getByRole("heading", { name: "1. Check the flagged lines" })).toBeInTheDocument();
  });

  it("renders the tab shortcuts as inline key badges", async () => {
    const screen = await render(<GettingStartedSection />);
    await expect.poll(() => screen.container.querySelectorAll("[data-inline-key-badge]").length).toBe(3);
  });

  it("does not send the reader to tabs the editor no longer has", async () => {
    const screen = await render(<GettingStartedSection />);
    const text = screen.container.textContent ?? "";
    for (const tab of ["Import tab", "Sync tab", "Export", "YouTube"]) expect(text).not.toContain(tab);
  });
});
