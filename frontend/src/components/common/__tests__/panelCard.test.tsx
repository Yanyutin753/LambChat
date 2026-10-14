/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { SkillBaseCard } from "../SkillBaseCard";
test("cards remain promptly available late in a staggered list", () => {
  const { container } = render(
    <SkillBaseCard title="Last result" animated animationDelay={1140} />,
  );
  expect(
    (container.querySelector(".scb") as HTMLElement).style.animationDelay,
  ).toBe("180ms");
});
test("restores the original banner while keeping management actions", () => {
  const { container } = render(
    <SkillBaseCard
      title="Research"
      gradient={["red", "green", "blue"]}
      bannerOverlay={<button>Manage</button>}
    />,
  );
  expect(screen.getByRole("button", { name: "Manage" })).toBeTruthy();
  expect(container.querySelector(".scb__banner")).not.toBeNull();
});

test("marketplace cards keep one title and icon below the original banner", () => {
  const { container } = render(
    <SkillBaseCard
      title="Hire Me"
      gradient={["red", "green", "blue"]}
      icon={<span>H</span>}
      statusPills={<span>Published</span>}
    />,
  );
  const cover = container.querySelector(".scb__banner");
  expect(cover).not.toBeNull();
  expect(container.querySelector("h3")?.textContent).toBe("Hire Me");
  expect(container.querySelectorAll("h3")).toHaveLength(1);
  expect(cover?.textContent).not.toContain("Published");
});

test("card selection supports the keyboard without hijacking nested actions", async () => {
  const { fireEvent } = await import("@testing-library/react");
  const { vi } = await import("vitest");
  const onSelect = vi.fn();
  const { container } = render(
    <SkillBaseCard
      title="Keyboard card"
      selectionMode
      onSelect={onSelect}
      bannerOverlay={<button>Inspect</button>}
    />,
  );
  const card = container.querySelector(".scb")!;
  fireEvent.keyDown(card, { key: "Enter" });
  expect(onSelect).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(screen.getByRole("button", { name: "Inspect" }), {
    key: "Enter",
  });
  expect(onSelect).toHaveBeenCalledTimes(1);
});

test("resource cards center their icon beside a compact title and status", () => {
  const { container } = render(
    <SkillBaseCard
      title="Document assistant"
      icon={<span>D</span>}
      statusPills={<div className="mt-1.5">Published</div>}
    />,
  );
  const header = container.querySelector(".scb__header");
  expect(header?.classList.contains("items-center")).toBe(true);
  expect(header?.classList.contains("gap-2")).toBe(true);
  expect(header?.querySelector(".scb__status")?.textContent).toBe("Published");
  const styles = readFileSync("src/styles/card-base.css", "utf8");
  expect(styles).toMatch(/\.scb__status\s*\{[^}]*margin-top: 0\.125rem;/);
  expect(styles).toMatch(/\.scb__status > \*\s*\{\s*margin-top: 0;/);
  expect(styles).toMatch(
    /\.scb__status\s*\{[^}]*font-size: 0\.75rem;[^}]*line-height: 1\.25;/,
  );
  expect(styles).toMatch(
    /\.scb__header > :is\([^)]*\.scb__icon-ring[^)]*\)\s*\{[^}]*width: 2\.25rem;[^}]*height: 2\.25rem;/,
  );
  const icon = header?.querySelector("[aria-hidden]") as HTMLElement;
  expect(icon.style.width).toBe("36px");
  expect(icon.style.height).toBe("36px");
});

 test("resource cards use flat surfaces and shared compact content spacing", () => {
  const { container } = render(<SkillBaseCard title="Compact" description="Description" tags={<span>Tag</span>} />);
  expect(container.querySelector(".scb__body")).not.toBeNull();
  expect(container.querySelector(".scb__description")?.classList.contains("mt-2")).toBe(true);
  const styles = readFileSync("src/styles/card-base.css", "utf8");
  expect(styles).toMatch(/\.scb\s*\{[^}]*box-shadow: none;/);
  expect(styles).toMatch(/\.scb:hover\s*\{[^}]*transform: none;/);
});

test("mobile panel cards share compact spacing and generated avatars follow dark theme", () => {
 const styles = readFileSync("src/styles/panels.css", "utf8");
 expect(styles).toMatch(/\.panel-card[^}]*padding: 0\.75rem;/);
 expect(styles).toMatch(/\.dark \.agent-avatar__artwork[^}]*brightness\(0\.88\)/);
});
