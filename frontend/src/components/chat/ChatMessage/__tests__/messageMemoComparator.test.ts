import type { Message } from "../../../../types";
import { areChatMessagePropsEqual } from "../messageMemo";

const baseMessage: Message = {
  id: "message-1",
  role: "assistant",
  content: "hello",
  timestamp: new Date("2026-01-01T00:00:00Z"),
};

test("keeps completed history messages stable when unrelated previews change", () => {
  expect(
    areChatMessagePropsEqual(
      {
        message: baseMessage,
        isLastMessage: false,
        activePreview: {
          kind: "file",
          previewKey: "file-2",
          filePath: "/tmp/2.txt",
        },
        latestAutoPreview: { messageId: "message-2", partIndex: 0 },
      },
      {
        message: baseMessage,
        isLastMessage: false,
        activePreview: {
          kind: "file",
          previewKey: "file-3",
          filePath: "/tmp/3.txt",
        },
        latestAutoPreview: { messageId: "message-3", partIndex: 0 },
      },
    ),
  ).toBe(true);
});

test("updates the message that owns an active preview", () => {
  const messageWithPreview: Message = {
    ...baseMessage,
    parts: [
      {
        type: "artifact",
        success: true,
        artifact: {
          kind: "file",
          id: "artifact-1",
          name: "one.txt",
          path: "/tmp/one.txt",
          preview: {
            kind: "file",
            previewKey: "file-1",
            filePath: "/tmp/one.txt",
          },
        },
      },
    ],
  };

  expect(
    areChatMessagePropsEqual(
      {
        message: messageWithPreview,
        isLastMessage: false,
        activePreview: {
          kind: "file",
          previewKey: "file-1",
          filePath: "/tmp/one.txt",
        },
      },
      {
        message: messageWithPreview,
        isLastMessage: false,
        activePreview: {
          kind: "file",
          previewKey: "file-2",
          filePath: "/tmp/two.txt",
        },
      },
    ),
  ).toBe(false);
});

test("ignores artifact parts without preview data when checking active previews", () => {
  const messageWithLegacyArtifact: Message = {
    ...baseMessage,
    parts: [
      {
        type: "artifact",
        success: true,
        artifact: {
          kind: "file",
          id: "artifact-1",
          name: "legacy.txt",
          path: "/tmp/legacy.txt",
        },
      } as Message["parts"][number],
    ],
  };

  expect(
    areChatMessagePropsEqual(
      {
        message: messageWithLegacyArtifact,
        isLastMessage: false,
        activePreview: {
          kind: "file",
          previewKey: "file-1",
          filePath: "/tmp/one.txt",
        },
      },
      {
        message: messageWithLegacyArtifact,
        isLastMessage: false,
        activePreview: {
          kind: "file",
          previewKey: "file-2",
          filePath: "/tmp/two.txt",
        },
      },
    ),
  ).toBe(true);
});

test("updates streaming messages when their message object changes", () => {
  expect(
    areChatMessagePropsEqual(
      { message: { ...baseMessage, isStreaming: true, content: "a" } },
      { message: { ...baseMessage, isStreaming: true, content: "ab" } },
    ),
  ).toBe(false);
});
