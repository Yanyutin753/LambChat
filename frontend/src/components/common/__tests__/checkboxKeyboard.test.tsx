/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Checkbox } from "../Checkbox";
afterEach(cleanup);
test("checkbox supports named keyboard activation without activating its parent", () => {
  const change = vi.fn(),
    parent = vi.fn();
  render(
    <div onKeyDown={parent}>
      <Checkbox checked={false} onChange={change} ariaLabel="Research" />
    </div>,
  );
  const checkbox = screen.getByRole("checkbox", { name: "Research" });
  expect(checkbox.tabIndex).toBe(0);
  fireEvent.keyDown(checkbox, { key: " " });
  fireEvent.keyDown(checkbox, { key: "Enter" });
  expect(change).toHaveBeenCalledTimes(2);
  expect(parent).not.toHaveBeenCalled();
});
test("disabled checkbox cannot activate by keyboard or pointer", () => {
  const change = vi.fn();
  render(<Checkbox checked disabled onChange={change} />);
  const checkbox = screen.getByRole("checkbox");
  expect(checkbox.tabIndex).toBe(-1);
  fireEvent.keyDown(checkbox, { key: " " });
  fireEvent.click(checkbox);
  expect(change).not.toHaveBeenCalled();
});

test("a decorative checkbox leaves its parent as the only interactive control", () => {
  const parent = vi.fn();
  const { container } = render(
    <button onClick={parent} aria-pressed>
      <Checkbox checked />
    </button>,
  );
  expect(screen.queryByRole("checkbox")).toBeNull();
  fireEvent.click(container.querySelector(".ui-checkbox")!);
  expect(parent).toHaveBeenCalledOnce();
});
