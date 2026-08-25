/** @vitest-environment jsdom */

import { act, fireEvent, render, screen } from "@testing-library/react";
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

const longDraft = "hello expanded composer ".repeat(10);

test("expanded composer renders at body level outside the chat shell", async () => {
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput={longDraft}
    />,
  );

  const editor = await screen.findByRole("textbox");
  const collapsedContainer = editor.closest(".chat-input-container");
  expect(collapsedContainer).not.toBeNull();
  // Collapsed: the composer participates in normal form layout.
  expect(collapsedContainer?.closest("form")).not.toBeNull();

  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: /(expand|展开编辑)/i }),
    );
  });

  const expandedContainer = document.querySelector(
    ".chat-input-container[data-composer-expanded]",
  );
  expect(expandedContainer).not.toBeNull();
  // Expanded: must escape the chat shell, where ancestor stacking contexts
  // (AppShell transform + relative z-0) cap its paint order below body-level
  // overlays such as the tool console (z-200) portal.
  expect(expandedContainer?.closest(".chat-input-shell")).toBeNull();
  expect(expandedContainer?.closest("form")).toBeNull();
  expect(expandedContainer?.closest("body")).not.toBeNull();

  // The dim backdrop must also live at body level so body-level overlays
  // cannot float above it while the page is dimmed.
  const backdrop = document.querySelector(".z-\\[279\\]");
  expect(backdrop).not.toBeNull();
  expect(backdrop?.closest(".chat-input-shell")).toBeNull();
});

test("collapsing restores the composer inside the form without remounting the editor", async () => {
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput={longDraft}
    />,
  );

  const editor = await screen.findByRole("textbox");
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: /(expand|展开编辑)/i }),
    );
  });
  expect(
    document.querySelector(".chat-input-container[data-composer-expanded]"),
  ).not.toBeNull();

  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: /(collapse|收起)/i }),
    );
  });

  const restoredContainer = document.querySelector(".chat-input-container");
  expect(restoredContainer).not.toBeNull();
  expect(restoredContainer?.closest("form")).not.toBeNull();
  // The same editor DOM node survives expand/collapse: reparenting must not
  // remount the rich composer or the draft (text, file references, undo
  // history) is lost.
  expect(editor.isConnected).toBe(true);
  expect(editor.closest("form")).not.toBeNull();
  expect(editor).toHaveTextContent(/hello/);
});

test("Enter still submits from the body-level expanded composer", async () => {
  const onSend = vi.fn();
  render(
    <ChatInput
      onSend={onSend}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput={longDraft}
    />,
  );

  const editor = await screen.findByRole("textbox");
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: /(expand|展开编辑)/i }),
    );
  });
  editor.focus();
  await act(async () => {
    fireEvent.keyDown(editor, { key: "Enter", code: "Enter", ctrlKey: true });
  });

  expect(onSend).toHaveBeenCalled();
});
