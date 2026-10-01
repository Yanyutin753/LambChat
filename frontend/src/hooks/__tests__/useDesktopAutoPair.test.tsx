/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
import { useDesktopAutoPair } from "../useDesktopAutoPair";

const mocks = vi.hoisted(() => ({
  daemonProcessStatus: vi.fn(),
  readPairingPat: vi.fn(),
  restartDaemon: vi.fn(),
  savePairing: vi.fn(),
  createPairingPat: vi.fn(),
  getValidAccessToken: vi.fn(),
  notifySandboxStatusRefresh: vi.fn(),
  revokePairingPat: vi.fn(),
}));
vi.mock("../../services/tauri/sandboxShell", () => mocks);
vi.mock("../../services/api/sandbox", () => ({ sandboxApi: mocks }));
vi.mock("../../services/api/tokenManager", () => mocks);
vi.mock("../useSandboxStatus", () => mocks);
vi.mock("../../services/api/serverConfig", () => ({
  effectiveApiBase: () => "http://localhost:8000",
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.useFakeTimers();
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.getValidAccessToken.mockResolvedValue("refreshed-jwt");
  mocks.createPairingPat.mockResolvedValue({
    token: "new-pat",
    pat_id: "pat-id",
  });
});
afterEach(() => vi.useRealTimers());
const flush = () => act(() => vi.advanceTimersByTimeAsync(0));

test("desktop frame runs pairing independently of the settings page", () => {
  const source = readFileSync(
    "src/components/layout/TitleBar/DesktopTitlebarFrame.tsx",
    "utf8",
  );
  expect(source).toMatch(/useDesktopAutoPair\(user\?\.id\)/);
});

test("login pairs once with refreshed JWT and confirmation enabled", async () => {
  const { rerender } = renderHook(({ id }) => useDesktopAutoPair(id), {
    initialProps: { id: undefined as string | undefined },
  });
  await flush();
  expect(mocks.createPairingPat).not.toHaveBeenCalled();
  rerender({ id: "user-1" });
  await flush();
  expect(mocks.createPairingPat).toHaveBeenCalledWith("refreshed-jwt");
  expect(mocks.savePairing).toHaveBeenCalledWith({
    serverUrl: "http://localhost:8000",
    pat: "new-pat",
    patId: "pat-id",
    confirmPolicy: "all",
  });
  expect(mocks.restartDaemon).toHaveBeenCalledTimes(1);
  rerender({ id: "user-1" });
  await act(() => vi.advanceTimersByTimeAsync(30000));
  expect(mocks.createPairingPat).toHaveBeenCalledTimes(1);
});

test("existing pairing restarts a stopped daemon without replacing credentials", async () => {
  mocks.readPairingPat.mockResolvedValue("existing-pat");
  renderHook(() => useDesktopAutoPair("user-1"));
  await flush();
  expect(mocks.restartDaemon).toHaveBeenCalledTimes(1);
  expect(mocks.createPairingPat).not.toHaveBeenCalled();
  expect(mocks.savePairing).not.toHaveBeenCalled();
});

test("running paired daemon and unsupported platform are left alone", async () => {
  mocks.readPairingPat.mockResolvedValue("existing-pat");
  mocks.daemonProcessStatus.mockResolvedValue("running");
  const first = renderHook(() => useDesktopAutoPair("user-1"));
  await flush();
  first.unmount();
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.daemonProcessStatus.mockResolvedValue("unsupported");
  renderHook(() => useDesktopAutoPair("user-1"));
  await flush();
  expect(mocks.createPairingPat).not.toHaveBeenCalled();
  expect(mocks.restartDaemon).not.toHaveBeenCalled();
});

test("transient failure retries, but repeated failures stop after three attempts", async () => {
  mocks.createPairingPat.mockRejectedValue(new Error("offline"));
  renderHook(() => useDesktopAutoPair("user-1"));
  await flush();
  expect(mocks.createPairingPat).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(30000));
  expect(mocks.createPairingPat).toHaveBeenCalledTimes(3);
});

test("logout while minting revokes the unused PAT without saving it", async () => {
  let finish!: (value: { token: string; pat_id: string }) => void;
  mocks.createPairingPat.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { unmount } = renderHook(() => useDesktopAutoPair("user-1"));
  await flush();
  unmount();
  await act(async () => finish({ token: "unused", pat_id: "unused-id" }));
  expect(mocks.savePairing).not.toHaveBeenCalled();
  expect(mocks.revokePairingPat).toHaveBeenCalledWith("unused");
});
