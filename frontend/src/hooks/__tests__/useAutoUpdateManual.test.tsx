/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useAutoUpdate } from "../useAutoUpdate";

const mocks = vi.hoisted(() => ({
  check: vi.fn(),
  relaunch: vi.fn(),
  backend: vi.fn(),
  linuxInfo: vi.fn(),
  linuxDownload: vi.fn(),
  linuxInstall: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(),
  apkStatus: vi.fn(),
  apkStart: vi.fn(),
  apkProgress: vi.fn(),
  apkCancel: vi.fn(),
  apkCleanup: vi.fn(),
  installApk: vi.fn(),
  stat: vi.fn(),
  writeFile: vi.fn(),
  appendFile: vi.fn(),
  deleteFile: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: mocks.check }));
vi.mock("@tauri-apps/plugin-process", () => ({ relaunch: mocks.relaunch }));
vi.mock("../../services/api", () => ({
  versionApi: { checkForUpdates: mocks.backend },
  buildReleaseAssetDownloadUrl: (name: string) => `/assets/${name}`,
}));
vi.mock("../../services/capacitor/updateDownloader", () => ({
  UpdateDownloader: {
    status: mocks.apkStatus,
    start: mocks.apkStart,
    progress: mocks.apkProgress,
    cancel: mocks.apkCancel,
    cleanup: mocks.apkCleanup,
  },
}));
vi.mock("../../services/capacitor/apkInstaller", () => ({
  ApkInstaller: { installApk: mocks.installApk },
}));
vi.mock("@capacitor/filesystem", () => ({
  Filesystem: mocks,
  Directory: { Cache: "CACHE" },
}));
vi.mock("../../services/tauri/linuxUpdate", () => ({
  getLinuxInstallInfo: mocks.linuxInfo,
  subscribeLinuxUpdateProgress: async () => () => {},
  downloadLinuxPackage: mocks.linuxDownload,
  installLinuxPackage: mocks.linuxInstall,
}));
vi.mock("react-hot-toast", () => ({ toast: mocks }));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  Object.defineProperty(navigator, "platform", {
    configurable: true,
    value: "MacIntel",
  });
  Object.defineProperty(navigator, "userAgent", {
    configurable: true,
    value: "Macintosh",
  });
  Object.assign(window, { __TAURI_INTERNALS__: {}, Capacitor: undefined });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("native checks and downloads have separate bounded network timeouts", async () => {
  const download = vi.fn().mockResolvedValue(undefined);
  mocks.check.mockResolvedValue({
    available: true,
    version: "9.0.0",
    download,
  });
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  expect(mocks.check).toHaveBeenCalledWith(
    expect.objectContaining({ timeout: 30_000 }),
  );
  expect(download).toHaveBeenCalledWith(expect.any(Function), {
    timeout: 30 * 60_000,
  });
});

test.each(["skipped", "failed", "dismissed"])(
  "%s native update releases its resource",
  async (scenario) => {
    const close = vi.fn().mockResolvedValue(undefined);
    if (scenario === "skipped")
      localStorage.setItem("lambchat:skipped-update-versions", '["9.0.0"]');
    mocks.check.mockResolvedValue({
      available: true,
      version: "9.0.0",
      close,
      download:
        scenario === "failed"
          ? vi.fn().mockRejectedValue(new Error("offline"))
          : async () => {},
    });
    const { result } = renderHook(() => useAutoUpdate());
    await act(async () => {
      if (scenario === "skipped") {
        window.dispatchEvent(new Event("focus"));
      } else {
        await result.current.checkNow();
      }
    });
    if (scenario === "dismissed") act(() => result.current.skipThisVersion());
    expect(close).toHaveBeenCalledOnce();
  },
);

async function androidUpdate() {
  Object.assign(window, {
    __TAURI_INTERNALS__: undefined,
    Capacitor: { getPlatform: () => "android" },
  });
  mocks.backend.mockResolvedValue({
    has_update: true,
    latest_version: "9.0.0",
    release_assets: [{ name: "update.apk", size: 10 }],
  });
  mocks.apkStatus.mockResolvedValue({ exists: false });
  mocks.apkCancel.mockResolvedValue(undefined);
  mocks.apkCleanup.mockResolvedValue(undefined);
  mocks.stat.mockRejectedValue(new Error("ENOENT"));
  mocks.writeFile.mockResolvedValue({ uri: "file:///update.apk" });
  mocks.appendFile.mockResolvedValue(undefined);
  mocks.deleteFile.mockResolvedValue(undefined);
  const hook = renderHook(() => useAutoUpdate());
  await act(async () => {
    await hook.result.current.checkNow();
  });
  return hook;
}

