/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import toast from "react-hot-toast";
import {
  getChatDraftKey,
  readChatDraft,
  updateChatDraft,
  useChatDraftAttachments,
} from "../chatDraftStore";

const attachment = {
  id: "one",
  key: "uploaded/one.txt",
  name: "one.txt",
  type: "document" as const,
  mimeType: "text/plain",
  size: 20,
};

test("draft storage separates accounts, servers, conversations and the new-chat composer", () => {
  const first = getChatDraftKey("alice", "one");
  expect(first).not.toBe(getChatDraftKey("bob", "one"));
  expect(first).not.toBe(getChatDraftKey("alice", "two"));
  expect(first).not.toBe(getChatDraftKey("alice", null));
  expect(getChatDraftKey(undefined, "one")).toBeUndefined();
  localStorage.setItem("lambchat_server_url", "https://another.example");
  expect(first).not.toBe(getChatDraftKey("alice", "one"));
  localStorage.removeItem("lambchat_server_url");
});

test("attachment updates from an old conversation cannot leak into the active draft", () => {
  const { result, rerender } = renderHook(
    ({ scope }) => useChatDraftAttachments(scope),
    { initialProps: { scope: "attachments-a" } },
  );
  const oldSetter = result.current[1];
  act(() => oldSetter([attachment]));
  rerender({ scope: "attachments-b" });
  expect(result.current[0]).toEqual([]);
  act(() =>
    oldSetter((current) => [...current, { ...attachment, id: "late" }]),
  );
  expect(result.current[0]).toEqual([]);
  rerender({ scope: "attachments-a" });
  expect(result.current[0].map((item) => item.id)).toEqual(["one", "late"]);
});

test("reload keeps interrupted uploads visible as failed and rejects corrupt data", () => {
  localStorage.setItem(
    "interrupted",
    JSON.stringify({
      version: 1,
      attachments: [
        { ...attachment, isUploading: true, url: "blob:expired" },
        { id: false },
      ],
    }),
  );
  expect(readChatDraft("interrupted").attachments).toEqual([
    {
      ...attachment,
      isUploading: false,
      uploadError: "interrupted",
      url: undefined,
    },
  ]);
  localStorage.setItem("invalid-json", "{");
  expect(readChatDraft("invalid-json").attachments).toEqual([]);
  localStorage.setItem(
    "invalid-tree",
    JSON.stringify({
      version: 1,
      composer: {
        version: 1,
        editorState: { root: { type: "root", children: "bad" } },
      },
      attachments: [],
    }),
  );
  expect(readChatDraft("invalid-tree").composer).toBeUndefined();
});

test("full storage retains the live draft and tells the user it cannot survive reload", () => {
  const error = vi.spyOn(toast, "error").mockImplementation(() => "toast");
  const setItem = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(() => {
      throw new DOMException("Full", "QuotaExceededError");
    });
  try {
    updateChatDraft("quota", () => ({ attachments: [attachment] }));
    expect(readChatDraft("quota").attachments).toEqual([attachment]);
    expect(error).toHaveBeenCalledWith(expect.any(String), {
      id: "chat-draft-save-failed",
    });
  } finally {
    setItem.mockRestore();
    error.mockRestore();
  }
});
