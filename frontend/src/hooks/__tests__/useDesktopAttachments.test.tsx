/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../types";
import { useDesktopAttachments } from "../useDesktopAttachments";
const mocks = vi.hoisted(() => ({
  pick: vi.fn(),
  read: vi.fn(),
  upload: vi.fn(),
  drop: vi.fn(),
  translate: (k: string) => k,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.translate }),
}));
vi.mock("../../services/tauri/sandboxShell", () => ({
  isShellAvailable: () => true,
}));
vi.mock("../../services/tauri/desktopFiles", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  pickDesktopFiles: mocks.pick,
  readDesktopFile: mocks.read,
}));
vi.mock("../../services/api/upload", () => ({
  uploadApi: { getConfig: vi.fn() },
}));
vi.mock("../../services/api/config", () => ({ getFullUrl: (s: string) => s }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: async (_name: string, callback: typeof mocks.drop) => {
    mocks.drop = callback;
    return () => {};
  },
}));
vi.mock("../../services/api/token", () => ({
  getAccessToken: () => "account",
}));
vi.mock("../../services/api/uploadFileUrl", () => ({
  isCurrentFileAccount: () => true,
}));
const original = {
  token: "a".repeat(32),
  path: "/tmp/a.txt",
  name: "a.txt",
  size: 3,
  modified: "1",
};
const limits = { image: 20, video: 100, audio: 20, document: 50, maxFiles: 20 };
function useHarness(mode: string, machineId: string | null = "m1") {
  const [attachments, setAttachments] = useState<MessageAttachment[]>([]);
  const result = useDesktopAttachments({
    attachments,
    onAttachmentsChange: setAttachments,
    mode,
    machineId,
    currentMachineId: "m1",
    accountId: "u1",
    draftKey: "d1",
    dropTarget: { current: document.createElement("div") },
    allowedCategories: ["image", "document"],
    validateCount: () => true,
    uploadFile: mocks.upload,
    uploadLimits: limits,
  });
  return { ...result, attachments, setAttachments };
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.pick.mockResolvedValue([original]);
  mocks.read.mockResolvedValue(
    new File(["abc"], "a.txt", { type: "text/plain" }),
  );
});
test("local native selection adds a path with no hash, upload or byte read", async () => {
  const { result } = renderHook(() => useHarness("local"));
  await act(async () => {
    await result.current.pickFiles();
  });
  expect(result.current.attachments[0].localFile?.path).toBe("/tmp/a.txt");
  expect(mocks.read).not.toHaveBeenCalled();
  expect(mocks.upload).not.toHaveBeenCalled();
  expect(result.current.blocked).toBe(false);
});
test("switching a pending local draft to cloud uploads before allowing send", async () => {
  const { result, rerender } = renderHook(({ mode }) => useHarness(mode), {
    initialProps: { mode: "local" },
  });
  await act(async () => {
    await result.current.pickFiles();
  });
  rerender({ mode: "cloud" });
  expect(result.current.blocked).toBe(true);
  await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(1));
  expect(mocks.upload.mock.calls[0][3]).toBe(`local-${original.token}`);
});
test("removing a local card while its cloud bytes load cannot resurrect it", async () => {
  let finish!: (f: File) => void;
  mocks.read.mockReturnValue(
    new Promise<File>((r) => {
      finish = r;
    }),
  );
  const { result } = renderHook(() => useHarness("cloud"));
  await act(async () => {
    await result.current.pickFiles();
  });
  await waitFor(() => expect(mocks.read).toHaveBeenCalled());
  act(() => result.current.setAttachments([]));
  await act(async () => finish(new File(["abc"], "a.txt")));
  expect(mocks.upload).not.toHaveBeenCalled();
  expect(result.current.attachments).toEqual([]);
});

test("a drop started before switching environment is not attached to the new draft context", async () => {
  const { result, rerender } = renderHook(({ mode }) => useHarness(mode), {
    initialProps: { mode: "local" },
  });
  await act(async () => {});
  act(() =>
    mocks.drop({
      payload: {
        batchId: "batch",
        pending: true,
        files: [],
        position: { x: 0, y: 0 },
      },
    }),
  );
  rerender({ mode: "cloud" });
  await act(async () => {});
  act(() =>
    mocks.drop({
      payload: {
        batchId: "batch",
        files: [original],
        position: { x: 0, y: 0 },
      },
    }),
  );
  expect(result.current.attachments).toEqual([]);
});

test.each([
  ["pending", "m1"],
  ["local", null],
])(
  "does not upload restored paths before environment resolves (%s)",
  async (mode, machineId) => {
    const { result, rerender } = renderHook(
      ({ mode, machineId }) => useHarness(mode, machineId),
      { initialProps: { mode: "local", machineId: "m1" as string | null } },
    );
    await act(async () => {
      await result.current.pickFiles();
    });
    rerender({ mode, machineId });
    await act(async () => {});
    expect(result.current.blocked).toBe(true);
    expect(mocks.read).not.toHaveBeenCalled();
    expect(mocks.upload).not.toHaveBeenCalled();
    rerender({ mode: "local", machineId: "m1" });
    expect(result.current.blocked).toBe(false);
  },
);

test("selection while environment is unresolved does not create an unbound path", async () => {
  const { result } = renderHook(() => useHarness("pending"));
  await act(async () => {
    await result.current.pickFiles();
  });
  expect(result.current.attachments).toEqual([]);
  expect(mocks.read).not.toHaveBeenCalled();
});
