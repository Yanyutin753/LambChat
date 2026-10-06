/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useAutoUpdate } from "../useAutoUpdate";

const mocks = vi.hoisted(() => ({
  check: vi.fn(),
  backend: vi.fn(),
  linuxInfo: vi.fn(),
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
  downloadLinuxPackage: async () => {},
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
      release_assets: [],
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
