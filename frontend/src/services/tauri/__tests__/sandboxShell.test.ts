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

function enterTauriShell(
  marker: "__TAURI__" | "__TAURI_INTERNALS__" = "__TAURI_INTERNALS__",
) {
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
    location: {
      protocol: "capacitor:",
      host: "localhost",
      hostname: "localhost",
    },
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
    location: {
      protocol: "https:",
      host: "tauri.localhost",
      hostname: "tauri.localhost",
    },
  });
  expect(isShellAvailable()).toBe(true);
});

test("isShellAvailable is false on a plain web origin", () => {
  vi.stubGlobal("window", {
    location: {
      protocol: "https:",
      host: "app.example.com",
      hostname: "app.example.com",
    },
  });
  expect(isShellAvailable()).toBe(false);
});

test("savePairing rejects with an explicit error outside the shell", async () => {
  await expect(
    savePairing({
      serverUrl: "http://127.0.0.1:8000",
      pat: "pat",
      confirmPolicy: "all",
    }),
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

  expect(mocks.invoke).toHaveBeenNthCalledWith(
    2,
    "read_pairing_pat",
    undefined,
  );
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

  expect(mocks.invoke).toHaveBeenCalledWith("open_local_path", {
    path: "audit",
  });
});

test("shell command errors propagate to the caller", async () => {
  enterTauriShell();
  mocks.invoke.mockRejectedValueOnce(
    new Error("path must be inside ~/.lambchat"),
  );

  await expect(openLocalPath("/etc/passwd")).rejects.toThrow(
    /path must be inside/,
  );
});

// ---------------------------------------------------------------------------
// subscribeDaemonStatus：Tauri 事件订阅替代 10s 轮询
// ---------------------------------------------------------------------------

const eventMocks = vi.hoisted(() => ({
  listen: vi.fn(),
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: eventMocks.listen,
}));

import { subscribeDaemonStatus } from "../sandboxShell.ts";

test("subscribeDaemonStatus forwards event payloads and unlisten is idempotent", async () => {
  enterTauriShell();
  const unlisten = vi.fn();
  let captured: ((event: { payload: unknown }) => void) | null = null;
  eventMocks.listen.mockImplementation(async (_name, handler) => {
    captured = handler;
    return unlisten;
  });

  const received: unknown[] = [];
  const cancel = await subscribeDaemonStatus((event) => received.push(event));
  expect(cancel).not.toBeNull();
  expect(eventMocks.listen).toHaveBeenCalledWith(
    "sandbox-daemon-status",
    expect.any(Function),
  );

  captured!({ payload: { running: true, unsupported: false, generation: 3, restarts: 1 } });
  expect(received).toEqual([
    { running: true, unsupported: false, generation: 3, restarts: 1 },
  ]);

  cancel!();
  cancel!(); // 幂等：第二次 no-op
  expect(unlisten).toHaveBeenCalledTimes(1);
  leaveTauriShell();
});

test("subscribeDaemonStatus returns null outside the shell", async () => {
  leaveTauriShell();
  eventMocks.listen.mockClear();
  expect(await subscribeDaemonStatus(() => {})).toBeNull();
  expect(eventMocks.listen).not.toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// 沙箱数据位置：sandbox_data_location / set / clear + 原生目录选择
// ---------------------------------------------------------------------------

const dialogMocks = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: dialogMocks.open }));

import {
  clearSandboxDataLocation,
  pickSandboxDirectory,
  readSandboxDataLocation,
  setSandboxDataLocation,
} from "../sandboxShell.ts";

const LOCATION = {
  root: "D:\\lambchat",
  customized: true,
  overrideConfigured: true,
};

test("readSandboxDataLocation resolves the typed location from the shell", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(LOCATION);

  await expect(readSandboxDataLocation()).resolves.toEqual(LOCATION);
  expect(mocks.invoke).toHaveBeenCalledWith("sandbox_data_location", undefined);
});

test("setSandboxDataLocation invokes set_sandbox_data_location with camelCase args", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await setSandboxDataLocation("D:\\lambchat", true);

  expect(mocks.invoke).toHaveBeenCalledWith("set_sandbox_data_location", {
    path: "D:\\lambchat",
    migrateData: true,
  });
});

test("clearSandboxDataLocation invokes clear_sandbox_data_location", async () => {
  enterTauriShell();
  mocks.invoke.mockResolvedValueOnce(undefined);

  await clearSandboxDataLocation();

  expect(mocks.invoke).toHaveBeenCalledWith(
    "clear_sandbox_data_location",
    undefined,
  );
});

test("data location commands reject outside the shell without invoking", async () => {
  await expect(readSandboxDataLocation()).rejects.toThrow(/desktop shell/i);
  await expect(setSandboxDataLocation("D:\\x", false)).rejects.toThrow(
    /desktop shell/i,
  );
  await expect(clearSandboxDataLocation()).rejects.toThrow(/desktop shell/i);
  expect(mocks.invoke).not.toHaveBeenCalled();
});

test("pickSandboxDirectory opens a native directory dialog in the shell", async () => {
  enterTauriShell();
  dialogMocks.open.mockResolvedValueOnce("E:\\sandbox-data");

  await expect(pickSandboxDirectory()).resolves.toBe("E:\\sandbox-data");
  expect(dialogMocks.open).toHaveBeenCalledWith({
    directory: true,
    multiple: false,
  });
});

test("pickSandboxDirectory maps multi-selection and cancel to null", async () => {
  enterTauriShell();
  dialogMocks.open.mockResolvedValueOnce(["E:\\a", "E:\\b"]);
  await expect(pickSandboxDirectory()).resolves.toBeNull();

  dialogMocks.open.mockResolvedValueOnce(null);
  await expect(pickSandboxDirectory()).resolves.toBeNull();
});

test("pickSandboxDirectory returns null outside the shell without the dialog", async () => {
  dialogMocks.open.mockClear();
  await expect(pickSandboxDirectory()).resolves.toBeNull();
  expect(dialogMocks.open).not.toHaveBeenCalled();
});
