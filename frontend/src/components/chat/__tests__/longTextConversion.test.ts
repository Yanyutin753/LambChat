import {
  LONG_TEXT_THRESHOLD,
  shouldConvertLongText,
  buildLongTextFileName,
  createLongTextFile,
  isLongTextAttachment,
  stripLocalAttachmentFields,
  prepareLongTextSubmit,
  canRestoreLongTextAttachment,
  restoreInputFromLongTextAttachment,
  shouldSkipLongTextConversion,
} from "../longTextConversion";
import type { MessageAttachment } from "../../../types";

function attachment(
  overrides: Partial<MessageAttachment> = {},
): MessageAttachment {
  return {
    id: "att-1",
    key: "k1",
    name: "long-text-20260101120000.txt",
    type: "document",
    mimeType: "text/plain",
    size: 12,
    url: "/api/upload/file/k1",
    ...overrides,
  };
}

test("shouldConvertLongText is false at or below threshold", () => {
  expect(shouldConvertLongText("a".repeat(LONG_TEXT_THRESHOLD))).toBe(false);
  expect(shouldConvertLongText("short")).toBe(false);
});

test("shouldConvertLongText is true above threshold", () => {
  expect(shouldConvertLongText("a".repeat(LONG_TEXT_THRESHOLD + 1))).toBe(true);
});

test("buildLongTextFileName uses txt extension and timestamp", () => {
  const name = buildLongTextFileName(new Date("2026-01-02T03:04:05Z"));
  expect(name).toMatch(/^long-text-\d{14}\.txt$/);
});

test("createLongTextFile builds a plain text document", () => {
  const file = createLongTextFile("hello world", "note.txt");
  expect(file.name).toBe("note.txt");
  expect(file.type).toBe("text/plain");
  expect(file.size).toBeGreaterThan(0);
});

test("isLongTextAttachment detects client-only long text flag", () => {
  expect(isLongTextAttachment(attachment())).toBe(false);
  expect(
    isLongTextAttachment(
      attachment({ fromLongText: true, localOriginalText: "x" }),
    ),
  ).toBe(true);
});

test("stripLocalAttachmentFields removes restore-only fields before submit", () => {
  const cleaned = stripLocalAttachmentFields([
    attachment({
      fromLongText: true,
      localOriginalText: "secret long text",
      isUploading: false,
      uploadProgress: 100,
      composerReferenceId: "ref-1",
      uploadError: "local only",
    }),
  ]);
  expect(cleaned[0]).toEqual({
    id: "att-1",
    key: "k1",
    name: "long-text-20260101120000.txt",
    type: "document",
    mimeType: "text/plain",
    size: 12,
    url: "/api/upload/file/k1",
  });
  expect(cleaned[0]).not.toHaveProperty("localOriginalText");
  expect(cleaned[0]).not.toHaveProperty("fromLongText");
  expect(cleaned[0]).not.toHaveProperty("composerReferenceId");
  expect(cleaned[0]).not.toHaveProperty("uploadError");
});

test("prepareLongTextSubmit keeps empty body when only long text attachment exists", () => {
  expect(
    prepareLongTextSubmit({
      message: "   ",
      attachments: [
        attachment({ fromLongText: true, localOriginalText: "abc" }),
      ],
    }),
  ).toEqual({
    message: "",
    attachments: [
      {
        id: "att-1",
        key: "k1",
        name: "long-text-20260101120000.txt",
        type: "document",
        mimeType: "text/plain",
        size: 12,
        url: "/api/upload/file/k1",
      },
    ],
  });
});

test("prepareLongTextSubmit keeps custom message when user typed one", () => {
  expect(
    prepareLongTextSubmit({
      message: "please summarize",
      attachments: [
        attachment({ fromLongText: true, localOriginalText: "abc" }),
      ],
    }).message,
  ).toBe("please summarize");
});

test("canRestoreLongTextAttachment requires original text", () => {
  expect(canRestoreLongTextAttachment(attachment({ fromLongText: true }))).toBe(
    false,
  );
  expect(
    canRestoreLongTextAttachment(
      attachment({ fromLongText: true, localOriginalText: "restored" }),
    ),
  ).toBe(true);
});

test("restoreInputFromLongTextAttachment returns original text", () => {
  expect(
    restoreInputFromLongTextAttachment(
      attachment({ fromLongText: true, localOriginalText: "full body" }),
    ),
  ).toBe("full body");
});

test("shouldSkipLongTextConversion honors one-shot allow oversized flag for current content", () => {
  const text = "a".repeat(LONG_TEXT_THRESHOLD + 10);
  expect(
    shouldSkipLongTextConversion({
      text,
      allowOversizedText: true,
      expanded: false,
    }),
  ).toBe(true);
  expect(
    shouldSkipLongTextConversion({
      text,
      allowOversizedText: false,
      expanded: true,
    }),
  ).toBe(true);
  expect(
    shouldSkipLongTextConversion({
      text,
      allowOversizedText: false,
      expanded: false,
    }),
  ).toBe(false);
});
