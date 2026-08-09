/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

vi.mock("../../../hooks/useFileUpload", () => ({
  useFileUpload: () => ({
    uploadFiles: vi.fn(),
    uploadFile: vi.fn(),
    uploadLimits: null,
    validateCount: () => true,
    cancelUpload: vi.fn(),
  }),
}));

vi.mock("../ChatInputToolbar", () => ({
  ChatInputToolbar: () => null,
}));

vi.mock("../ChatInputSelectors", () => ({
  ChatInputSelectors: () => null,
}));

import { ChatInput } from "../ChatInput";

beforeEach(() => {
  localStorage.clear();
});

function fireLexicalArrow(editor: HTMLElement, key: "ArrowUp" | "ArrowDown") {
  const event = new KeyboardEvent("keydown", {
    key,
    code: key,
    bubbles: true,
    cancelable: true,
  });
  event.preventDefault();
  fireEvent(editor, event);
}

function moveCaretToEnd(editor: HTMLElement) {
  const range = document.createRange();
  range.selectNodeContents(editor);
  range.collapse(false);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

test("ArrowUp and ArrowDown browse input history and restore the draft", async () => {
  localStorage.setItem("chatInputHistory", JSON.stringify(["first", "second"]));
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput="draft"
    />,
  );

  const editor = await screen.findByRole("textbox");
  await waitFor(() => expect(editor).toHaveTextContent("draft"));
  editor.focus();
  moveCaretToEnd(editor);
  const lexicalKeyDown = vi.fn();
  editor.addEventListener("keydown", lexicalKeyDown);

  fireLexicalArrow(editor, "ArrowUp");
  await waitFor(() => expect(editor).toHaveTextContent("second"));
  expect(lexicalKeyDown).not.toHaveBeenCalled();

  fireLexicalArrow(editor, "ArrowUp");
  await waitFor(() => expect(editor).toHaveTextContent("first"));

  fireLexicalArrow(editor, "ArrowDown");
  await waitFor(() => expect(editor).toHaveTextContent("second"));

  fireLexicalArrow(editor, "ArrowDown");
  await waitFor(() => expect(editor).toHaveTextContent("draft"));
});

test("a sent message remains available after the chat input remounts", async () => {
  const onSend = vi.fn(() => {
    expect(localStorage.getItem("chatInputHistory")).toBe('["persisted"]');
  });
  const first = render(
    <ChatInput
      onSend={onSend}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput="persisted"
    />,
  );
  const firstEditor = await screen.findByRole("textbox");
  await waitFor(() => expect(firstEditor).toHaveTextContent("persisted"));
  firstEditor.focus();
  fireEvent.keyDown(firstEditor, {
    key: "Enter",
    code: "Enter",
    ctrlKey: true,
  });
  await waitFor(() =>
    expect(localStorage.getItem("chatInputHistory")).toBe('["persisted"]'),
  );
  first.unmount();

  render(<ChatInput onSend={vi.fn()} onStop={vi.fn()} isLoading={false} />);
  const nextEditor = await screen.findByRole("textbox");
  nextEditor.focus();
  nextEditor.addEventListener("keydown", (event) => event.stopPropagation());
  fireLexicalArrow(nextEditor, "ArrowUp");

  await waitFor(() => expect(nextEditor).toHaveTextContent("persisted"));
});
