import { describe, expect, it } from "vitest";
import { render } from "@/test/render";
import { AboutSection } from "@/ui/help-sections/about";

describe("AboutSection", () => {
  it("renders the section content", async () => {
    const screen = await render(<AboutSection />);
    await expect.element(screen.getByRole("heading", { name: "What it is" })).toBeInTheDocument();
  });

  it("credits Composer, which the editor is built on", async () => {
    const screen = await render(<AboutSection />);
    await expect
      .element(screen.getByRole("link", { name: "Composer" }))
      .toHaveAttribute("href", "https://github.com/better-lyrics/composer");
    await expect.element(screen.getByText(/not affiliated with or endorsed by them/)).toBeInTheDocument();
  });

  it("states the license", async () => {
    const screen = await render(<AboutSection />);
    await expect.element(screen.getByRole("heading", { name: "License" })).toBeInTheDocument();
    await expect.element(screen.getByText(/AGPL v3/)).toBeInTheDocument();
  });
});
