/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Blob as NodeBlob } from "node:buffer";
import toast from "react-hot-toast";
import { downloadBlob, downloadUrl } from "../viewerDownload";

const bridge = vi.hoisted(() => ({ invoke: vi.fn() }));
const mobileFilesystem = vi.hoisted(() => ({
  writeFile: vi.fn().mockResolvedValue({ uri: "file:///documents/file.txt" }),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke }));
vi.mock(
  "@capacitor/filesystem",
  () => ({
    Directory: { Documents: "DOCUMENTS" },
    Filesystem: mobileFilesystem,
  }),
  { virtual: true },
);
vi.mock("react-hot-toast", () => ({ default: { error: vi.fn() } }));
vi.mock("i18next", () => ({ default: { t: (key: string) => key } }));
vi.mock("../../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn(),
}));
import { authenticatedRequest } from "../../../services/api/authenticatedRequest";
const request = vi.mocked(authenticatedRequest);
let anchorClick: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  bridge.invoke.mockReset().mockResolvedValue(true);
  mobileFilesystem.writeFile.mockClear();
  vi.mocked(toast.error).mockClear();
  request.mockReset();
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  vi.stubGlobal("Blob", NodeBlob);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("original bytes")),
  );
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:download");
      static revokeObjectURL = vi.fn();
    },
  );
  anchorClick = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("desktop saves original binary bytes and Unicode filename through the native dialog", async () => {
  await downloadBlob(new Blob([new Uint8Array([80, 75, 0, 255])]), "报告.docx");
  expect(bridge.invoke).toHaveBeenCalledOnce();
  const [command, payload, options] = bridge.invoke.mock.calls[0];
  expect(command).toBe("desktop_save_file");
  expect(Array.from(new Uint8Array(payload))).toEqual([80, 75, 0, 255]);
  expect(JSON.parse(options.headers["x-file-name"])).toBe("报告.docx");
  expect(options.headers["x-file-name"]).toMatch(/^[\x20-\x7e]+$/);
  expect(anchorClick).not.toHaveBeenCalled();
});

test("desktop URL downloads fetch bytes before invoking the save dialog", async () => {
  await downloadUrl("https://example.com/report.docx", "report.docx");
  expect(fetch).toHaveBeenCalledWith(
    "https://example.com/report.docx",
    undefined,
  );
  expect(bridge.invoke).toHaveBeenCalledOnce();
  expect(anchorClick).not.toHaveBeenCalled();
});

test("cancelling the native dialog does not start a browser download or report failure", async () => {
  bridge.invoke.mockResolvedValue(false);
  await downloadBlob(new Blob(["data"]), "file.txt");
  expect(bridge.invoke).toHaveBeenCalledOnce();
  expect(anchorClick).not.toHaveBeenCalled();
  expect(toast.error).not.toHaveBeenCalled();
});

test("a native save failure is reported without attempting a browser fallback", async () => {
  bridge.invoke.mockRejectedValue(new Error("disk full"));
  await downloadBlob(new Blob(["data"]), "file.txt");
  expect(toast.error).toHaveBeenCalledWith("chat.message.downloadFailed");
  expect(anchorClick).not.toHaveBeenCalled();
});

test("web downloads keep the browser anchor path", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", undefined);
  await downloadBlob(new Blob(["data"]), "file.txt");
  expect(anchorClick).toHaveBeenCalledOnce();
  expect(bridge.invoke).not.toHaveBeenCalled();
});

test("Capacitor downloads save bytes and open the native share sheet", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", undefined);
  vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
  const share = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "share", {
    configurable: true,
    value: share,
  });

  await downloadBlob(new Blob([new Uint8Array([80, 75, 0, 255])]), "报告.docx");

  expect(mobileFilesystem.writeFile).toHaveBeenCalledWith(
    expect.objectContaining({ path: "报告.docx", directory: "DOCUMENTS" }),
  );
  expect(share).toHaveBeenCalledOnce();
  expect(anchorClick).not.toHaveBeenCalled();
});

test("browser upload downloads hand the signed proxy URL to the native anchor without prefetching bytes", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", undefined);
  await downloadUrl(
    "/api/upload/file/generated-images/gen-image.png?file_token=tok",
  );
  expect(fetch).not.toHaveBeenCalled();
  expect(request).not.toHaveBeenCalled();
  expect(anchorClick).toHaveBeenCalledOnce();
  const anchor = anchorClick.mock.instances[0] as HTMLAnchorElement;
  const href = new URL(anchor.href);
  expect(href.pathname).toBe("/api/upload/file/generated-images/gen-image.png");
  expect(href.searchParams.get("file_token")).toBe("tok");
  expect(href.searchParams.get("proxy")).toBe("true");
  expect(anchor.download).toBe("gen-image.png");
});

test("browser upload downloads resolve the capability first and never fetch the file body", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", undefined);
  localStorage.setItem("access_token", "acct-viewer-download");
  request.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        url: "/api/upload/file/generated-images/clip.mp4?file_token=cap2",
      }),
    ),
  );
  await downloadUrl(
    "/api/upload/file/generated-images/clip.mp4",
    "clip.mp4",
  );
  expect(request).toHaveBeenCalledTimes(1);
  expect(fetch).not.toHaveBeenCalled();
  expect(anchorClick).toHaveBeenCalledOnce();
  const anchor = anchorClick.mock.instances[0] as HTMLAnchorElement;
  const href = new URL(anchor.href);
  expect(href.searchParams.get("file_token")).toBe("cap2");
  expect(href.searchParams.get("proxy")).toBe("true");
  expect(anchor.download).toBe("clip.mp4");
});

test("native app runtimes keep the prefetch path for cross-origin webview downloads", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", undefined);
  vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
  const share = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "share", {
    configurable: true,
    value: share,
  });
  await downloadUrl(
    "/api/upload/file/generated-images/native-shot.png?file_token=tok3",
    "native-shot.png",
  );
  await vi.waitFor(() =>
    expect(mobileFilesystem.writeFile).toHaveBeenCalledOnce(),
  );
  expect(fetch).toHaveBeenCalledOnce();
  expect(anchorClick).not.toHaveBeenCalled();
  expect(bridge.invoke).not.toHaveBeenCalled();
});
