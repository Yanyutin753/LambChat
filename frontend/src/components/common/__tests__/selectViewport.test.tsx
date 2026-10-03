/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Select } from "../ui/Select";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("select options fit the visible viewport above the mobile keyboard", () => {
  const viewport = {
    width: 320,
    height: 240,
    offsetLeft: 0,
    offsetTop: 40,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  vi.stubGlobal("visualViewport", viewport);
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue(
    new DOMRect(12, 140, 500, 36),
  );
  render(
    <Select
      value="one"
      onChange={vi.fn()}
      ariaLabel="Model"
      options={[{ value: "one", label: "First" }]}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Model" }));
  const menu = screen.getByRole("listbox", { name: "Model" });
  expect(Number.parseFloat(menu.style.width)).toBeLessThanOrEqual(288);
  expect(Number.parseFloat(menu.style.maxHeight)).toBeLessThanOrEqual(84);
});

test("select listbox inherits the visible selection name when no label is supplied", () => {
  render(
    <Select
      value="one"
      onChange={vi.fn()}
      options={[{ value: "one", label: "General agent" }]}
    />,
  );
  const trigger = screen.getByRole("button", { name: "General agent" });
  fireEvent.click(trigger);
  const listbox = screen.getByRole("listbox", { name: "General agent" });
  expect(trigger.getAttribute("aria-controls")).toBe(listbox.id);
});

test("labelled select describes its current value after it changes", () => {
  const props = {
    onChange: vi.fn(),
    ariaLabel: "Role",
    options: [
      { value: "a", label: "Alpha" },
      { value: "b", label: "Beta" },
    ],
  };
  const view = render(<Select {...props} value="a" />);
  expect(
    screen.getByRole("button", { name: "Role", description: "Alpha" }),
  ).toBeTruthy();
  view.rerender(<Select {...props} value="b" />);
  expect(
    screen.getByRole("button", { name: "Role", description: "Beta" }),
  ).toBeTruthy();
});

test("disabling a select closes its portalled choices and does not reopen on recovery", () => {
  const props = {
    value: "one",
    ariaLabel: "Model",
    onChange: vi.fn(),
    options: [{ value: "one", label: "First" }],
  };
  const view = render(<Select {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Model" }));
  expect(screen.getByRole("listbox")).toBeTruthy();
  view.rerender(<Select {...props} disabled />);
  expect(screen.queryByRole("listbox")).toBeNull();
  view.rerender(<Select {...props} />);
  expect(screen.queryByRole("listbox")).toBeNull();
});

test("an already closed disabled select does not announce an artificial open change", () => {
  const onOpenChange = vi.fn();
  render(
    <Select
      value="one"
      disabled
      onOpenChange={onOpenChange}
      onChange={vi.fn()}
      options={[{ value: "one", label: "First" }]}
    />,
  );
  expect(onOpenChange).not.toHaveBeenCalled();
});

test("grouped options keep headings out of keyboard navigation and skip disabled choices", () => {
  const onChange = vi.fn();
  render(
    <Select
      value="one"
      onChange={onChange}
      ariaLabel="Category"
      options={[
        { value: "one", label: "First", group: "Basics" },
        { value: "two", label: "Second", group: "Models", disabled: true },
        { value: "three", label: "Third", group: "Models" },
      ]}
    />,
  );
  const trigger = screen.getByRole("button", { name: "Category" });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  expect(screen.getAllByRole("group")).toHaveLength(2);
  expect(screen.getByRole("group", { name: "Models" })).toContainElement(
    screen.getByRole("option", { name: "Third" }),
  );
  expect(screen.getByRole("option", { name: "First" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
  expect(screen.getByRole("option", { name: "Third" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(trigger).toHaveFocus();
  expect(onChange).not.toHaveBeenCalled();
});
