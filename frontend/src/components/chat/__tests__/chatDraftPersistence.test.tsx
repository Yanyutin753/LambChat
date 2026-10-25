/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ChatInput } from "../ChatInput";
import { createRef } from "react";
import {
  RichChatComposer,
  type RichChatComposerHandle,
} from "../richComposer/RichChatComposer";
import { readChatDraft, updateChatDraft } from "../chatDraftStore";
import type { MessageAttachment } from "../../../types";
const uploadFile = vi.hoisted(() => vi.fn());

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../../hooks/useFileUpload", () => ({
  useFileUpload: () => ({
    uploadFiles: vi.fn(),
    uploadFile,
    uploadLimits: null,
    validateCount: () => true,
    cancelUpload: vi.fn(),
  }),
}));
vi.mock("../ChatInputToolbar", () => ({ ChatInputToolbar: () => null }));
vi.mock("../ChatInputSelectors", () => ({ ChatInputSelectors: () => null }));

const props = { onSend: vi.fn(), onStop: vi.fn(), isLoading: false };

test("leaving and returning restores each conversation's own unsent draft", async () => {
  const view = render(
    <ChatInput
      {...props}
      key="a"
      draftKey="draft-switch-a"
      pendingInput="未发出的内容"
    />,
  );
  expect(screen.getByRole("textbox")).toHaveTextContent("未发出的内容");
  view.rerender(<ChatInput {...props} key="b" draftKey="draft-switch-b" />);
  expect(screen.getByRole("textbox")).toHaveTextContent("");
  view.rerender(
    <ChatInput
      {...props}
      key="b"
      draftKey="draft-switch-b"
      pendingInput="另一个对话"
    />,
  );
  view.rerender(<ChatInput {...props} key="a" draftKey="draft-switch-a" />);
  await waitFor(() =>
    expect(screen.getByRole("textbox")).toHaveTextContent("未发出的内容"),
  );
  view.rerender(<ChatInput {...props} key="b" draftKey="draft-switch-b" />);
  await waitFor(() =>
    expect(screen.getByRole("textbox")).toHaveTextContent("另一个对话"),
  );
});

test("accepted text stays cleared after remount; rejected text returns to its original conversation", async () => {
  const onSend = vi.fn();
  const view = render(
    <ChatInput
      {...props}
      onSend={onSend}
      draftKey="draft-reject-a"
      pendingInput="不要丢失"
    />,
  );
  fireEvent.submit(screen.getByRole("textbox").closest("form")!);
  expect(onSend).toHaveBeenCalledTimes(1);
  view.unmount();
  const other = render(
    <ChatInput {...props} draftKey="draft-reject-b" pendingInput="新草稿" />,
  );
  act(() => onSend.mock.calls[0][4].onRejected());
  expect(screen.getByRole("textbox")).toHaveTextContent("新草稿");
  other.unmount();
  const restored = render(
    <ChatInput {...props} onSend={onSend} draftKey="draft-reject-a" />,
  );
  await waitFor(() =>
    expect(screen.getByRole("textbox")).toHaveTextContent("不要丢失"),
  );
  fireEvent.submit(screen.getByRole("textbox").closest("form")!);
  act(() => onSend.mock.calls[1][4].onAccepted());
  restored.unmount();
  render(<ChatInput {...props} draftKey="draft-reject-a" />);
  expect(screen.getByRole("textbox").textContent).toBe("");
});

test("a late rejection restores the original draft before new edits after returning", async () => {
  const onSend = vi.fn();
  const first = render(
    <ChatInput
      {...props}
      onSend={onSend}
      draftKey="late-return"
      pendingInput="原稿"
    />,
  );
  fireEvent.submit(screen.getByRole("textbox").closest("form")!);
  first.unmount();
  render(<ChatInput {...props} draftKey="late-return" pendingInput="新写的" />);
  act(() => onSend.mock.calls[0][4].onRejected());
  await waitFor(() =>
    expect(screen.getByRole("textbox")).toHaveTextContent("原稿新写的"),
  );
});

test("a fresh page restores multiline text, rich references and completed attachments from storage", async () => {
  const handle = createRef<RichChatComposerHandle>();
  const editor = render(<RichChatComposer ref={handle} ariaLabel="fixture" />);
  act(() => {
    handle.current!.setPlainText("  第一行\n\n最后一行  ");
    handle.current!.insertSkill({ skillName: "writer", tags: [] });
    handle.current!.insertFileReference({
      referenceId: "ref-1",
      fileName: "notes.txt",
      category: "document",
      status: "ready",
    });
  });
  const composer = handle.current!.getSnapshot();
  editor.unmount();
  const attachment: MessageAttachment = {
    id: "file-1",
    key: "uploads/notes.txt",
    name: "notes.txt",
    type: "document",
    mimeType: "text/plain",
    size: 42,
    composerReferenceId: "ref-1",
    localOriginalText: "长文本原文",
    fromLongText: true,
  };
  // A previously unseen key forces a disk read, with no in-memory draft.
  localStorage.setItem(
    "cold-page",
    JSON.stringify({ version: 1, composer, attachments: [attachment] }),
  );
  const onSend = vi.fn();
  render(<ChatInput {...props} draftKey="cold-page" onSend={onSend} />);
  expect(screen.getByRole("textbox")).toHaveTextContent("第一行");
  expect(screen.getByRole("button", { name: "Skill writer" })).toBeVisible();
  expect(
    screen.getByRole("button", { name: "File notes.txt, ready" }),
  ).toBeVisible();
  expect(readChatDraft("cold-page").composer).toEqual(composer);
  act(() =>
    updateChatDraft("cold-page", (draft) => ({
      ...draft,
      attachments: [
        { ...attachment, isUploading: false, uploadError: "interrupted" },
      ],
    })),
  );
  const fileChip = screen.getByRole("button", {
    name: "File notes.txt, failed",
  });
  fireEvent.click(fileChip.querySelector("button")!);
  const [restoredFile, category, meta] = uploadFile.mock.calls.at(-1)!;
  expect(restoredFile).toBeInstanceOf(File);
  expect(restoredFile.name).toBe("notes.txt");
  expect(restoredFile.size).toBe(new Blob(["长文本原文"]).size);
  expect(category).toBe("document");
  expect(meta.localOriginalText).toBe("长文本原文");
  act(() =>
    updateChatDraft("cold-page", (draft) => ({
      ...draft,
      attachments: [attachment],
    })),
  );
  fireEvent.submit(screen.getByRole("textbox").closest("form")!);
  expect(onSend.mock.calls[0][2]).toEqual([
    expect.objectContaining({ key: attachment.key }),
  ]);
  expect(onSend.mock.calls[0][3]).toMatchObject({ enabledSkills: ["writer"] });
});

test("deleting a draft removes it instead of reviving old text", () => {
  const view = render(
    <ChatInput {...props} draftKey="delete-draft" pendingInput="待删除" />,
  );
  const empty = createRef<RichChatComposerHandle>();
  const fixture = render(
    <RichChatComposer ref={empty} ariaLabel="empty fixture" />,
  );
  act(() =>
    updateChatDraft("delete-draft", (draft) => ({
      ...draft,
      composer: empty.current!.getSnapshot(),
    })),
  );
  fixture.unmount();
  view.unmount();
  expect(localStorage.getItem("delete-draft")).toBeNull();
  render(<ChatInput {...props} draftKey="delete-draft" />);
  expect(screen.getByRole("textbox").textContent).toBe("");
});
