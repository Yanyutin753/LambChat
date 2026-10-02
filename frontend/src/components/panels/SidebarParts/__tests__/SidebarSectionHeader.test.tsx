/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SidebarSectionHeader } from "../SidebarSectionHeader";

afterEach(cleanup);

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
