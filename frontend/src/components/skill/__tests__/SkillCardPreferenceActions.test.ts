/** @vitest-environment jsdom */
import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SkillCard } from "../SkillCard";
import type { SkillResponse } from "../../../types";

vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("disabled skills keep the same card surface and retain their status", () => {
  const toggle = vi.fn();
  const { container } = render(
    createElement(SkillCard, {
      skill: {
        name: "research",
        description: "Research notes",
        tags: [],
        enabled: false,
        source: "manual",
        files: {},
        file_count: 1,
        installed_from: "manual",
        is_published: false,
        marketplace_is_active: true,
      },
      onToggle: toggle,
      onEdit: vi.fn(),
      onDelete: vi.fn(),
    }),
  );
  expect(container.querySelector(".scb--muted")).toBeNull();
  expect(screen.getByText("skills.card.disabled")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "skills.card.enable" }));
  expect(toggle).toHaveBeenCalledWith("research");
});

test("favorite and pin actions preserve preferences without opening the editor", () => {
  const skill: SkillResponse = {
    name: "research",
    description: "Research notes",
    tags: ["研究"],
    enabled: true,
    source: "manual",
    files: {},
    file_count: 1,
    installed_from: "manual",
    is_published: false,
    marketplace_is_active: true,
    is_favorite: true,
    is_pinned: false,
  };
  const preferences = vi.fn();
  const edit = vi.fn();
  render(
    createElement(SkillCard, {
      skill,
      onToggle: vi.fn(),
      onEdit: edit,
      onDelete: vi.fn(),
      onTogglePreference: preferences,
    }),
  );
  const favorite = screen.getByRole("button", {
    name: "personaPresets.favorite",
  });
  expect(favorite.getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(favorite);
  expect(preferences).toHaveBeenCalledWith(skill, { is_favorite: false });
  fireEvent.click(screen.getByRole("button", { name: "personaPresets.pin" }));
  expect(preferences).toHaveBeenCalledWith(skill, { is_pinned: true });
  expect(edit).not.toHaveBeenCalled();
});
