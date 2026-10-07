/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useAutoUpdate } from "../useAutoUpdate";

const mocks = vi.hoisted(() => ({
  check: vi.fn(),
  backend: vi.fn(),
  linuxInfo: vi.fn(),
  linuxDownload: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(),
  apkStatus: vi.fn(),
  apkStart: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: mocks.check }));
vi.mock("../../services/api", () => ({
  versionApi: { checkForUpdates: mocks.backend },
  buildReleaseAssetDownloadUrl: (name: string) => `/assets/${name}`,
}));
vi.mock("../../services/capacitor/updateDownloader", () => ({
  UpdateDownloader: { status: mocks.apkStatus, start: mocks.apkStart },
}));
vi.mock("../../services/tauri/linuxUpdate", () => ({
  getLinuxInstallInfo: mocks.linuxInfo,
  subscribeLinuxUpdateProgress: async () => () => {},
  downloadLinuxPackage: mocks.linuxDownload,
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
afterEach(() => cleanup());

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
