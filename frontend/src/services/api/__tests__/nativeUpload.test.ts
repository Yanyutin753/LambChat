/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const request = vi.hoisted(() => vi.fn());
vi.mock("../authenticatedRequest", () => ({ authenticatedRequest: request }));
vi.mock("../tokenManager", () => ({
  getValidAccessToken: async () => "test-access-token",
  redirectToLogin: vi.fn(), refreshAccessToken: vi.fn(),
}));

class UploadXHR extends EventTarget {
  static sent: UploadXHR[] = [];
  static autoFinish = true;
  upload = new EventTarget();
  status = 200;
  responseText = JSON.stringify({ key: "image/user/a.jpg", name: "a.tiff", type: "image",
    mime_type: "image/jpeg", size: 3, url: "/api/upload/file/image/user/a.jpg" });
  withCredentials = false;
  url = "";
  headers: Record<string, string> = {};
  open(_method: string, url: string) { this.url = url; }
  setRequestHeader(key: string, value: string) { this.headers[key] = value; }
  send() {
    UploadXHR.sent.push(this);
    if (UploadXHR.autoFinish) this.dispatchEvent(new Event("load"));
  }
  abort() { this.dispatchEvent(new Event("abort")); }
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE", "https://baked.example");
  localStorage.clear();
  localStorage.setItem("lambchat_server_url", "https://runtime.example");
  vi.stubGlobal("XMLHttpRequest", UploadXHR);
  UploadXHR.sent = [];
  UploadXHR.autoFinish = true;
  request.mockReset().mockResolvedValue(new Response(JSON.stringify({ mode: "proxy" })));
});
afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test.each(["macOS", "Windows", "Android", "iOS"])(
  "%s uses the configured server for initialization and image-transcode fallback", async (platform) => {
    if (platform === "macOS" || platform === "Windows") vi.stubGlobal("__TAURI_INTERNALS__", {});
    else vi.stubGlobal("Capacitor", { isNativePlatform: () => true, getPlatform: () => platform.toLowerCase() });
    const { uploadApi } = await import("../upload");
    const result = await uploadApi.uploadFile(new File(["abc"], "a.tiff", { type: "image/tiff" })).promise;
    expect(request.mock.calls[0][0]).toBe("https://runtime.example/api/upload/direct");
    expect(UploadXHR.sent[0].url).toBe("https://runtime.example/api/upload/file?folder=uploads");
    expect(UploadXHR.sent[0].headers.Authorization).toBe("Bearer test-access-token");
    expect(result.mimeType).toBe("image/jpeg");
  },
);

test("native proxy cancellation retains the direct-upload AbortError contract", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  UploadXHR.autoFinish = false;
  const { uploadApi } = await import("../upload");
  const handle = uploadApi.uploadFile(new File(["abc"], "a.tiff"));
  const rejected = expect(handle.promise).rejects.toMatchObject({ name: "AbortError" });
  await vi.waitFor(() => expect(UploadXHR.sent).toHaveLength(1));
  handle.abort();
  await rejected;
});