test("Android stalled native download is cancelled before fallback and releases busy state", async () => {
  vi.useFakeTimers();
  const { result } = await androidUpdate();
  mocks.apkStart.mockResolvedValue({ downloadId: "17" });
  mocks.apkProgress.mockResolvedValue({
    status: "paused",
    bytesSoFar: 0,
    totalBytes: 10,
  });
  const fallback = vi.fn(async () => {
    expect(mocks.apkCancel).toHaveBeenCalledWith({ downloadId: "17" });
    throw new TypeError("offline");
  });
  vi.stubGlobal("fetch", fallback);
  let pending!: Promise<void>;
  await act(async () => {
    pending = result.current.startUpdate();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_400);
  });
  expect(fallback).toHaveBeenCalledOnce();
  await pending;
  expect(result.current.state.downloading).toBe(false);
});

test("Android truncated fallback download is removed and never installed", async () => {
  const { result } = await androidUpdate();
  mocks.apkStart.mockRejectedValue(new Error("unavailable"));
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2]))),
  );
  await act(async () => {
    await result.current.startUpdate();
  });
  expect(mocks.installApk).not.toHaveBeenCalled();
  expect(mocks.deleteFile).toHaveBeenCalledWith({
    path: "update.apk",
    directory: "CACHE",
  });
  expect(result.current.state.downloading).toBe(false);
  expect(result.current.state.error).toBeTruthy();
});

test("an old Android shell that cannot cancel never starts a competing fallback", async () => {
  vi.useFakeTimers();
  const { result } = await androidUpdate();
  mocks.apkStart.mockResolvedValue({ downloadId: "17" });
  mocks.apkProgress.mockResolvedValue({
    status: "paused",
    bytesSoFar: 0,
    totalBytes: 10,
  });
  mocks.apkCancel.mockRejectedValue(new Error("UNIMPLEMENTED"));
  const fallback = vi.fn();
  vi.stubGlobal("fetch", fallback);
  let pending!: Promise<void>;
  await act(async () => {
    pending = result.current.startUpdate();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_400);
  });
  expect(result.current.state.downloading).toBe(false);
  await pending;
  expect(fallback).not.toHaveBeenCalled();
  expect(result.current.state.error).toBeTruthy();
});

test("Android progress renews the idle budget and a complete native package installs", async () => {
  vi.useFakeTimers();
  const { result } = await androidUpdate();
  mocks.installApk.mockResolvedValue({ status: "installer" });
  mocks.apkStart.mockResolvedValue({ downloadId: "17" });
  mocks.apkProgress.mockResolvedValue({
    status: "running",
    bytesSoFar: 1,
    totalBytes: 10,
  });
  let pending!: Promise<void>;
  await act(async () => {
    pending = result.current.startUpdate();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(59_000);
  });
  mocks.apkProgress.mockResolvedValue({
    status: "running",
    bytesSoFar: 5,
    totalBytes: 10,
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(59_000);
  });
  expect(result.current.state.downloading).toBe(true);
  mocks.apkProgress.mockResolvedValue({
    status: "success",
    bytesSoFar: 10,
    totalBytes: 10,
    localUri: "file:///update.apk",
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
    await pending;
  });
  expect(mocks.installApk).toHaveBeenCalledWith({ path: "file:///update.apk" });
  expect(mocks.apkCancel).not.toHaveBeenCalled();
  expect(result.current.state.readyToInstall).toBe(true);
});

test("a complete Android fallback package remains cached and installs", async () => {
  const { result } = await androidUpdate();
  mocks.apkStart.mockRejectedValue(new Error("unavailable"));
  mocks.installApk.mockResolvedValue({ status: "installer" });
  const response = new Response(new Uint8Array(10));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  await act(async () => {
    await result.current.startUpdate();
  });
  expect(mocks.installApk).toHaveBeenCalledWith({ path: "file:///update.apk" });
  expect(mocks.deleteFile).not.toHaveBeenCalled();
  expect(response.body?.locked).toBe(false);
});

test("Android fallback stops a stalled response body and releases its reader", async () => {
  vi.useFakeTimers();
  const { result } = await androidUpdate();
  mocks.apkStart.mockRejectedValue(new Error("unavailable"));
  let response!: Response;
  vi.stubGlobal(
    "fetch",
    vi.fn((_url, init) => {
      const stream = new ReadableStream({
        start(controller) {
          init.signal?.addEventListener("abort", () =>
            controller.error(init.signal.reason),
          );
        },
      });
      response = new Response(stream);
      return Promise.resolve(response);
    }),
  );
  let pending!: Promise<void>;
  await act(async () => {
    pending = result.current.startUpdate();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });
  expect(result.current.state.downloading).toBe(false);
  await pending;
  expect(response.body?.locked).toBe(false);
});

