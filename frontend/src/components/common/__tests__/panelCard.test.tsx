/** @vitest-environment jsdom */
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
