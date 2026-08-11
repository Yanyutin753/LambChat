/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../types";
import i18n from "../../i18n";
import { useFileUpload } from "../useFileUpload";

const apiMocks = vi.hoisted(() => ({
  getConfig: vi.fn(async () => ({
    uploadLimits: {
      image: 10,
      video: 10,
      audio: 10,
      document: 10,
      maxFiles: 10,
    },
  })),
  checkFile: vi.fn(
    async (_hash: string, size: number, name: string, mimeType: string) => ({
      exists: true,
      key: `documents/test/${name}`,
      url: `/api/upload/file/documents/test/${name}`,
      name,
      type: mimeType.startsWith("image/") ? "image" : "document",
      mimeType,
      size,
    }),
  ),
  uploadFile: vi.fn(),
}));

const toastMocks = vi.hoisted(() => ({ error: vi.fn() }));

vi.mock("../../services/api", () => ({
  uploadApi: apiMocks,
}));

vi.mock("react-hot-toast", () => ({
  default: toastMocks,
}));

class HashWorker {
  static starts = 0;
  onmessage: ((event: MessageEvent<{ hash: string }>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  constructor() {
    HashWorker.starts += 1;
  }

  postMessage() {
    queueMicrotask(
      () =>
        this.onmessage?.({ data: { hash: "a".repeat(64) } } as MessageEvent<{
          hash: string;
        }>),
    );
  }

  terminate() {}
}

function useUploadHarness() {
  const [attachments, setAttachments] = useState<MessageAttachment[]>([]);
  const upload = useFileUpload({
    attachments,
    onAttachmentsChange: setAttachments,
  });
  return { ...upload, attachments };
}

beforeEach(async () => {
  vi.clearAllMocks();
  HashWorker.starts = 0;
  vi.stubGlobal("Worker", HashWorker);
  await i18n.changeLanguage("en");
});

test("zero-byte files never enter attachment state or hashing", async () => {
  const { result } = renderHook(() => useUploadHarness());

  act(() => result.current.uploadFile(new File([], "bpm_r5.bin")));

  await waitFor(() =>
    expect(toastMocks.error).toHaveBeenCalledWith(
      "This file is empty and cannot be uploaded.",
    ),
  );
  expect(result.current.attachments).toEqual([]);
  expect(HashWorker.starts).toBe(0);
  expect(apiMocks.checkFile).not.toHaveBeenCalled();
  expect(apiMocks.uploadFile).not.toHaveBeenCalled();
});

test("mixed batches skip empty files and keep uploading valid files", async () => {
  const { result } = renderHook(() => useUploadHarness());
  const empty = new File([], "stale.bin");
  const valid = new File(["valid contents"], "notes.txt", {
    type: "text/plain",
  });

  act(() => result.current.uploadFiles([empty, valid]));

  await waitFor(() =>
    expect(result.current.attachments).toEqual([
      expect.objectContaining({
        name: "notes.txt",
        size: valid.size,
        mimeType: "text/plain",
      }),
    ]),
  );
  expect(toastMocks.error).toHaveBeenCalledWith(
    "This file is empty and cannot be uploaded.",
  );
  expect(HashWorker.starts).toBe(1);
  expect(apiMocks.checkFile).toHaveBeenCalledOnce();
});

test("file-count validation ignores empty files in a mixed batch", async () => {
  apiMocks.getConfig.mockResolvedValueOnce({
    uploadLimits: {
      image: 10,
      video: 10,
      audio: 10,
      document: 10,
      maxFiles: 1,
    },
  });
  const { result } = renderHook(() => useUploadHarness());
  const empty = new File([], "stale.bin");
  const valid = new File(["valid contents"], "only-valid-file.txt", {
    type: "text/plain",
  });

  await waitFor(() => expect(result.current.uploadLimits?.maxFiles).toBe(1));
  act(() => result.current.uploadFiles([empty, valid]));

  await waitFor(() =>
    expect(result.current.attachments).toEqual([
      expect.objectContaining({
        name: "only-valid-file.txt",
        size: valid.size,
        mimeType: "text/plain",
      }),
    ]),
  );
  expect(toastMocks.error).toHaveBeenCalledTimes(1);
  expect(toastMocks.error).toHaveBeenCalledWith(
    "This file is empty and cannot be uploaded.",
  );
  expect(HashWorker.starts).toBe(1);
  expect(apiMocks.checkFile).toHaveBeenCalledOnce();
});