test("Android rechecks preserve an active download and prevent duplicate starts", async () => {
  Object.assign(window, {
    __TAURI_INTERNALS__: undefined,
    Capacitor: { getPlatform: () => "android" },
  });
  mocks.backend.mockResolvedValue({
    has_update: true,
    latest_version: "9.0.0",
    release_assets: [{ name: "LambChat.apk", size: 100 }],
  });
  mocks.apkStatus.mockResolvedValue({ exists: false });
  mocks.apkStart.mockReturnValue(new Promise(() => {}));
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  await act(async () => {
    void result.current.startUpdate();
    await vi.waitFor(() => expect(mocks.apkStart).toHaveBeenCalledOnce());
  });
  expect(result.current.state.downloading).toBe(true);
  mocks.backend.mockResolvedValue({
    has_update: true,
    latest_version: "9.1.0",
    release_assets: [{ name: "LambChat-new.apk", size: 200 }],
  });
  await act(async () => {
    await result.current.checkNow();
  });
  expect(result.current.state.downloading).toBe(true);
  expect(result.current.state.version).toBe("9.0.0");
  await act(async () => {
    void result.current.startUpdate();
  });
  expect(mocks.apkStart).toHaveBeenCalledOnce();
});

test("a newly discovered desktop update never reports up-to-date before React renders", async () => {
  mocks.check.mockResolvedValue({
    available: true,
    version: "9.0.0",
    download: async () => {},
  });
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  expect(result.current.state.version).toBe("9.0.0");
  expect(mocks.success).toHaveBeenCalledWith(
    expect.stringContaining("9.0.0"),
    expect.anything(),
  );
});

test.each(["android", "ios", "linux"])(
  "%s manual checks report the discovered version directly",
  async (platform) => {
    if (platform === "linux") {
      Object.defineProperty(navigator, "platform", {
        configurable: true,
        value: "Linux x86_64",
      });
      mocks.linuxInfo.mockResolvedValue({ source: "unknown", arch: "x86_64" });
    } else {
      Object.assign(window, {
        __TAURI_INTERNALS__: undefined,
        Capacitor: { getPlatform: () => platform },
      });
    }
    mocks.backend.mockResolvedValue({
      has_update: true,
      latest_version: "9.0.0",
      published_at: "2026-10-06T19:35:00Z",
      release_assets: [],
    });
    const { result } = renderHook(() => useAutoUpdate());
    await act(async () => {
      await result.current.checkNow();
    });
    expect(result.current.state.version).toBe("9.0.0");
    expect(result.current.state.publishedAt).toBe("2026-10-06T19:35:00Z");
    expect(mocks.success).toHaveBeenCalledWith(
      expect.stringContaining("9.0.0"),
      expect.anything(),
    );
  },
);

test("a failed native check reports failure rather than latest", async () => {
  mocks.check.mockRejectedValue(new Error("offline"));
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  expect(mocks.error).toHaveBeenCalled();
  expect(mocks.success).not.toHaveBeenCalled();
});

test("repeated manual clicks share one pending native check", async () => {
  let finish!: (value: null) => void;
  mocks.check.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    const first = result.current.checkNow();
    const second = result.current.checkNow();
    await vi.waitFor(() => expect(mocks.check).toHaveBeenCalled());
    finish(null);
    await Promise.all([first, second]);
  });
  expect(mocks.check).toHaveBeenCalledTimes(1);
  expect(mocks.success).toHaveBeenCalledTimes(1);
});

test.each([null, { available: true, version: "9.1.0", download: vi.fn() }])(
  "desktop rechecks keep the downloaded package version when the response is %j",
  async (response) => {
    mocks.check.mockResolvedValueOnce({
      available: true,
      version: "9.0.0",
      download: async () => {},
    });
    const { result } = renderHook(() => useAutoUpdate());
    await act(async () => {
      await result.current.checkNow();
    });
    expect(result.current.state.readyToInstall).toBe(true);
    mocks.success.mockClear();
    mocks.check.mockResolvedValueOnce(response);
    await act(async () => {
      await result.current.checkNow();
    });
    expect(result.current.state.version).toBe("9.0.0");
    expect(result.current.state.readyToInstall).toBe(true);
    expect(mocks.success).toHaveBeenCalledWith(
      expect.stringContaining("9.0.0"),
      expect.anything(),
    );
  },
);

