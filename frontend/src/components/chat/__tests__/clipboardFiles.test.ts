/** @vitest-environment jsdom */

import { describe, expect, test, vi } from "vitest";
import { classifyClipboardFiles } from "../clipboardFiles";

const PNG_DATA_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

function clipboardData({
  files = [],
  html = "",
  text = "",
}: {
  files?: File[];
  html?: string;
  text?: string;
}): Pick<DataTransfer, "files" | "getData"> {
  return {
    files: files as unknown as FileList,
    getData: (type: string) => {
      if (type === "text/html") return html;
      if (type === "text/plain") return text;
      return "";
    },
  };
}

describe("classifyClipboardFiles", () => {
  test("keeps non-empty native clipboard files", () => {
    const image = new File(["image-bytes"], "capture.png", {
      type: "image/png",
    });

    expect(classifyClipboardFiles(clipboardData({ files: [image] }))).toEqual({
      kind: "files",
      files: [image],
    });
  });

  test("rejects a zero-byte virtual file placeholder", () => {
    const placeholder = new File([], "bpm_r5.bin", { type: "" });

    expect(
      classifyClipboardFiles(clipboardData({ files: [placeholder] })),
    ).toEqual({ kind: "invalid-image" });
  });

  test("recovers an embedded data image when the native file is empty", () => {
    const placeholder = new File([], "bpm_r5.bin", { type: "" });

    const result = classifyClipboardFiles(
      clipboardData({
        files: [placeholder],
        html: `<img src="${PNG_DATA_URL}" alt="copied image">`,
      }),
    );

    expect(result.kind).toBe("files");
    if (result.kind !== "files") throw new Error("expected recovered file");
    expect(result.files).toHaveLength(1);
    expect(result.files[0]).toMatchObject({
      name: "pasted-image.png",
      type: "image/png",
    });
    expect(result.files[0].size).toBeGreaterThan(0);
  });

  test.each([
    '<img src="https://files.example.test/image.png">',
    '<img src="blob:https://app.example.test/stale">',
  ])("rejects image markup without readable bytes", (html) => {
    expect(classifyClipboardFiles(clipboardData({ html }))).toEqual({
      kind: "invalid-image",
    });
  });

  test("classifies image markup without constructing resource-bearing DOM", () => {
    const createElement = vi
      .spyOn(document, "createElement")
      .mockImplementation(() => {
        throw new Error("clipboard classification must not construct DOM");
      });

    try {
      expect(
        classifyClipboardFiles(
          clipboardData({
            html: '<img alt="remote" src="https://files.example.test/a.png">',
          }),
        ),
      ).toEqual({ kind: "invalid-image" });
      expect(createElement).not.toHaveBeenCalled();
    } finally {
      createElement.mockRestore();
    }
  });

  test("leaves ordinary text for the text paste pipeline", () => {
    expect(
      classifyClipboardFiles(clipboardData({ text: "ordinary pasted text" })),
    ).toEqual({ kind: "none" });
  });
});
