/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const request = vi.hoisted(() => vi.fn());
vi.mock("../authenticatedRequest", () => ({ authenticatedRequest: request }));
vi.mock("../tokenManager", () => ({
  getValidAccessToken: async () => "test-access-token",
  redirectToLogin: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

class UploadXHR extends EventTarget {
  static sent: UploadXHR[] = [];
  static autoFinish = true;
  upload = new EventTarget();
  status = 200;
  responseText = JSON.stringify({
    key: "image/user/a.jpg",
    name: "a.tiff",
    type: "image",
    mime_type: "image/jpeg",
    size: 3,
    url: "/api/upload/file/image/user/a.jpg",
  });
  withCredentials = false;
  url = "";
  headers: Record<string, string> = {};
  open(_method: string, url: string) {
    this.url = url;
  }
  setRequestHeader(key: string, value: string) {
    this.headers[key] = value;
  }
  send() {
    UploadXHR.sent.push(this);
    if (UploadXHR.autoFinish) this.dispatchEvent(new Event("load"));
  }
  abort() {
    this.dispatchEvent(new Event("abort"));
  }
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE", "https://baked.example");
  localStorage.clear();
  localStorage.setItem("lambchat_server_url", "https://runtime.example");
  vi.stubGlobal("XMLHttpRequest", UploadXHR);
  UploadXHR.sent = [];
  UploadXHR.autoFinish = true;
  request
    .mockReset()
    .mockResolvedValue(new Response(JSON.stringify({ mode: "proxy" })));
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test.each(["macOS", "Windows", "Android", "iOS"])(
  "%s sends TIFF straight to its configured cloud server without direct initialization",
  async (platform) => {
    if (platform === "macOS" || platform === "Windows")
      vi.stubGlobal("__TAURI_INTERNALS__", {});
    else
      vi.stubGlobal("Capacitor", {
        isNativePlatform: () => true,
        getPlatform: () => platform.toLowerCase(),
      });
    const { uploadApi } = await import("../upload");
    const result = await uploadApi.uploadFile(
      new File(["abc"], "a.tiff", { type: "image/tiff" }),
    ).promise;
    expect(request).not.toHaveBeenCalled();
    expect(UploadXHR.sent[0].url).toBe(
      "https://runtime.example/api/upload/file?folder=uploads",
    );
    expect(UploadXHR.sent[0].headers.Authorization).toBe(
      "Bearer test-access-token",
    );
    expect(result.mimeType).toBe("image/jpeg");
  },
);

test("native proxy cancellation retains the direct-upload AbortError contract", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  UploadXHR.autoFinish = false;
  const { uploadApi } = await import("../upload");
  const handle = uploadApi.uploadFile(new File(["abc"], "a.tiff"));
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  await vi.waitFor(() => expect(UploadXHR.sent).toHaveLength(1));
  handle.abort();
  await rejected;
});

test.each([
  ["scan.TIFF", ""],
  ["scan.tif", "application/octet-stream"],
  ["photo.heic", "image/heic"],
  ["photo.jpg", "image/jpeg"],
  ["figure.png", "image/png"],
  ["image", "image/webp"],
])(
  "%s skips direct initialization before cloud image upload",
  async (name, type) => {
    const { uploadApi } = await import("../upload");
    await uploadApi.uploadFile(new File(["abc"], name, { type })).promise;
    expect(request).not.toHaveBeenCalled();
    expect(UploadXHR.sent).toHaveLength(1);
  },
);

test.each([
  ["animation.gif", "image/gif"],
  ["vector.SVG", ""],
  ["animation", "image/gif"],
  ["movie.mp4", "video/mp4"],
  ["report.pdf", "application/pdf"],
])("%s retains storage direct-upload negotiation", async (name, type) => {
  const { uploadApi } = await import("../upload");
  await uploadApi.uploadFile(new File(["abc"], name, { type })).promise;
  expect(request.mock.calls[0][0]).toContain("/api/upload/direct");
});

test("a silent hash worker releases TIFF to cloud upload after three seconds", async () => {
  vi.useFakeTimers();
  const terminate = vi.fn();
  vi.stubGlobal(
    "Worker",
    class {
      postMessage() {}
      terminate = terminate;
    },
  );
  const { uploadApi } = await import("../upload");
  const handle = uploadApi.uploadFile(
    new File(["abc"], "scan.tiff", { type: "image/tiff" }),
  );
  await vi.advanceTimersByTimeAsync(2999);
  expect(UploadXHR.sent).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(1);
  expect(terminate).toHaveBeenCalledOnce();
  expect(UploadXHR.sent).toHaveLength(1);
  expect(request).not.toHaveBeenCalled();
  await expect(handle.promise).resolves.toMatchObject({
    mimeType: "image/jpeg",
  });
  expect(vi.getTimerCount()).toBe(0);
});

test("native dedup checks use the same selected server as the upload", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  request.mockResolvedValue(new Response(JSON.stringify({ exists: false })));
  const { uploadApi } = await import("../upload");
  await uploadApi.checkFile("a".repeat(64), 3, "a.tiff", "image/tiff");
  expect(request.mock.calls[0][0]).toBe(
    "https://runtime.example/api/upload/check",
  );
});

test.each([401, 403])(
  "checkFile preserves authorization status %s",
  async (status) => {
    request.mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { code: "forbidden", message: "Denied" } }),
        { status },
      ),
    );
    const { uploadApi } = await import("../upload");
    await expect(
      uploadApi.checkFile("a".repeat(64), 3, "a.tiff", "image/tiff"),
    ).rejects.toMatchObject({ status });
  },
);

test("switching accounts during initialization never sends the old file via proxy", async () => {
  localStorage.setItem("access_token", "old-account");
  let initialize!: (response: Response) => void;
  request.mockReturnValue(
    new Promise<Response>((resolve) => {
      initialize = resolve;
    }),
  );
  const { uploadApi } = await import("../upload");
  const handle = uploadApi.uploadFile(
    new File(["private old file"], "a.mp4", { type: "video/mp4" }),
  );
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  await vi.waitFor(() => expect(request).toHaveBeenCalled());
  localStorage.setItem("access_token", "new-account");
  initialize(new Response(JSON.stringify({ mode: "proxy" })));
  await rejected;
  expect(UploadXHR.sent).toHaveLength(0);
});

test("switching accounts while proxy authentication waits cannot transmit bytes", async () => {
  localStorage.setItem("access_token", "old-account");
  const tokens = await import("../tokenManager");
  let authenticate!: (token: string) => void;
  const token = vi.spyOn(tokens, "getValidAccessToken").mockReturnValue(
    new Promise((resolve) => {
      authenticate = resolve;
    }),
  );
  const { uploadApi } = await import("../upload");
  const handle = uploadApi.uploadFile(new File(["private old file"], "a.tiff"));
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  await vi.waitFor(() => expect(token).toHaveBeenCalled());
  localStorage.setItem("access_token", "new-account");
  authenticate("new-account");
  await rejected;
  expect(UploadXHR.sent).toHaveLength(0);
});