test("native rechecks close ignored updates without closing the install target", async () => {
  const originalClose = vi.fn();
  const ignoredClose = vi.fn();
  mocks.check.mockResolvedValueOnce({
    available: true,
    version: "9.0.0",
    download: async () => {},
    close: originalClose,
  });
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  mocks.check.mockResolvedValueOnce({
    available: true,
    version: "9.1.0",
    close: ignoredClose,
  });
  await act(async () => {
    await result.current.checkNow();
  });
  expect(ignoredClose).toHaveBeenCalledOnce();
  expect(originalClose).not.toHaveBeenCalled();
});

test.each(["android", "ios", "linux"])(
  "%s missing release metadata reports check failure rather than latest",
  async (platform) => {
    if (platform === "linux") {
      Object.defineProperty(navigator, "platform", {
        configurable: true,
        value: "Linux x86_64",
      });
      mocks.linuxInfo.mockResolvedValue({ source: "unknown", arch: "x86_64" });
    } else {
      Object.assign(window, {
        __TAURI_INTERNALS__: undefined,
        Capacitor: { getPlatform: () => platform },
      });
    }
    mocks.backend.mockResolvedValue({
      has_update: false,
      latest_version: null,
    });
    const { result } = renderHook(() => useAutoUpdate());
    await act(async () => {
      await result.current.checkNow();
    });
    expect(mocks.error).toHaveBeenCalled();
    expect(mocks.success).not.toHaveBeenCalled();
  },
);

test("Linux rechecks do not relabel an active package download", async () => {
  Object.defineProperty(navigator, "platform", {
    configurable: true,
    value: "Linux x86_64",
  });
  mocks.linuxInfo.mockResolvedValue({ source: "deb", arch: "x86_64" });
  mocks.linuxDownload.mockReturnValue(new Promise(() => {}));
  const release = (version: string) => ({
    has_update: true,
    latest_version: version,
    release_assets: [{ name: `LambChat-v${version}-Linux-x86_64.deb` }],
  });
  mocks.backend.mockResolvedValue(release("9.0.0"));
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  expect(result.current.state.downloading).toBe(true);
  mocks.success.mockClear();
  mocks.backend.mockResolvedValue(release("9.1.0"));
  await act(async () => {
    await result.current.checkNow();
  });
  expect(result.current.state.version).toBe("9.0.0");
  expect(mocks.linuxDownload).toHaveBeenCalledOnce();
  expect(mocks.success).toHaveBeenCalledWith(
    expect.stringContaining("9.0.0"),
    expect.anything(),
  );
});

test.each([false, true])(
  "Android cached APK remains the install target during rechecks (newer=%s)",
  async (newer) => {
    Object.assign(window, {
      __TAURI_INTERNALS__: undefined,
      Capacitor: { getPlatform: () => "android" },
    });
    mocks.apkStatus.mockResolvedValue({ exists: true, size: 100 });
    mocks.backend.mockResolvedValue({
      has_update: true,
      latest_version: "9.0.0",
      release_assets: [{ name: "old.apk", size: 100 }],
    });
    const { result } = renderHook(() => useAutoUpdate());
    await act(async () => {
      await result.current.checkNow();
    });
    expect(result.current.state.readyToInstall).toBe(true);
    mocks.success.mockClear();
    mocks.backend.mockResolvedValue({
      has_update: newer,
      latest_version: newer ? "9.1.0" : "9.0.0",
      release_assets: [{ name: "new.apk", size: 200 }],
    });
    await act(async () => {
      await result.current.checkNow();
    });
    expect(result.current.state.version).toBe("9.0.0");
    expect(result.current.state.releaseAssets[0].name).toBe("old.apk");
    expect(mocks.success).toHaveBeenCalledWith(
      expect.stringContaining("9.0.0"),
      expect.anything(),
    );
  },
);

test("a ready native target is known even before the next React render", async () => {
  mocks.check
    .mockResolvedValueOnce({
      available: true,
      version: "9.0.0",
      download: async () => {},
    })
    .mockResolvedValueOnce(null);
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
    mocks.success.mockClear();
    await result.current.checkNow();
  });
  expect(mocks.success).toHaveBeenCalledWith(
    expect.stringContaining("9.0.0"),
    expect.anything(),
  );
});

test("channel switch discards a stale native check before it can download", async () => {
  const { setUpdateChannel } = await import("../../utils/updateChannel");
  let resolve!: (value: unknown) => void;
  mocks.check.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  mocks.check.mockResolvedValue(null);
  const download = vi.fn();
  const close = vi.fn();
  const { result } = renderHook(() => useAutoUpdate());
  let pending!: Promise<void>;
  await act(async () => {
    pending = result.current.checkNow();
  });
  await act(async () => {
    setUpdateChannel("dev");
  });
  await act(async () => {
    resolve({ available: true, version: "9.0.0", download, close });
    await pending;
  });
  expect(download).not.toHaveBeenCalled();
  expect(result.current.state.available).toBe(false);
  expect(close).toHaveBeenCalled();
  act(() => {
    setUpdateChannel("stable");
  });
});

