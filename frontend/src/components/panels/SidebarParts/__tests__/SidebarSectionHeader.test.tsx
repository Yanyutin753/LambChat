/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SidebarSectionHeader } from "../SidebarSectionHeader";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test("touch reveals only the current section and renews its three-second timeout", () => {
  vi.useFakeTimers();
  render(
    <>
      {["Chats", "Projects"].map((label) => (
        <SidebarSectionHeader
          key={label}
          label={label}
          collapsed={false}
          onToggle={vi.fn()}
          createLabel={`New ${label}`}
          onCreate={vi.fn()}
        />
      ))}
    </>,
  );
  const chats = screen
    .getByRole("button", { name: "Chats" })
    .closest(".sidebar-action-row")!;
  const projects = screen
    .getByRole("button", { name: "Projects" })
    .closest(".sidebar-action-row")!;
  expect(chats).not.toHaveAttribute("data-revealed", "true");
  fireEvent.touchStart(chats);
  expect(chats).toHaveAttribute("data-revealed", "true");
  expect(projects).not.toHaveAttribute("data-revealed", "true");
  act(() => vi.advanceTimersByTime(2000));
  fireEvent.touchStart(chats);
  act(() => vi.advanceTimersByTime(2000));
  expect(chats).toHaveAttribute("data-revealed", "true");
  act(() => vi.advanceTimersByTime(1000));
  expect(chats).not.toHaveAttribute("data-revealed", "true");
});

test("section toggle and create remain available without a duplicate menu", () => {
  const toggle = vi.fn();
  const create = vi.fn();
  render(
    <SidebarSectionHeader
      label="Chats"
      collapsed
      onToggle={toggle}
      createLabel="New chat"
      onCreate={create}
      createIcon="compose"
    />,
  );
  const heading = screen.getByRole("button", { name: "Chats" });
  expect(heading.getAttribute("aria-expanded")).toBe("false");
  expect(heading.querySelector("svg")).not.toBeNull();
  fireEvent.click(heading);
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(create).toHaveBeenCalledOnce();
  expect(toggle).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button", { name: "More" })).toBeNull();
});

test.each([false, true])(
  "the rendered arrow matches the shipped direct-child reveal selector when touched (collapsed=%s)",
  (collapsed) => {
    vi.useFakeTimers();
    render(
      <SidebarSectionHeader
        label="Chats"
        collapsed={collapsed}
        onToggle={vi.fn()}
        createLabel="New chat"
        onCreate={vi.fn()}
      />,
    );
    const heading = screen.getByRole("button", { name: "Chats" });
    const row = heading.closest(".sidebar-action-row")!;
    const arrow = heading.querySelector("svg")!;
    const css = postcss.parse(
      readFileSync(resolve(process.cwd(), "src/styles/components.css"), "utf8"),
    );
    let revealSelector: string | undefined;
    css.walkRules((rule) => {
      if (!rule.selector.includes(".sidebar-action-row:is")) return;
      const directChild = rule.selectors.find((selector) =>
        />\s*button\s*>\s*\.sidebar-action-reveal\s*$/.test(selector),
      );
      if (directChild) revealSelector = directChild;
    });
    expect(revealSelector).toBeDefined();
    expect(arrow.parentElement).toBe(heading);
    expect(arrow.matches(revealSelector!)).toBe(false);
    fireEvent.touchStart(row);
    expect(arrow.matches(revealSelector!)).toBe(true);
    act(() => vi.advanceTimersByTime(3000));
    expect(arrow.matches(revealSelector!)).toBe(false);
  },
);
