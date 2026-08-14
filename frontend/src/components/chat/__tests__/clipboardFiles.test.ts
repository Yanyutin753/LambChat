/** @vitest-environment jsdom */

import { afterEach, describe, expect, test, vi } from "vitest";
import {
  classifyClipboardFiles,
  decodeEmbeddedClipboardImage,
} from "../clipboardFiles";

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

class SuccessfulClipboardWorker {
  static terminations = 0;
  onmessage: ((event: MessageEvent<{ ok: true; blob: Blob }>) => void) | null =
    null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  postMessage() {
    queueMicrotask(() => {
      this.onmessage?.({
        data: {
          ok: true,
          blob: new Blob([new Uint8Array([1, 2, 3])], { type: "image/png" }),
        },
      } as MessageEvent<{ ok: true; blob: Blob }>);
    });
  }

  terminate() {
    SuccessfulClipboardWorker.terminations += 1;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

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

  test("classifies an embedded image without decoding bytes synchronously", () => {
    const placeholder = new File([], "bpm_r5.bin", { type: "" });
    const atobSpy = vi.spyOn(globalThis, "atob");

    const result = classifyClipboardFiles(
      clipboardData({
        files: [placeholder],
        html: `<img src="${PNG_DATA_URL}" alt="copied image">`,
      }),
    );

    expect(result).toEqual({
      kind: "embedded-image",
      source: PNG_DATA_URL,
      mimeType: "image/png",
    });
    expect(atobSpy).not.toHaveBeenCalled();
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

test("decodes a validated embedded image in a worker", async () => {
  SuccessfulClipboardWorker.terminations = 0;
  vi.stubGlobal("Worker", SuccessfulClipboardWorker);

  const file = await decodeEmbeddedClipboardImage(PNG_DATA_URL, "image/png");

  expect(file).toMatchObject({ name: "pasted-image.png", type: "image/png" });
  expect(file.size).toBe(3);
  expect(SuccessfulClipboardWorker.terminations).toBe(1);
});

test("decodes a validated embedded image asynchronously when Worker is unavailable", async () => {
  vi.stubGlobal("Worker", undefined);
  const fetchMock = vi.fn(async () => ({
    blob: async () => new Blob([new Uint8Array([4, 5])], { type: "image/png" }),
  }));
  vi.stubGlobal("fetch", fetchMock);

  const file = await decodeEmbeddedClipboardImage(PNG_DATA_URL, "image/png");

  expect(file.size).toBe(2);
  expect(fetchMock).toHaveBeenCalledWith(PNG_DATA_URL);
});
