/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ModalSurface } from "../ModalSurface";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("Tab wraps visible modal controls without entering collapsed descendants", () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    {},
  ] as DOMRectList);
  render(
    <ModalSurface open onClose={() => {}} label="Settings">
      <button>First</button>
      <button>Last visible</button>
      <div inert aria-hidden="true">
        <input aria-label="Collapsed setting" />
      </div>
    </ModalSurface>,
  );
  screen.getByRole("button", { name: "Last visible" }).focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "First" }),
  );
});

test("Tab skips controls removed from sequential keyboard navigation", () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    {},
  ] as DOMRectList);
  render(
    <ModalSurface open onClose={vi.fn()} label="Settings">
      <button>First</button>
      <button>Last visible</button>
      <button tabIndex={-1}>Pointer only</button>
    </ModalSurface>,
  );
  screen.getByRole("button", { name: "Last visible" }).focus();
  const event = new KeyboardEvent("keydown", {
    key: "Tab",
    bubbles: true,
    cancelable: true,
  });
  fireEvent(document.activeElement!, event);
  expect(event.defaultPrevented).toBe(true);
  expect(screen.getByRole("button", { name: "First" })).toHaveFocus();
});

test("a rich text editor participates in the modal Tab cycle", () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    {},
  ] as DOMRectList);
  render(
    <ModalSurface open onClose={vi.fn()} label="Edit">
      <button>Close</button>
      <div contentEditable role="textbox" aria-label="Draft" />
    </ModalSurface>,
  );
  screen.getByRole("textbox").focus();
  expect(screen.getByRole("textbox")).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "Tab" });
  expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
});
