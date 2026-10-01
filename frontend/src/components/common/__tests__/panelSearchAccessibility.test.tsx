/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PanelSearchInput } from "../PanelSearchInput";

afterEach(cleanup);

test("search exposes its translated placeholder as a name and preserves explicit labels", () => {
  const { rerender } = render(
    <PanelSearchInput placeholder="Search memories" onValueChange={vi.fn()} />,
  );
  expect(screen.getByRole("textbox", { name: "Search memories" })).toBeTruthy();
  rerender(
    <PanelSearchInput
      placeholder="Search"
      aria-label="Find files"
      onValueChange={vi.fn()}
    />,
  );
  expect(screen.getByRole("textbox", { name: "Find files" })).toBeTruthy();
});

test("search waits for Chinese composition to finish before filtering", () => {
  const change = vi.fn();
  render(<PanelSearchInput placeholder="Search" onValueChange={change} />);
  const input = screen.getByRole("textbox");
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "yan" } });
  expect(change).not.toHaveBeenCalled();
  fireEvent.compositionEnd(input, { target: { value: "研究" } });
  expect(change).toHaveBeenCalledWith("研究");
});
