/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
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

async function sendDraft(modifier: "ctrl" | "shift") {
  const onSend = vi.fn();
  render(
    <ChatInput
      onSend={onSend}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput="hello"
    />,
  );

  const editor = await screen.findByRole("textbox");
  expect(editor).toHaveTextContent("hello");
  editor.focus();
  expect(editor).toHaveFocus();
  fireEvent.keyDown(editor, {
    key: "Enter",
    code: "Enter",
    ctrlKey: modifier === "ctrl",
    shiftKey: modifier === "shift",
  });

  return onSend;
}

test("Ctrl+Enter sends the current rich-composer message by default", async () => {
  const onSend = await sendDraft("ctrl");

  expect(onSend).toHaveBeenCalledWith("hello", {}, [], undefined);
});

test("Shift+Enter sends after selecting the Shift shortcut", async () => {
  localStorage.setItem("newlineModifier", "shift");

  const onSend = await sendDraft("shift");

  expect(onSend).toHaveBeenCalledWith("hello", {}, [], undefined);
});
