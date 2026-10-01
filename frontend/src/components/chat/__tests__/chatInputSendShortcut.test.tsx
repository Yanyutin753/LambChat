/** @vitest-environment jsdom */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

vi.mock("../../../hooks/useMentionSearch", () => ({
  useMentionSearch: () => ({
    presets: [{ id: "ada", name: "Ada", tags: [] }],
    isLoading: false,
  }),
}));

import { ChatInput } from "../ChatInput";

beforeEach(() => {
  localStorage.clear();
});

test.each([{ isComposing: true }, { keyCode: 229 }])(
  "confirming IME text does not select a mention or discard the draft (%j)",
  async (composition) => {
    const select = vi.fn();
    const props = {
      onSend: vi.fn(),
      onStop: vi.fn(),
      isLoading: false,
      onUsePersonaPreset: select,
      onMentionQueryChange: vi.fn(),
    };
    const { rerender } = render(<ChatInput {...props} />);
    const editor = await screen.findByRole("textbox");
    rerender(<ChatInput {...props} pendingInput="@Ada" />);
    editor.focus();
    await waitFor(() =>
      expect(editor.closest("[data-mention-active]")).not.toBeNull(),
    );
    fireEvent.keyDown(editor, { key: "Enter", ...composition });
    expect(select).not.toHaveBeenCalled();
    expect(editor).toHaveTextContent("@Ada");
    fireEvent.keyDown(editor, { key: "Enter" });
    expect(select).toHaveBeenCalledOnce();
  },
);

test("Escape dismisses mention suggestions while preserving the draft", async () => {
  const props = {
    onSend: vi.fn(),
    onStop: vi.fn(),
    isLoading: false,
    onUsePersonaPreset: vi.fn(),
    onMentionQueryChange: vi.fn(),
  };
  const { rerender } = render(<ChatInput {...props} />);
  const editor = await screen.findByRole("textbox");
  rerender(<ChatInput {...props} pendingInput="@Ada" />);
  editor.focus();
  await waitFor(() =>
    expect(editor.closest("[data-mention-active]")).not.toBeNull(),
  );
  fireEvent.keyDown(editor, { key: "Escape", isComposing: true });
  expect(editor.closest("[data-mention-active]")).not.toBeNull();
  fireEvent.keyDown(editor, { key: "Escape" });
  expect(editor.closest("[data-mention-active]")).toBeNull();
  expect(editor).toHaveTextContent("@Ada");
});

async function sendDraft(modifier: "ctrl" | "shift" | "enter") {
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
  await act(async () => {
    fireEvent.keyDown(editor, {
      key: "Enter",
      code: "Enter",
      ctrlKey: modifier === "ctrl",
      shiftKey: modifier === "shift",
    });
  });

  return onSend;
}

test("Ctrl+Enter sends the current rich-composer message by default", async () => {
  const onSend = await sendDraft("ctrl");

  expect(onSend.mock.calls[0]?.slice(0, 4)).toEqual([
    "hello",
    {},
    [],
    undefined,
  ]);
  expect(onSend.mock.calls[0]?.[4]).toEqual(
    expect.objectContaining({ onAccepted: expect.any(Function) }),
  );
});

test("Enter sends when the Enter shortcut is selected", async () => {
  localStorage.setItem("newlineModifier", "enter");

  const onSend = await sendDraft("enter");

  expect(onSend.mock.calls[0]?.slice(0, 4)).toEqual([
    "hello",
    {},
    [],
    undefined,
  ]);
});

test("Shift+Enter sends after selecting the Shift shortcut", async () => {
  localStorage.setItem("newlineModifier", "shift");

  const onSend = await sendDraft("shift");

  expect(onSend.mock.calls[0]?.slice(0, 4)).toEqual([
    "hello",
    {},
    [],
    undefined,
  ]);
  expect(onSend.mock.calls[0]?.[4]).toEqual(
    expect.objectContaining({ onAccepted: expect.any(Function) }),
  );
});
