/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { VersionInfo } from "../../types";
import { setUpdateBusy, setUpdateChannel } from "../../utils/updateChannel";
import { useVersion } from "../useVersion";

const api = vi.hoisted(() => ({ get: vi.fn(), checkForUpdates: vi.fn() }));
vi.mock("../../services/api", () => ({ versionApi: api }));

function pendingVersion() {
  let resolve!: (info: VersionInfo) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<VersionInfo>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  setUpdateBusy(false);
  setUpdateChannel("stable");
  api.get.mockReset();
  api.checkForUpdates.mockReset();
});
afterEach(cleanup);

test("a slow initial response cannot overwrite a newer manual update check", async () => {
  const initial = pendingVersion();
  api.get.mockReturnValue(initial.promise);
  api.checkForUpdates.mockResolvedValue({ app_version: "3.0.0" });
  const { result } = renderHook(useVersion);
  await act(async () => {
    await result.current.checkForUpdates();
  });
  expect(result.current.versionInfo?.app_version).toBe("3.0.0");
  await act(async () => {
    initial.resolve({ app_version: "2.0.0" });
  });
  expect(result.current.versionInfo?.app_version).toBe("3.0.0");
  expect(result.current.isLoading).toBe(false);
});

test("a stale manual error cannot replace the latest successful result", async () => {
  api.get.mockResolvedValue({ app_version: "1.0.0" });
  const older = pendingVersion();
  const newer = pendingVersion();
  api.checkForUpdates
    .mockReturnValueOnce(older.promise)
    .mockReturnValueOnce(newer.promise);
  const { result } = renderHook(useVersion);
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  let first!: Promise<void>;
  let second!: Promise<void>;
  act(() => {
    first = result.current.checkForUpdates();
    second = result.current.checkForUpdates();
  });
  await act(async () => {
    newer.resolve({ app_version: "3.0.0" });
    await second;
  });
  await act(async () => {
    older.reject(new Error("stale failure"));
    await first;
  });
  expect(result.current.versionInfo?.app_version).toBe("3.0.0");
  expect(result.current.error).toBeNull();
  expect(result.current.isLoading).toBe(false);
});

test("switching channels invalidates all older requests without reusing their sequence", async () => {
  const stable = pendingVersion();
  const dev = pendingVersion();
  const older = pendingVersion();
  const latestStable = pendingVersion();
  api.get.mockReturnValueOnce(stable.promise).mockReturnValueOnce(dev.promise);
  api.checkForUpdates
    .mockReturnValueOnce(older.promise)
    .mockReturnValueOnce(latestStable.promise);
  const { result } = renderHook(useVersion);
  let first!: Promise<void>;
  let second!: Promise<void>;
  act(() => {
    first = result.current.checkForUpdates();
    second = result.current.checkForUpdates();
    setUpdateChannel("dev");
  });
  await act(async () => {
    latestStable.resolve({ app_version: "stable-late" });
    older.reject(new Error("stable error"));
    stable.resolve({ app_version: "stable-initial" });
    await Promise.all([first, second]);
  });
  expect(result.current.versionInfo).toBeNull();
  expect(result.current.error).toBeNull();
  expect(result.current.isLoading).toBe(true);
  await act(async () => {
    dev.resolve({ app_version: "dev-current" });
  });
  expect(result.current.versionInfo?.app_version).toBe("dev-current");
  expect(result.current.isLoading).toBe(false);
});