test("restart retry does not reinstall a consumed native download", async () => {
  const install = vi.fn().mockResolvedValue(undefined);
  const close = vi.fn().mockResolvedValue(undefined);
  mocks.check.mockResolvedValue({
    available: true,
    version: "9.0.0",
    download: async () => {},
    install,
    close,
  });
  mocks.relaunch
    .mockRejectedValueOnce(new Error("restart failed"))
    .mockResolvedValue(undefined);
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  await act(async () => {
    await result.current.startUpdate();
  });
  expect(result.current.state.error).toContain("restart failed");
  await act(async () => {
    await result.current.startUpdate();
  });
  expect(install).toHaveBeenCalledOnce();
  expect(mocks.relaunch).toHaveBeenCalledTimes(2);
});

test("installing a cached update prevents skipping or duplicate installation", async () => {
  let finish!: () => void;
  const install = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  const close = vi.fn().mockResolvedValue(undefined);
  mocks.check.mockResolvedValue({
    available: true,
    version: "9.0.0",
    download: async () => {},
    install,
    close,
  });
  mocks.relaunch.mockResolvedValue(undefined);
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  let installing!: Promise<void>;
  await act(async () => {
    installing = result.current.startUpdate();
  });
  expect(result.current.state.downloading).toBe(true);
  await act(async () => {
    result.current.skipThisVersion();
    await result.current.startUpdate();
  });
  expect(close).not.toHaveBeenCalled();
  expect(result.current.state.available).toBe(true);
  expect(install).toHaveBeenCalledOnce();
  await act(async () => {
    finish();
    await installing;
  });
});

test("failed native replacement remains retryable and releases installation busy state", async () => {
  const install = vi
    .fn()
    .mockRejectedValueOnce(new Error("replace failed"))
    .mockResolvedValue(undefined);
  mocks.check.mockResolvedValue({
    available: true,
    version: "9.0.0",
    download: async () => {},
    install,
    close: vi.fn().mockResolvedValue(undefined),
  });
  mocks.relaunch.mockResolvedValue(undefined);
  const { result } = renderHook(() => useAutoUpdate());
  await act(async () => {
    await result.current.checkNow();
  });
  await act(async () => {
    await result.current.startUpdate();
  });
  expect(result.current.state.downloading).toBe(false);
  expect(result.current.state.readyToInstall).toBe(true);
  expect(mocks.relaunch).not.toHaveBeenCalled();
  await act(async () => {
    await result.current.startUpdate();
  });
  expect(install).toHaveBeenCalledTimes(2);
  expect(result.current.state.error).toBeNull();
  expect(mocks.relaunch).toHaveBeenCalledOnce();
});

test.each(["linux", "foreground"])(
  "%s restart retry never repeats a successful installation",
  async (mode) => {
    const install = vi.fn().mockResolvedValue(undefined);
    if (mode === "linux") {
      Object.defineProperty(navigator, "platform", {
        configurable: true,
        value: "Linux x86_64",
      });
      mocks.linuxInfo.mockResolvedValue({ source: "deb", arch: "x86_64" });
      mocks.linuxDownload.mockResolvedValue(true);
      mocks.linuxInstall.mockImplementation(install);
      mocks.backend.mockResolvedValue({
        has_update: true,
        latest_version: "9.0.0",
        release_assets: [{ name: "LambChat-v9.0.0-Linux-x86_64.deb" }],
      });
    } else {
      mocks.check.mockResolvedValue({
        available: true,
        version: "9.0.0",
        download: vi.fn().mockRejectedValue(new Error("background failed")),
        downloadAndInstall: install,
        close: vi.fn().mockResolvedValue(undefined),
      });
    }
    mocks.relaunch
      .mockRejectedValueOnce(new Error("restart failed"))
      .mockResolvedValue(undefined);
    const { result } = renderHook(() => useAutoUpdate());
    await act(async () => {
      await result.current.checkNow();
    });
    await act(async () => {
      await result.current.startUpdate();
    });
    expect(result.current.state.error).toContain("restart failed");
    await act(async () => {
      await result.current.startUpdate();
    });
    expect(install).toHaveBeenCalledOnce();
    expect(mocks.relaunch).toHaveBeenCalledTimes(2);
  },
);
