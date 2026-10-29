/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { useState, type DragEvent } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../types";
import { useComposerDesktopAttachments } from "../useComposerDesktopAttachments";

const mocks = vi.hoisted(() => ({
  resolve: vi.fn(),
  upload: vi.fn(),
  error: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }));
vi.mock("react-hot-toast", () => ({ toast: { error: mocks.error } }));
vi.mock("../useSandboxStatus", () => ({
  useSandboxStatus: () => ({ defaultMachineId: "m1", currentMachineId: "m1" }),
}));
vi.mock("../../services/tauri/sandboxShell", () => ({
  isShellAvailable: () => true,
}));
vi.mock("../../services/tauri/desktopFiles", async (original) => ({
  ...(await original<object>()),
  resolveDroppedDesktopFiles: mocks.resolve,
}));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("../../services/api/token", () => ({
  getAccessToken: () => "account",
}));
vi.mock("../../services/api/upload", () => ({
  uploadApi: { getConfig: vi.fn() },
}));
vi.mock("../../services/api/uploadFileUrl", () => ({
  isCurrentFileAccount: () => true,
}));
vi.mock("../../services/api/config", () => ({ getFullUrl: (s: string) => s }));

function useHarness(draftKey = "d1", disabled = false) {
  const [attachments, onAttachmentsChange] = useState<MessageAttachment[]>([]);
  const result = useComposerDesktopAttachments({
    attachments,
    onAttachmentsChange,
    agent: { supports_sandbox: true },
    mode: "local",
    selectedMachine: "m1",
    accountId: "u1",
    draftKey,
    disabled,
    allowedCategories: ["image", "document"],
    validateCount: () => true,
    uploadFile: mocks.upload,
    uploadFiles: mocks.upload,
    uploadLimits: null,
  });
  return { ...result, attachments };
}
const picture = new File(["image bytes"], "wechat.png", { type: "image/png" });
function drop(files: File[], html = "", items: File[] = []) {
  return {
    preventDefault: vi.fn(),
    dataTransfer: {
      files,
      items: items.map((file) => ({ kind: "file", getAsFile: () => file })),
      getData: (type: string) => (type === "text/html" ? html : ""),
    },
  } as unknown as DragEvent;
}
const receipt = {
  token: "a".repeat(32),
  path: "C:\\Pictures\\wechat.png",
  name: "wechat.png",
  size: 11,
  modified: "1",
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.resolve.mockResolvedValue([null]);
});

test("desktop image bytes without an original path reach the existing upload pipeline", async () => {
  const { result } = renderHook(() => useHarness());
  await act(async () => {
    await result.current.handleDrop(drop([picture]));
  });
  expect(mocks.upload).toHaveBeenCalledWith([picture]);
});
test("a dropped native file keeps its original path and does not upload", async () => {
  mocks.resolve.mockResolvedValue([receipt]);
  const { result } = renderHook(() => useHarness());
  await act(async () => {
    await result.current.handleDrop(drop([picture]));
  });
  expect(result.current.attachments[0]?.localFile?.path).toBe(
    "C:\\Pictures\\wechat.png",
  );
  expect(mocks.upload).not.toHaveBeenCalled();
});
test("file items are accepted even when the drag source leaves FileList empty", async () => {
  const { result } = renderHook(() => useHarness());
  await act(async () => {
    await result.current.handleDrop(drop([], "", [picture]));
  });
  expect(mocks.upload).toHaveBeenCalledWith([picture]);
});
test("an unreadable image placeholder reports a useful error instead of doing nothing", async () => {
  const { result } = renderHook(() => useHarness());
  await act(async () => {
    await result.current.handleDrop(
      drop([], '<img src="file:///wechat/private.png">'),
    );
  });
  expect(mocks.error).toHaveBeenCalledWith("fileUpload.dropUnavailable");
  expect(mocks.upload).not.toHaveBeenCalled();
});
test("a late native response cannot attach to another draft", async () => {
  let finish!: (value: (typeof receipt)[]) => void;
  mocks.resolve.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { result, rerender } = renderHook(({ draft }) => useHarness(draft), {
    initialProps: { draft: "first" },
  });
  let pending: unknown;
  act(() => {
    pending = result.current.handleDrop(drop([picture]));
  });
  expect(mocks.resolve).toHaveBeenCalled();
  rerender({ draft: "second" });
  await act(async () => {
    finish([receipt]);
    await pending;
  });
  expect(result.current.attachments).toEqual([]);
  expect(mocks.upload).not.toHaveBeenCalled();
});
test("disabled composer does not accept dropped files", async () => {
  const { result } = renderHook(() => useHarness("d1", true));
  await act(async () => {
    await result.current.handleDrop(drop([picture]));
  });
  expect(mocks.resolve).not.toHaveBeenCalled();
  expect(mocks.upload).not.toHaveBeenCalled();
});
test("a virtual file with no readable File object reports the failure", async () => {
  const { result } = renderHook(() => useHarness());
  const event = {
    preventDefault: vi.fn(),
    dataTransfer: {
      files: [],
      types: ["Files"],
      getData: () => "",
      items: [{ kind: "file", getAsFile: () => null }],
    },
  } as unknown as DragEvent;
  await act(async () => {
    await result.current.handleDrop(event);
  });
  expect(mocks.error).toHaveBeenCalledWith("fileUpload.dropUnavailable");
});
