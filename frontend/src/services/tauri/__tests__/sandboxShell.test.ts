import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: mocks.invoke,
}));

import {
  clearPairing,
  daemonProcessStatus,
  isShellAvailable,
  openLocalPath,
  readPairingPat,
  restartDaemon,
  savePairing,
  writeConfirmPolicy,
} from "../sandboxShell.ts";

function enterTauriShell(marker: "__TAURI__" | "__TAURI_INTERNALS__" = "__TAURI_INTERNALS__") {
  (globalThis as Record<string, unknown>)[marker] = {};
}

function leaveTauriShell() {
  delete (globalThis as Record<string, unknown>).__TAURI__;
  delete (globalThis as Record<string, unknown>).__TAURI_INTERNALS__;
}

/** 模拟 Capacitor 移动端原生运行时（isNativeAppRuntime 对其返回 true）。 */
function enterCapacitorNative(platform: "android" | "ios" = "android") {
  (globalThis as Record<string, unknown>).Capacitor = {
    isNativePlatform: () => true,
    getPlatform: () => platform,
  };
}

function leaveCapacitorNative() {
  delete (globalThis as Record<string, unknown>).Capacitor;
}

beforeEach(() => {
  mocks.invoke.mockReset();
  leaveTauriShell();
  leaveCapacitorNative();
});

afterEach(() => {
  leaveTauriShell();
  leaveCapacitorNative();
  vi.unstubAllGlobals();
});

test("isShellAvailable is false outside the desktop shell", () => {
  expect(isShellAvailable()).toBe(false);
});

test("isShellAvailable is true inside the Tauri shell", () => {
  enterTauriShell();
  expect(isShellAvailable()).toBe(true);
});

test("isShellAvailable is true with the __TAURI__ marker", () => {
  enterTauriShell("__TAURI__");
  expect(isShellAvailable()).toBe(true);
});

test("isShellAvailable is false inside the Capacitor android app", () => {
  enterCapacitorNative("android");
  expect(isShellAvailable()).toBe(false);
});

test("isShellAvailable is false inside the Capacitor iOS app", () => {
  enterCapacitorNative("ios");
  expect(isShellAvailable()).toBe(false);
});

test("isShellAvailable is false on a capacitor: webview origin", () => {
  vi.stubGlobal("window", {
    location: { protocol: "capacitor:", host: "localhost", hostname: "localhost" },
  });
  expect(isShellAvailable()).toBe(false);
});

test("isShellAvailable is true on a tauri: webview origin", () => {
  vi.stubGlobal("window", {
    location: { protocol: "tauri:", host: "localhost", hostname: "localhost" },
  });
  expect(isShellAvailable()).toBe(true);
});

test("isShellAvailable is true on the tauri.localhost origin (Windows)", () => {
  vi.stubGlobal("window", {
    location: { protocol: "https:", host: "tauri.localhost", hostname: "tauri.localhost" },
  });
  expect(isShellAvailable()).toBe(true);
});

test("isShellAvailable is false on a plain web origin", () => {
  vi.stubGlobal("window", {
    location: { protocol: "https:", host: "app.example.com", hostname: "app.example.com" },
  });
  expect(isShellAvailable()).toBe(false);
});

test("savePairing rejects with an explicit error outside the shell", async () => {
  await expect(
    savePairing({ serverUrl: "http://127.0.0.1:8000", pat: "pat", confirmPolicy: "all" }),
  ).rejects.toThrow(/desktop shell/i);
  expect(mocks.invoke).not.toHaveBeenCalled();
});

test("restartDaemon rejects outside the shell without invoking", async () => {
  await expect(restartDaemon()).rejects.toThrow(/desktop shell/i);
  expect(mocks.invoke).not.toHaveBeenCalled();
});

test("openLocalPath rejects outside the shell without invoking", async () => {
  await expect(openLocalPath("workspaces")).rejects.toThrow(/desktop shell/i);
  expect(mocks.invoke).not.toHaveBeenCalled();
});

test("savePairing invokes save_pairing with camelCase args", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await savePairing({
    serverUrl: "http://127.0.0.1:8000",
    pat: "pat-token",
    confirmPolicy: "commands",
    patId: "pat-uuid-1",
  });

  expect(mocks.invoke).toHaveBeenCalledWith("save_pairing", {
    serverUrl: "http://127.0.0.1:8000",
    pat: "pat-token",
    confirmPolicy: "commands",
    patId: "pat-uuid-1",
  });
});

test("savePairing forwards patId as undefined when omitted (legacy shape)", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await savePairing({
    serverUrl: "http://127.0.0.1:8000",
    pat: "pat-token",
    confirmPolicy: "all",
  });

  const args = mocks.invoke.mock.calls[0][1] as Record<string, unknown>;
  expect(args).toMatchObject({
    serverUrl: "http://127.0.0.1:8000",
    pat: "pat-token",
    confirmPolicy: "all",
  });
  // 未传 patId 时不携带该键（Rust Option<String> 收到 None）
  expect("patId" in args).toBe(false);
});

test("writeConfirmPolicy invokes write_confirm_policy with the policy", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await writeConfirmPolicy("commands");

  expect(mocks.invoke).toHaveBeenCalledWith("write_confirm_policy", {
    policy: "commands",
  });
});

test("clearPairing invokes clear_pairing with no args", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await clearPairing();

  expect(mocks.invoke).toHaveBeenCalledWith("clear_pairing", undefined);
});

test("readPairingPat resolves the stored PAT or null", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce("lc_pat_stored");
  await expect(readPairingPat()).resolves.toBe("lc_pat_stored");

  mocks.invoke.mockResolvedValueOnce(null);
  await expect(readPairingPat()).resolves.toBeNull();

  expect(mocks.invoke).toHaveBeenNthCalledWith(2, "read_pairing_pat", undefined);
});

test("writeConfirmPolicy and clearPairing reject outside the shell", async () => {
  await expect(writeConfirmPolicy("all")).rejects.toThrow(/desktop shell/i);
  await expect(clearPairing()).rejects.toThrow(/desktop shell/i);
  await expect(readPairingPat()).rejects.toThrow(/desktop shell/i);
  expect(mocks.invoke).not.toHaveBeenCalled();
});

test("restartDaemon invokes restart_daemon with no args", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await restartDaemon();

  expect(mocks.invoke).toHaveBeenCalledWith("restart_daemon", undefined);
});

test("daemonProcessStatus resolves the status string from the shell", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce("running");

  await expect(daemonProcessStatus()).resolves.toBe("running");
  expect(mocks.invoke).toHaveBeenCalledWith("daemon_process_status", undefined);
});

test("openLocalPath invokes open_local_path with the path payload", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await openLocalPath("audit");

  expect(mocks.invoke).toHaveBeenCalledWith("open_local_path", { path: "audit" });
});

test("shell command errors propagate to the caller", async () => {
  enterTauriShell();
  mocks.invoke.mockRejectedValueOnce(new Error("path must be inside ~/.lambchat"));

  await expect(openLocalPath("/etc/passwd")).rejects.toThrow(
    /path must be inside/,
  );
});
