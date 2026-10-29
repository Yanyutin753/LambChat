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
  uploadFile: vi.fn((file: File) => ({
    promise: Promise.resolve({
      key: `documents/test/${file.name}`,
      url: `/api/upload/file/documents/test/${file.name}`,
      name: file.name,
      type: file.type.startsWith("image/") ? "image" : "document",
      mimeType: file.type,
      size: file.size,
    }),
    abort: vi.fn(),
  })),
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

function useUploadHarness(initial: MessageAttachment[] = []) {
  const [attachments, setAttachments] = useState<MessageAttachment[]>(initial);
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
  expect(apiMocks.uploadFile).toHaveBeenCalledOnce();
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
  expect(apiMocks.uploadFile).toHaveBeenCalledOnce();
});

test("moves an upload from preparing through throttled uploading and server processing", async () => {
  apiMocks.checkFile.mockResolvedValueOnce({ exists: false } as never);
  let resolveUpload!: (value: {
    key: string;
    url: string;
    name: string;
    type: "document";
    mimeType: string;
    size: number;
  }) => void;
  const uploadPromise = new Promise<{
    key: string;
    url: string;
    name: string;
    type: "document";
    mimeType: string;
    size: number;
  }>((resolve) => {
    resolveUpload = resolve;
  });
  apiMocks.uploadFile.mockReturnValueOnce({
    promise: uploadPromise,
    abort: vi.fn(),
  });
  const { result } = renderHook(() => useUploadHarness());
  const file = new File(["upload body"], "notes.txt", {
    type: "text/plain",
  });

  act(() => result.current.uploadFile(file));

  expect(result.current.attachments[0]).toMatchObject({
    name: "notes.txt",
    isUploading: true,
    uploadProgress: 0,
    uploadStage: "preparing",
  });
  await waitFor(() => expect(apiMocks.uploadFile).toHaveBeenCalledOnce());
  const options = apiMocks.uploadFile.mock.calls[0]?.[1] as {
    onProgress?: (progress: number) => void;
    onProcessingProgress?: (progress: number) => void;
  };

  act(() => options.onProgress?.(35));
  expect(result.current.attachments[0]).toMatchObject({
    uploadProgress: 35,
    uploadStage: "uploading",
  });

  act(() => options.onProgress?.(100));
  expect(result.current.attachments[0]).toMatchObject({
    uploadProgress: 99,
    uploadStage: "processing",
  });

  act(() => options.onProcessingProgress?.(63));
  expect(result.current.attachments[0]).toMatchObject({
    uploadStage: "processing",
    uploadProcessingProgress: 63,
  });

  act(() =>
    resolveUpload({
      key: "documents/test/notes.txt",
      url: "/api/upload/file/documents/test/notes.txt",
      name: "notes.txt",
      type: "document",
      mimeType: "text/plain",
      size: file.size,
    }),
  );
  await waitFor(() =>
    expect(result.current.attachments[0]).toEqual(
      expect.objectContaining({ key: "documents/test/notes.txt" }),
    ),
  );
  expect(result.current.attachments[0]).not.toHaveProperty("isUploading");
  expect(result.current.attachments[0]).not.toHaveProperty("uploadProgress");
  expect(result.current.attachments[0]).not.toHaveProperty("uploadStage");
  expect(result.current.attachments[0]).not.toHaveProperty(
    "uploadProcessingProgress",
  );
});

test("image uploads send original bytes for cloud compression and remain cancellable", async () => {
  const abort = vi.fn();
  apiMocks.uploadFile.mockReturnValueOnce({
    promise: new Promise(() => {}),
    abort,
  });
  const { result } = renderHook(() => useUploadHarness());
  const file = new File([new Uint8Array(300 * 1024)], "capture.png", {
    type: "image/png",
  });
  act(() => result.current.uploadFile(file));
  expect(HashWorker.starts).toBe(0);
  expect(apiMocks.uploadFile).toHaveBeenCalledWith(file, expect.any(Object));
  expect(result.current.attachments[0]).toMatchObject({
    name: "capture.png",
    uploadStage: "preparing",
  });
  act(() => result.current.cancelUpload(result.current.attachments[0].id));
  expect(result.current.attachments).toEqual([]);
  expect(abort).toHaveBeenCalledOnce();
});

