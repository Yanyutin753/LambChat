/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SidebarSectionHeader } from "../SidebarSectionHeader";

afterEach(cleanup);

test("section toggle, add and more actions stay independent", () => {
  const toggle = vi.fn();
  const create = vi.fn();
  const select = vi.fn();
  render(
    <SidebarSectionHeader
      label="Chats"
      collapsed
      onToggle={toggle}
      createLabel="New chat"
      onCreate={create}
      moreLabel="More"
      menuItems={[{ label: "Select chats", onClick: select }]}
    />,
  );
  const heading = screen.getByRole("button", { name: "Chats" });
  expect(heading.getAttribute("aria-expanded")).toBe("false");
  expect(heading.querySelector("svg")).not.toBeNull();
  fireEvent.click(heading);
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(create).toHaveBeenCalledOnce();
  expect(toggle).toHaveBeenCalledOnce();
  const more = screen.getByRole("button", { name: "More" });
  fireEvent.click(more);
  const popover = document.getElementById(more.getAttribute("popovertarget")!);
  expect(popover?.getAttribute("popover")).toBe("auto");
  fireEvent.click(
    screen.getByRole("button", { name: "Select chats", hidden: true }),
  );
  expect(select).toHaveBeenCalledOnce();
  expect(toggle).toHaveBeenCalledOnce();
});
