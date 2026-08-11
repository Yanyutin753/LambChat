/** @vitest-environment jsdom */

import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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

const pendingAttachment: MessageAttachment = {
  ...uploadedAttachment,
  id: "attachment-2",
  key: "uploads/pending-notes.pdf",
  name: "pending-notes.pdf",
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
  const update = onAttachmentsChange.mock.calls[0]?.[0] as (
    previous: MessageAttachment[],
  ) => MessageAttachment[];
  expect(update([uploadedAttachment])).toEqual([]);
});

test("acceptance preserves text edits and new attachments made while POST is pending", async () => {
  const user = userEvent.setup();
  const onSend = vi.fn();

  function DraftHarness() {
    const [attachments, setAttachments] = useState([uploadedAttachment]);
    return (
      <>
        <button
          type="button"
          onClick={() =>
            setAttachments((previous) => [...previous, pendingAttachment])
          }
        >
          Add pending attachment
        </button>
        <ChatInput
          onSend={onSend}
          onStop={vi.fn()}
          isLoading={false}
          pendingInput="submitted draft"
          attachments={attachments}
          onAttachmentsChange={setAttachments}
        />
      </>
    );
  }

  render(<DraftHarness />);

  const editor = await screen.findByRole("textbox");
  fireEvent.submit(editor.closest("form")!);
  expect(onSend).toHaveBeenCalledTimes(1);

  await user.click(editor);
  await user.type(editor, " with pending edit");
  await user.click(
    screen.getByRole("button", { name: "Add pending attachment" }),
  );
  expect(editor).toHaveTextContent("submitted draft with pending edit");
  expect(screen.getByText("report.pdf")).toBeVisible();
  expect(screen.getByText("pending-notes.pdf")).toBeVisible();

  const submissionCallbacks = onSend.mock.calls[0]?.[4] as {
    onAccepted: () => void;
  };
  act(() => submissionCallbacks.onAccepted());

  expect(editor).toHaveTextContent("submitted draft with pending edit");
  expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();
  expect(screen.getByText("pending-notes.pdf")).toBeVisible();

  fireEvent.submit(editor.closest("form")!);
  expect(onSend.mock.calls[1]?.[2]).toEqual([pendingAttachment]);
});

test("acceptance preserves a submitted attachment that the user modified while pending", async () => {
  const onSend = vi.fn();

  function DraftHarness() {
    const [attachments, setAttachments] = useState([uploadedAttachment]);
    return (
      <>
        <button
          type="button"
          onClick={() =>
            setAttachments((previous) =>
              previous.map((attachment) =>
                attachment.id === uploadedAttachment.id
                  ? { ...attachment, name: "renamed-report.pdf" }
                  : attachment,
              ),
            )
          }
        >
          Rename attachment
        </button>
        <ChatInput
          onSend={onSend}
          onStop={vi.fn()}
          isLoading={false}
          pendingInput="submitted text"
          attachments={attachments}
          onAttachmentsChange={setAttachments}
        />
      </>
    );
  }

  render(<DraftHarness />);
  const editor = await screen.findByRole("textbox");
  fireEvent.submit(editor.closest("form")!);
  fireEvent.click(screen.getByRole("button", { name: "Rename attachment" }));

  const submissionCallbacks = onSend.mock.calls[0]?.[4] as {
    onAccepted: () => void;
  };
  act(() => submissionCallbacks.onAccepted());

  expect(screen.getByText("renamed-report.pdf")).toBeVisible();
  expect(editor).toHaveTextContent("");
});
