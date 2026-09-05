import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: mocks.invoke,
}));

import {
  daemonProcessStatus,
  isShellAvailable,
  openLocalPath,
  restartDaemon,
  savePairing,
} from "../sandboxShell.ts";

function enterTauriShell() {
  (globalThis as Record<string, unknown>).__TAURI_INTERNALS__ = {};
}

function leaveTauriShell() {
  delete (globalThis as Record<string, unknown>).__TAURI_INTERNALS__;
}

beforeEach(() => {
  mocks.invoke.mockReset();
  leaveTauriShell();
});

afterEach(() => {
  leaveTauriShell();
});

test("isShellAvailable is false outside the desktop shell", () => {
  expect(isShellAvailable()).toBe(false);
});

test("isShellAvailable is true inside the Tauri shell", () => {
  enterTauriShell();
  expect(isShellAvailable()).toBe(true);
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
  });

  expect(mocks.invoke).toHaveBeenCalledWith("save_pairing", {
    serverUrl: "http://127.0.0.1:8000",
    pat: "pat-token",
    confirmPolicy: "commands",
  });
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
