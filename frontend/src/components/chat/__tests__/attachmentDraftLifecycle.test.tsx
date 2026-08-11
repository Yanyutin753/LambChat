/** @vitest-environment jsdom */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../../types";

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

const uploadedAttachment: MessageAttachment = {
  id: "attachment-1",
  key: "uploads/report.pdf",
  name: "report.pdf",
  type: "document",
  mimeType: "application/pdf",
  size: 2048,
  url: "/api/upload/file/uploads/report.pdf",
};

test("keeps the exact draft until the server accepts attachment claims", async () => {
  const onSend = vi.fn();
  const onAttachmentsChange = vi.fn();

  render(
    <ChatInput
      onSend={onSend}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput="keep this exact draft"
      attachments={[uploadedAttachment]}
      onAttachmentsChange={onAttachmentsChange}
    />,
  );

  const editor = await screen.findByRole("textbox");
  expect(editor.textContent).toBe("keep this exact draft");
  fireEvent.submit(editor.closest("form")!);

  expect(onSend).toHaveBeenCalledTimes(1);
  expect(editor.textContent).toBe("keep this exact draft");
  expect(onAttachmentsChange).not.toHaveBeenCalled();

  const submissionCallbacks = onSend.mock.calls[0]?.[4] as
    | { onAccepted: () => void }
    | undefined;
  expect(submissionCallbacks?.onAccepted).toEqual(expect.any(Function));

  act(() => submissionCallbacks?.onAccepted());

  expect(editor.textContent).toBe("");
  expect(onAttachmentsChange).toHaveBeenCalledWith([]);
});
