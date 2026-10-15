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
  test("keeps skills interleaved with text and files without promoting unselected skills", () => {
    const file = attachment("notes.txt");
    expect(splitUserMessageFileReferences(
      "先 [引用技能：writer] 再 [引用文件：notes.txt] 后 [引用技能：reviewer] [引用技能：unknown]",
      [file],
      ["writer", "reviewer"],
    )).toEqual([
      { kind: "text", value: "先 " },
      { kind: "skill", skillName: "writer" },
      { kind: "text", value: " 再 " },
      { kind: "file", fileName: "notes.txt", referenceNumber: 1, attachment: file },
      { kind: "text", value: " 后 " },
      { kind: "skill", skillName: "reviewer" },
      { kind: "text", value: " [引用技能：unknown]" },
    ]);
  });
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
