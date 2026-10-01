/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SkillBaseCard } from "../SkillBaseCard";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("right click and more button open the same actions without activating the card", () => {
  const edit = vi.fn();
  const activate = vi.fn();
  const { container } = render(
    <SkillBaseCard
      title="Research"
      onClick={activate}
      actions={[{ label: "Edit", onClick: edit }]}
    />,
  );
  fireEvent.contextMenu(container.querySelector(".scb")!, {
    clientX: 100,
    clientY: 100,
  });
  fireEvent.click(screen.getByRole("menuitem", { name: "Edit" }));
  expect(edit).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("menu")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.moreOptions" }));
  expect(screen.getByRole("menuitem", { name: "Edit" })).toBeTruthy();
  expect(activate).not.toHaveBeenCalled();
});
test("keyboard menu supports navigation, Escape and focus return", () => {
  const { container } = render(
    <SkillBaseCard
      title="Research"
      onClick={vi.fn()}
      actions={[
        { label: "Edit", onClick: vi.fn() },
        { label: "Delete", onClick: vi.fn(), danger: true },
      ]}
    />,
  );
  const card = container.querySelector<HTMLElement>(".scb")!;
  card.focus();
  fireEvent.keyDown(card, { key: "F10", shiftKey: true });
  expect(document.activeElement).toBe(
    screen.getByRole("menuitem", { name: "Edit" }),
  );
  fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
  expect(document.activeElement).toBe(
    screen.getByRole("menuitem", { name: "Delete" }),
  );
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(document.activeElement).toBe(card);
});
test("outside click closes the menu and nested controls do not activate the card", () => {
  const activate = vi.fn();
  render(
    <SkillBaseCard
      title="Research"
      onClick={activate}
      footer={<button>Toggle</button>}
      actions={[{ label: "Edit", onClick: vi.fn() }]}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Toggle" }));
  expect(activate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "common.moreOptions" }));
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("menu")).toBeNull();
});

test("clicking more again closes its menu", () => {
  render(
    <SkillBaseCard
      title="Research"
      actions={[{ label: "Edit", onClick: vi.fn() }]}
    />,
  );
  const more = screen.getByRole("button", { name: "common.moreOptions" });
  fireEvent.click(more);
  fireEvent.pointerDown(more);
  fireEvent.click(more);
  expect(screen.queryByRole("menu")).toBeNull();
});
test("card primary action is separate from its nested controls", () => {
  const activate = vi.fn();
  const { container } = render(
    <SkillBaseCard
      title="Research"
      onClick={activate}
      footer={
        <button role="switch" aria-checked="true">
          Toggle
        </button>
      }
    />,
  );
  expect(container.querySelector(".scb")?.getAttribute("role")).not.toBe(
    "button",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Research", exact: true }),
  );
  expect(activate).toHaveBeenCalledTimes(1);
});
