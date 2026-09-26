/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { RichChatComposer } from "../RichChatComposer";

function fireArrowKey(
  editor: HTMLElement,
  key: "ArrowUp" | "ArrowDown",
  options: { isComposing?: boolean; keyCode?: number } = {},
) {
  const event = new KeyboardEvent("keydown", {
    key,
    code: key,
    bubbles: true,
    cancelable: true,
    isComposing: options.isComposing ?? false,
  });
  if (options.keyCode !== undefined) {
    Object.defineProperty(event, "keyCode", { value: options.keyCode });
  }
  fireEvent(editor, event);
  return event;
}

test("arrow keys during an IME composition never reach history navigation", () => {
  const onArrowKey = vi.fn(() => true);
  render(<RichChatComposer ariaLabel="message" onArrowKey={onArrowKey} />);
  const editor = screen.getByRole("textbox", { name: "message" });

  const composingEvent = fireArrowKey(editor, "ArrowUp", { isComposing: true });
  expect(onArrowKey).not.toHaveBeenCalled();
  expect(composingEvent.defaultPrevented).toBe(false);

  const legacyEvent = fireArrowKey(editor, "ArrowDown", { keyCode: 229 });
  expect(onArrowKey).not.toHaveBeenCalled();
  expect(legacyEvent.defaultPrevented).toBe(false);
});

test("plain arrow keys are still forwarded to onArrowKey", () => {
  const onArrowKey = vi.fn(() => true);
  render(<RichChatComposer ariaLabel="message" onArrowKey={onArrowKey} />);
  const editor = screen.getByRole("textbox", { name: "message" });

  const event = fireArrowKey(editor, "ArrowUp");
  expect(onArrowKey).toHaveBeenCalledWith("up", expect.any(HTMLElement));
  expect(event.defaultPrevented).toBe(true);
});
