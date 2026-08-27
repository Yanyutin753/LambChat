/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import type { MessageAttachment, SkillResponse } from "../../../types";
import { SELECTION_ACTION_EVENT } from "../../common/selectionActionPopoverUtils";

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

const availableSkills: SkillResponse[] = ["writer", "reviewer"].map((name) => ({
  name,
  description: `${name} skill`,
  tags: [],
  enabled: true,
  source: "manual",
  files: {},
  file_count: 0,
  installed_from: "manual",
  is_published: false,
  marketplace_is_active: false,
}));

async function insertSkill(
  user: ReturnType<typeof userEvent.setup>,
  editor: HTMLElement,
  name: string,
): Promise<void> {
  await user.click(editor);
  await user.type(editor, ` /${name}`);
  fireEvent.mouseDown(screen.getByRole("option", { name }));
}

function insertPendingText(text: string): void {
  act(() => {
    window.dispatchEvent(
      new CustomEvent(SELECTION_ACTION_EVENT, { detail: { prompt: text } }),
    );
  });
}

test("a rejected submission restores its exact outbox before pending draft edits", async () => {
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
          pendingInput="keep this exact draft"
          attachments={attachments}
          onAttachmentsChange={setAttachments}
        />
      </>
    );
  }

  render(<DraftHarness />);

  const editor = await screen.findByRole("textbox");
  expect(editor.textContent).toBe("keep this exact draft");
  fireEvent.submit(editor.closest("form")!);

  expect(onSend).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(editor.textContent).toBe(""));
  expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();

  insertPendingText("pending edit");
  expect(editor).toHaveTextContent("pending edit");
  await user.click(
    screen.getByRole("button", { name: "Add pending attachment" }),
  );

  const submissionCallbacks = onSend.mock.calls[0]?.[4] as
    | { onAccepted: () => void; onRejected: () => void }
    | undefined;
  expect(submissionCallbacks?.onAccepted).toEqual(expect.any(Function));
  expect(submissionCallbacks?.onRejected).toEqual(expect.any(Function));

  act(() => submissionCallbacks?.onRejected());

  expect(editor).toHaveTextContent("keep this exact draft");
  expect(editor).toHaveTextContent("pending edit");
  expect(screen.getByText("report.pdf")).toBeVisible();
  expect(screen.getByText("pending-notes.pdf")).toBeVisible();

  fireEvent.submit(editor.closest("form")!);
  expect(onSend.mock.calls[1]?.[0]).toContain("keep this exact draft");
  expect(onSend.mock.calls[1]?.[0]).toContain("pending edit");
  expect(onSend.mock.calls[1]?.[2]).toEqual([
    uploadedAttachment,
    pendingAttachment,
  ]);
});

test("acceptance leaves only the pending text, attachments, and skills for the next submit", async () => {
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
          skills={availableSkills}
        />
      </>
    );
  }

  render(<DraftHarness />);

  const editor = await screen.findByRole("textbox");
  await insertSkill(user, editor, "writer");
  fireEvent.submit(editor.closest("form")!);
  expect(onSend).toHaveBeenCalledTimes(1);
  expect(onSend.mock.calls[0]?.[3]).toEqual({ enabledSkills: ["writer"] });
  await waitFor(() => expect(editor.textContent).toBe(""));
  expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();

  insertPendingText("pending edit");
  insertPendingText("/reviewer");
  fireEvent.mouseDown(screen.getByRole("option", { name: "reviewer" }));
  await user.click(
    screen.getByRole("button", { name: "Add pending attachment" }),
  );
  expect(editor).toHaveTextContent("pending edit");
  expect(screen.getByText("pending-notes.pdf")).toBeVisible();

  const submissionCallbacks = onSend.mock.calls[0]?.[4] as {
    onAccepted: () => void;
  };
  act(() => submissionCallbacks.onAccepted());

  expect(editor).toHaveTextContent("pending edit");
  expect(screen.getByText("pending-notes.pdf")).toBeVisible();

  fireEvent.submit(editor.closest("form")!);
  expect(onSend.mock.calls[1]?.[0]).toBe("pending edit");
  expect(onSend.mock.calls[1]?.[2]).toEqual([pendingAttachment]);
  expect(onSend.mock.calls[1]?.[3]).toEqual({ enabledSkills: ["reviewer"] });
});

test("acceptance preserves a pending replacement that reuses a submitted attachment id", async () => {
  const onSend = vi.fn();

  function DraftHarness() {
    const [attachments, setAttachments] = useState([uploadedAttachment]);
    return (
      <>
        <button
          type="button"
          onClick={() =>
            setAttachments((previous) => [
              ...previous,
              { ...uploadedAttachment, name: "renamed-report.pdf" },
            ])
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
  expect(editor.textContent).toBe("");
});
