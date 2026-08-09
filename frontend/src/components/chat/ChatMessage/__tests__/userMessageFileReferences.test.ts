import { describe, expect, test } from "vitest";
import type { MessageAttachment } from "../../../../types";
import { splitUserMessageFileReferences } from "../userMessageFileReferences";

function attachment(name: string): MessageAttachment {
  return {
    id: `attachment-${name}`,
    name,
    key: `uploads/${name}`,
    mimeType: "text/plain",
    size: 12,
    category: "document",
  };
}

describe("splitUserMessageFileReferences", () => {
  test("keeps text order while promoting matching file markers", () => {
    const file = attachment("notes.txt");

    expect(
      splitUserMessageFileReferences("开头 [引用文件：notes.txt] 结尾", [file]),
    ).toEqual([
      { kind: "text", value: "开头 " },
      {
        kind: "file",
        fileName: "notes.txt",
        referenceNumber: 1,
        attachment: file,
      },
      { kind: "text", value: " 结尾" },
    ]);
  });

  test("leaves unmatched bracket text untouched", () => {
    expect(splitUserMessageFileReferences("[引用文件：plain.txt]", [])).toEqual(
      [{ kind: "text", value: "[引用文件：plain.txt]" }],
    );
  });
});
