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
import i18n from "../../../i18n";

beforeEach(() => {
  localStorage.clear();
});

function renderRunningInput() {
  const onSend = vi.fn();
  const onQueueFollowUp = vi.fn();
  const onSupplement = vi.fn();
  render(
    <ChatInput
      onSend={onSend}
      onStop={vi.fn()}
      onQueueFollowUp={onQueueFollowUp}
      onSupplement={onSupplement}
      isLoading={true}
      pendingInput="hello"
    />,
  );
  return { onSend, onQueueFollowUp, onSupplement };
}

test("Alt+Enter leaves the draft intact when Ctrl+Enter is the send key", async () => {
  const { onSend, onQueueFollowUp, onSupplement } = renderRunningInput();

  const editor = await screen.findByRole("textbox");
  editor.focus();
  await act(async () => {
    fireEvent.keyDown(editor, { key: "Enter", code: "Enter", altKey: true });
  });

  expect(onQueueFollowUp).not.toHaveBeenCalled();
  expect(onSend).not.toHaveBeenCalled();
  expect(onSupplement).not.toHaveBeenCalled();
  expect(editor).toHaveTextContent("hello");
});

test("Ctrl+Alt+Enter during a running session queues a follow-up", async () => {
  const { onSend, onQueueFollowUp, onSupplement } = renderRunningInput();

  const editor = await screen.findByRole("textbox");
  editor.focus();
  await act(async () => {
    fireEvent.keyDown(editor, {
      key: "Enter",
      code: "Enter",
      altKey: true,
      ctrlKey: true,
    });
  });

  expect(onQueueFollowUp).toHaveBeenCalledExactlyOnceWith("hello", []);
  expect(onSupplement).not.toHaveBeenCalled();
  expect(onSend).not.toHaveBeenCalled();
  expect(editor).not.toHaveTextContent("hello");
});

test("Alt+ArrowUp does not edit queued messages", async () => {
  const onCancelSteer = vi.fn();
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={true}
      onCancelSteer={onCancelSteer}
      steerMessages={[
        {
          id: "q1",
          content: "第一条追加",
          queued: true,
          status: "deferred",
          deferred: true,
          timestamp: new Date(1),
        },
        {
          id: "q2",
          content: "第二条追加",
          queued: true,
          status: "deferred",
          deferred: true,
          timestamp: new Date(2),
        },
      ]}
    />,
  );

  const editor = await screen.findByRole("textbox");
  editor.focus();
  await act(async () => {
    fireEvent.keyDown(editor, {
      key: "ArrowUp",
      code: "ArrowUp",
      altKey: true,
    });
  });

  expect(editor).not.toHaveTextContent("第二条追加");
  expect(onCancelSteer).not.toHaveBeenCalled();
});

test("queue chip edit button loads that message into the composer", async () => {
  const onCancelSteer = vi.fn();
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={true}
      onCancelSteer={onCancelSteer}
      steerMessages={[
        {
          id: "q1",
          content: "要改的追加",
          queued: true,
          status: "deferred",
          deferred: true,
          timestamp: new Date(1),
        },
      ]}
    />,
  );

  const editor = await screen.findByRole("textbox");
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("chat.queueMore") }),
  );
  fireEvent.click(screen.getByTestId("queue-edit-trigger"));

  expect(editor).toHaveTextContent("要改的追加");
  expect(onCancelSteer).toHaveBeenCalledWith("要改的追加", "q1");
});

test("guiding a queued message preserves attachments and the current draft", async () => {
  const onCancelSteer = vi.fn();
  const onSupplement = vi.fn();
  const attachments = [
    {
      id: "a",
      key: "a",
      name: "notes.txt",
      type: "document" as const,
      mimeType: "text/plain",
      size: 12,
    },
  ];
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading
      pendingInput="unfinished draft"
      onCancelSteer={onCancelSteer}
      onSupplement={onSupplement}
      steerMessages={[
        {
          id: "q1",
          content: "Use these notes",
          attachments,
          queued: true,
          status: "deferred",
          deferred: true,
          timestamp: new Date(1),
        },
      ]}
    />,
  );
  const editor = await screen.findByRole("textbox");
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("chat.queueGuide") }),
  );
  expect(onCancelSteer).toHaveBeenCalledWith("Use these notes", "q1");
  expect(onSupplement).toHaveBeenCalledExactlyOnceWith(
    "Use these notes",
    attachments,
  );
  expect(editor).toHaveTextContent("unfinished draft");
});

test("plain Enter during a running session queues a follow-up", async () => {
  localStorage.setItem("newlineModifier", "enter");
  const { onSend, onQueueFollowUp, onSupplement } = renderRunningInput();

  const editor = await screen.findByRole("textbox");
  editor.focus();
  await act(async () => {
    fireEvent.keyDown(editor, { key: "Enter", code: "Enter" });
  });

  expect(onQueueFollowUp).toHaveBeenCalledExactlyOnceWith("hello", []);
  expect(onSupplement).not.toHaveBeenCalled();
  expect(onSend).not.toHaveBeenCalled();
});
