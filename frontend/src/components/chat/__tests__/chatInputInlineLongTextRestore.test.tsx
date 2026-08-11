/** @vitest-environment jsdom */

import {
  act,
  createEvent,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../../types";

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

vi.mock("../../../hooks/useFileUpload", () => ({
  useFileUpload: ({
    onAttachmentsChange,
  }: {
    onAttachmentsChange: (
      update: (previous: MessageAttachment[]) => MessageAttachment[],
    ) => void;
  }) => ({
    uploadFiles: vi.fn(),
    uploadFile: (
      file: File,
      category: string,
      clientMeta: Partial<MessageAttachment>,
    ) => {
      void category;
      queueMicrotask(() =>
        onAttachmentsChange((previous) => [
          ...previous,
          {
            id: clientMeta.composerReferenceId ?? file.name,
            key: `uploads/${clientMeta.composerReferenceId ?? file.name}`,
            name: file.name,
            type: "document",
            mimeType: file.type,
            size: file.size,
            ...clientMeta,
          },
        ]),
      );
    },
    uploadLimits: null,
    validateCount: () => true,
    cancelUpload: vi.fn(),
  }),
}));

vi.mock("../ChatInputToolbar", () => ({ ChatInputToolbar: () => null }));
vi.mock("../ChatInputSelectors", () => ({ ChatInputSelectors: () => null }));

import { ChatInput } from "../ChatInput";

function pasteText(editor: HTMLElement, text: string): void {
  const paste = createEvent.paste(editor, {
    clipboardData: {
      files: [],
      getData: (type: string) => (type === "text/plain" ? text : ""),
    },
  });
  fireEvent(editor, paste);
}

test("the outbox removes submitted inline text and acceptance preserves a new inline resource", async () => {
  const onSend = vi.fn();
  render(
    <ChatInput onSend={onSend} onStop={vi.fn()} isLoading={false} />,
  );
  const editor = await screen.findByRole("textbox");
  const submittedText = `submitted inline ${"x".repeat(3100)}`;
  const pendingText = `pending inline ${"y".repeat(3100)}`;
  pasteText(editor, submittedText);

  await waitFor(() =>
    expect(
      screen.getAllByRole("button", { name: /send as text instead/i }),
    ).toHaveLength(1),
  );
  fireEvent.submit(editor.closest("form")!);
  expect(onSend).toHaveBeenCalledOnce();
  await waitFor(() =>
    expect(
      screen.queryAllByRole("button", { name: /send as text instead/i }),
    ).toHaveLength(0),
  );

  pasteText(editor, pendingText);
  await waitFor(() =>
    expect(
      screen.getAllByRole("button", { name: /send as text instead/i }),
    ).toHaveLength(1),
  );

  const submissionCallbacks = onSend.mock.calls[0]?.[4] as {
    onAccepted: () => void;
  };
  act(() => submissionCallbacks.onAccepted());

  await waitFor(() =>
    expect(
      screen.getAllByRole("button", { name: /send as text instead/i }),
    ).toHaveLength(1),
  );
  const restore = screen.getByRole("button", {
    name: /send as text instead/i,
  });
  fireEvent.click(restore);

  expect(editor).toHaveTextContent(pendingText);
  expect(
    screen.queryByRole("button", {
      name: /send as text instead/i,
    }),
  ).not.toBeInTheDocument();
});