test("original image above final size limit is sent within the bounded cloud preparation allowance", async () => {
  const { result } = renderHook(() => useUploadHarness());
  await waitFor(() => expect(result.current.uploadLimits?.image).toBe(10));
  const file = new File([new Uint8Array(11 * 1024 * 1024)], "scan.tiff", {
    type: "image/tiff",
  });
  act(() => result.current.uploadFile(file));
  expect(apiMocks.uploadFile).toHaveBeenCalledWith(file, expect.any(Object));
  expect(HashWorker.starts).toBe(0);
});

test("leaving a composer marks only its unfinished uploads as failed", async () => {
  apiMocks.uploadFile.mockReturnValueOnce({
    promise: new Promise(() => {}),
    abort: vi.fn(),
  });
  let attachments: MessageAttachment[] = [
    {
      id: "complete",
      key: "done.txt",
      name: "done.txt",
      type: "document",
      mimeType: "text/plain",
      size: 1,
    },
  ];
  const onAttachmentsChange = (
    update:
      | MessageAttachment[]
      | ((current: MessageAttachment[]) => MessageAttachment[]),
  ) => {
    attachments = typeof update === "function" ? update(attachments) : update;
  };
  const { result, unmount } = renderHook(() =>
    useFileUpload({ attachments, onAttachmentsChange }),
  );
  act(() =>
    result.current.uploadFile(
      new File(["unfinished"], "pending.txt", { type: "text/plain" }),
    ),
  );
  expect(attachments[1].isUploading).toBe(true);
  unmount();
  expect(attachments[0].uploadError).toBeUndefined();
  expect(attachments[1]).toMatchObject({
    name: "pending.txt",
    isUploading: false,
    uploadError: "interrupted",
  });
});

test.each(["scan.TIFF", "scan.tif", "scan.PNG"])(
  "%s uses image intake limits when MIME type is absent",
  async (name) => {
    apiMocks.getConfig.mockResolvedValueOnce({
      uploadLimits: {
        image: 1,
        video: 10,
        audio: 10,
        document: 1,
        maxFiles: 10,
      },
    });
    apiMocks.uploadFile.mockReturnValueOnce({
      promise: new Promise(() => {}),
      abort: vi.fn(),
    });
    const { result } = renderHook(() => useUploadHarness());
    await waitFor(() => expect(result.current.uploadLimits?.image).toBe(1));
    const file = new File([new Uint8Array(1.5 * 1024 * 1024)], name);
    act(() => result.current.uploadFile(file));
    expect(apiMocks.uploadFile).toHaveBeenCalledWith(file, expect.any(Object));
    expect(result.current.attachments[0].type).toBe("image");
  },
);

const localOriginal: MessageAttachment = {
  id: "local-original",
  key: "",
  name: "original.txt",
  size: 3,
  type: "document",
  mimeType: "text/plain",
  localFile: {
    path: "/tmp/original.txt",
    machineId: "m1",
    token: "a".repeat(32),
  },
};
test("cloud promotion replaces the local card and removes its path only after success", async () => {
  const { result } = renderHook(() => useUploadHarness([localOriginal]));
  await act(async () => {
    await result.current.uploadFile(
      new File(["abc"], "original.txt", { type: "text/plain" }),
      "document",
      undefined,
      localOriginal.id,
    );
  });
  expect(result.current.attachments).toHaveLength(1);
  expect(result.current.attachments[0].url).toContain("/api/upload/file/");
  expect(result.current.attachments[0].localFile).toBeUndefined();
});
test("failed cloud promotion keeps the original path and a visible retryable error", async () => {
  apiMocks.uploadFile.mockReturnValueOnce({
    promise: Promise.reject(new Error("offline")),
    abort: vi.fn(),
  });
  const { result } = renderHook(() => useUploadHarness([localOriginal]));
  await act(async () => {
    await result.current.uploadFile(
      new File(["abc"], "original.txt", { type: "text/plain" }),
      "document",
      undefined,
      localOriginal.id,
    );
  });
  expect(result.current.attachments).toEqual([
    expect.objectContaining({
      id: localOriginal.id,
      localFile: localOriginal.localFile,
      isUploading: false,
      uploadError: "offline",
    }),
  ]);
});
