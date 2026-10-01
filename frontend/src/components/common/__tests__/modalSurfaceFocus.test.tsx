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
