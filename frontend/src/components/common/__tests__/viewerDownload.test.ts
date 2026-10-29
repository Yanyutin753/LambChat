/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Blob as NodeBlob } from "node:buffer";
import toast from "react-hot-toast";
import { downloadBlob, downloadUrl } from "../viewerDownload";

const bridge = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke }));
vi.mock("react-hot-toast", () => ({ default: { error: vi.fn() } }));
vi.mock("i18next", () => ({ default: { t: (key: string) => key } }));
let anchorClick: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  bridge.invoke.mockReset().mockResolvedValue(true);
  vi.mocked(toast.error).mockClear();
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
