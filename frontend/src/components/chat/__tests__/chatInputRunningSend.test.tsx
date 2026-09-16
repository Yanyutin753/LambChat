/** @vitest-environment jsdom */

import { beforeEach, expect, test, vi } from "vitest";

import {
  createRunningDraftSender,
  createRunningSendToolkit,
  handleEnterSubmit,
} from "../chatInputRunningSend";
import type { MessageAttachment } from "../../../types";

test("editing a queued message restores its attachments as visible draft cards", () => {
  const file: MessageAttachment = {
    id: "f1",
    key: "f1",
    name: "report.pdf",
    type: "document",
    mimeType: "application/pdf",
    size: 10,
    composerReferenceId: "old-node",
  };
  const restoreAttachments = vi.fn();
  const removeQueued = vi.fn();
  const toolkit = createRunningSendToolkit({
    input: "",
    visibleAttachments: [],
    clearDraft: vi.fn(),
    setComposerText: vi.fn(),
    focusComposer: vi.fn(),
    removeQueued,
    restoreAttachments,
  });
  toolkit.editQueuedMessage("", "q1", [file]);
  expect(restoreAttachments).toHaveBeenCalledWith([
    { ...file, composerReferenceId: undefined },
  ]);
  expect(removeQueued).toHaveBeenCalledWith("", "q1");
});

type TestEvent = {
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  preventDefault: ReturnType<typeof vi.fn>;
};

const enterEvent = (overrides: Partial<TestEvent> = {}): TestEvent => ({
  altKey: false,
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  preventDefault: vi.fn(),
  ...overrides,
});

const runningState = (overrides: Record<string, unknown> = {}) => ({
  isLoading: true,
  sendBlocked: false,
  input: "hello",
  visibleAttachments: [],
  hasUploadingAttachment: false,
  hasFailedAttachment: false,
  hasInvalidAttachment: false,
  ...overrides,
});

const actions = () => ({
  clearDraft: vi.fn(),
  openStopConfirm: vi.fn(),
  submitForm: vi.fn(),
});

beforeEach(() => {
  localStorage.clear();
});

test.each([
  ["ctrl", { ctrlKey: true }],
  ["shift", { shiftKey: true }],
  ["enter", {}],
] as const)(
  "%s send preference queues without guiding",
  (preference, modifiers) => {
    localStorage.setItem("newlineModifier", preference);
    const onQueueFollowUp = vi.fn();
    const onSupplement = vi.fn();
    const act = actions();
    handleEnterSubmit(
      enterEvent(modifiers) as never,
      runningState(),
      { onQueueFollowUp, onSupplement },
      act,
    );
    expect(onQueueFollowUp).toHaveBeenCalledExactlyOnceWith("hello", []);
    expect(onSupplement).not.toHaveBeenCalled();
    expect(act.clearDraft).toHaveBeenCalledOnce();
  },
);

test("Alt+Enter does not override the configured send key", () => {
  const onSupplement = vi.fn();
  const onQueueFollowUp = vi.fn();
  const act = actions();

  handleEnterSubmit(
    enterEvent({ altKey: true }) as never,
    runningState(),
    { onSupplement, onQueueFollowUp },
    act,
  );

  expect(onQueueFollowUp).not.toHaveBeenCalled();
  expect(onSupplement).not.toHaveBeenCalled();
  expect(act.clearDraft).not.toHaveBeenCalled();
  expect(act.openStopConfirm).not.toHaveBeenCalled();
});

test("the send key while running queues a follow-up", () => {
  const onSupplement = vi.fn();
  const onQueueFollowUp = vi.fn();
  const act = actions();

  handleEnterSubmit(
    enterEvent({ ctrlKey: true }) as never,
    runningState(),
    { onSupplement, onQueueFollowUp },
    act,
  );

  expect(onQueueFollowUp).toHaveBeenCalledWith("hello", []);
  expect(onSupplement).not.toHaveBeenCalled();
});

test("Alt held together with Ctrl preserves the configured send behavior and queues", () => {
  const onSupplement = vi.fn();
  const onQueueFollowUp = vi.fn();

  handleEnterSubmit(
    enterEvent({ altKey: true, ctrlKey: true }) as never,
    runningState(),
    { onSupplement, onQueueFollowUp },
    actions(),
  );

  expect(onQueueFollowUp).toHaveBeenCalledWith("hello", []);
  expect(onSupplement).not.toHaveBeenCalled();
});

test("Alt+Enter with an unsendable draft does not hijack the key", () => {
  const onSupplement = vi.fn();
  const onQueueFollowUp = vi.fn();
  const act = actions();
  const event = enterEvent({ altKey: true });

  handleEnterSubmit(
    event as never,
    runningState({ hasUploadingAttachment: true }),
    { onSupplement, onQueueFollowUp },
    act,
  );

  expect(event.preventDefault).not.toHaveBeenCalled();
  expect(onSupplement).not.toHaveBeenCalled();
  expect(onQueueFollowUp).not.toHaveBeenCalled();
  expect(act.openStopConfirm).not.toHaveBeenCalled();
});

test("sendBlocked suppresses supplementing and queueing entirely", () => {
  const onSupplement = vi.fn();
  const onQueueFollowUp = vi.fn();
  const act = actions();

  handleEnterSubmit(
    enterEvent({ altKey: true }) as never,
    runningState({ sendBlocked: true }),
    { onSupplement, onQueueFollowUp },
    act,
  );

  expect(onQueueFollowUp).not.toHaveBeenCalled();
  expect(onSupplement).not.toHaveBeenCalled();
  expect(act.openStopConfirm).not.toHaveBeenCalled();
});

test("idle Enter submits the form", () => {
  const onSupplement = vi.fn();
  const act = actions();

  handleEnterSubmit(
    enterEvent({ ctrlKey: true }) as never,
    runningState({ isLoading: false }),
    { onSupplement },
    act,
  );

  expect(act.submitForm).toHaveBeenCalled();
  expect(onSupplement).not.toHaveBeenCalled();
});

test("running Enter without a sendable draft opens the stop confirmation", () => {
  const onSupplement = vi.fn();
  const act = actions();

  handleEnterSubmit(
    enterEvent({ ctrlKey: true }) as never,
    runningState({ input: "  " }),
    { onSupplement },
    act,
  );

  expect(act.openStopConfirm).toHaveBeenCalled();
  expect(onSupplement).not.toHaveBeenCalled();
});

test("createRunningDraftSender sends the draft then clears it", () => {
  const send = vi.fn();
  const clearDraft = vi.fn();

  const sender = createRunningDraftSender("hello", [], clearDraft);
  const handler = sender(send);
  handler?.();

  expect(send).toHaveBeenCalledWith("hello", []);
  expect(clearDraft).toHaveBeenCalled();
  expect(sender(undefined)).toBeUndefined();
});
