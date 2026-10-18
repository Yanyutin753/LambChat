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

vi.mock("../ChatInputSelectors", () => ({
  ChatInputSelectors: () => null,
}));

vi.mock("../SessionWorkspaceBar", () => ({
  SessionWorkspaceBar: () => (
    <div data-testid="workspace-header">Project directory</div>
  ),
}));

import { ChatInput } from "../ChatInput";
import { ModalSurface } from "../../common/ModalSurface";

beforeEach(() => {
  localStorage.clear();
});

const longDraft = "hello expanded composer ".repeat(10);

test.each([{ isComposing: true }, { keyCode: 229 }])(
  "cancelling IME composition keeps the expanded composer open (%j)",
  async (composition) => {
    render(
      <ChatInput
        onSend={vi.fn()}
        onStop={vi.fn()}
        isLoading={false}
        pendingInput={longDraft}
      />,
    );
    const editor = await screen.findByRole("textbox");
    fireEvent.click(
      screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
    );
    fireEvent.keyDown(editor, { key: "Escape", ...composition });
    expect(document.querySelector("[data-composer-expanded]")).not.toBeNull();
    fireEvent.keyDown(editor, { key: "Escape" });
    expect(document.querySelector("[data-composer-expanded]")).toBeNull();
  },
);

test("directory header shares the composer boundary and follows expand and collapse", async () => {
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput={longDraft}
    />,
  );
  const editor = await screen.findByRole("textbox");
  const header = screen.getByTestId("workspace-header");
  const container = editor.closest(".chat-input-container");
  expect(header.parentElement).toBe(container);
  expect(
    header.compareDocumentPosition(editor) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
    );
  });
  expect(header.parentElement).toBe(container);
  expect(header.closest(".chat-input-shell")).toBeNull();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /(collapse|收起)/i }));
  });
  expect(header.closest("form")).not.toBeNull();
  expect(editor.isConnected).toBe(true);
});

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
      screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
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
  expect(expandedContainer?.closest("form")).not.toBeNull();
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
      screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
    );
  });
  expect(
    document.querySelector(".chat-input-container[data-composer-expanded]"),
  ).not.toBeNull();

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /(collapse|收起)/i }));
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
      screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
    );
  });
  editor.focus();
  await act(async () => {
    fireEvent.keyDown(editor, { key: "Enter", code: "Enter", ctrlKey: true });
  });

  expect(onSend).toHaveBeenCalled();
});

test("Escape closes the foreground modal and keeps the expanded draft in place", async () => {
  const close = vi.fn();
  const view = (modal: boolean) => (
    <div id="root">
      <ChatInput
        onSend={vi.fn()}
        onStop={vi.fn()}
        isLoading={false}
        pendingInput={longDraft}
      />
      <ModalSurface open={modal} onClose={close} label="Search">
        <input aria-label="Search" />
      </ModalSurface>
    </div>
  );
  const { rerender } = render(view(false));
  await screen.findByRole("textbox");
  fireEvent.click(
    screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
  );
  rerender(view(true));
  expect(
    (document.querySelector("body > [data-chat-composer-host]") as HTMLElement)
      .inert,
  ).toBe(true);
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Search" }), {
    key: "Escape",
  });
  expect(close).toHaveBeenCalledOnce();
  expect(document.querySelector("[data-composer-expanded]")).not.toBeNull();
  rerender(view(false));
  expect(
    (document.querySelector("body > [data-chat-composer-host]") as HTMLElement)
      .inert,
  ).toBe(false);
});

test.each([false, true])(
  "clicking Send submits the draft (expanded=%s)",
  async (expanded) => {
    const onSend = vi.fn();
    render(
      <ChatInput
        onSend={onSend}
        onStop={vi.fn()}
        isLoading={false}
        pendingInput={longDraft}
      />,
    );
    await screen.findByRole("textbox");
    if (expanded)
      fireEvent.click(
        screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
      );
    const send = screen.getByRole("button", {
      name: /^(send message|发送|chat.send)$/i,
    });
    fireEvent.click(send);
    expect(onSend).toHaveBeenCalledOnce();
    expect(onSend.mock.calls[0][0]).toBe(longDraft.trim());
  },
);

test("rejected expanded submission restores the complete multilingual draft", async () => {
  const draft = "中文输入，emoji 🐑\n第二行 English <tag> & code";
  const onSend = vi.fn();
  render(
    <ChatInput
      onSend={onSend}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput={draft}
    />,
  );
  const editor = await screen.findByRole("textbox");
  fireEvent.click(
    screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
  );
  fireEvent.click(screen.getByRole("button", { name: /send message/i }));
  expect(onSend.mock.calls[0][0]).toBe(draft);
  await act(async () => onSend.mock.calls[0][4].onRejected());
  expect(editor.textContent).toContain("中文输入，emoji 🐑");
  expect(editor.textContent).toContain("第二行 English <tag> & code");
  fireEvent.click(screen.getByRole("button", { name: /send message/i }));
  expect(onSend.mock.calls[1][0]).toBe(draft);
});

test.each([{ isComposing: true }, { keyCode: 229 }])(
  "confirming IME text in expanded mode does not submit (%j)",
  async (composition) => {
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
    fireEvent.click(
      screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
    );
    editor.focus();
    fireEvent.keyDown(editor, { key: "Enter", ctrlKey: true, ...composition });
    expect(onSend).not.toHaveBeenCalled();
    expect(editor).toHaveTextContent(longDraft.trim());
  },
);

test("the Goal header follows the expanded editor and returns above the composer", async () => {
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput={longDraft}
      persistentGoal={{
        id: "g",
        session_id: "s",
        user_id: "u",
        objective: "Goal stays visible",
        rubric: "verified",
        version: 1,
        revision: 1,
        status: "active",
        accounting: { turns: 0, tokens: 0 },
        started_at: null,
        current_run_id: "r",
      }}
    />,
  );
  const editor = await screen.findByRole("textbox");
  expect(
    screen.getByText("Goal stays visible").closest(".chat-input-container"),
  ).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: /^(Expand editor|展开编辑)$/i }),
  );
  expect(
    screen.getByText("Goal stays visible").closest("[data-composer-expanded]"),
  ).toBeTruthy();
  fireEvent.keyDown(editor, { key: "Escape" });
  expect(
    screen.getByText("Goal stays visible").closest(".chat-input-container"),
  ).toBeNull();
});
