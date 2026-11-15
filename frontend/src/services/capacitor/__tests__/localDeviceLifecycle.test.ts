import { beforeEach, expect, test, vi } from "vitest";
const mocks = vi.hoisted(() => ({ enabled: true, invoke: vi.fn() }));
vi.mock("../localDevice", () => ({
  isAndroidLocalDevice: () => mocks.enabled,
  invokeAndroidDevice: mocks.invoke,
}));
import {
  savePairing,
  readPairingPat,
  readMachineId,
  writeConfirmPolicy,
  restartDaemon,
  clearPairing,
  isShellAvailable,
} from "../../tauri/sandboxShell";
beforeEach(() => {
  mocks.enabled = true;
  mocks.invoke.mockReset().mockResolvedValue(undefined);
});

test("Android lifecycle uses its native bridge without enabling desktop APIs", async () => {
  expect(isShellAvailable()).toBe(false);
  await savePairing({
    serverUrl: "https://chat.example",
    pat: "private-token",
    confirmPolicy: "all",
  });
  expect(mocks.invoke).toHaveBeenLastCalledWith("save_pairing", {
    serverUrl: "https://chat.example",
    pat: "private-token",
    confirmPolicy: "all",
  });
  await readPairingPat("https://chat.example");
  expect(mocks.invoke).toHaveBeenLastCalledWith("read_pairing_pat", {
    serverUrl: "https://chat.example",
  });
  await readMachineId();
  expect(mocks.invoke).toHaveBeenLastCalledWith("read_machine_id", undefined);
  await writeConfirmPolicy("commands");
  expect(mocks.invoke).toHaveBeenLastCalledWith("write_confirm_policy", {
    policy: "commands",
  });
  await restartDaemon();
  expect(mocks.invoke).toHaveBeenLastCalledWith("restart_daemon", undefined);
  await clearPairing();
  expect(mocks.invoke).toHaveBeenLastCalledWith("clear_pairing", undefined);
});

test("missing mobile bridge refuses pairing rather than falling into a desktop call", async () => {
  mocks.enabled = false;
  await expect(
    savePairing({
      serverUrl: "https://chat.example",
      pat: "private-token",
      confirmPolicy: "all",
    }),
  ).rejects.toThrow("desktop shell");
  expect(mocks.invoke).not.toHaveBeenCalled();
});
