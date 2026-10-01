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
