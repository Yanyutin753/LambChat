/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

const mocks = vi.hoisted(() => ({
  isShellAvailable: vi.fn(),
  daemonProcessStatus: vi.fn(),
  savePairing: vi.fn(),
  restartDaemon: vi.fn(),
  openLocalPath: vi.fn(),
  getStatus: vi.fn(),
  createPat: vi.fn(),
  login: vi.fn(),
}));

vi.mock("../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: mocks.isShellAvailable,
  daemonProcessStatus: mocks.daemonProcessStatus,
  savePairing: mocks.savePairing,
  restartDaemon: mocks.restartDaemon,
  openLocalPath: mocks.openLocalPath,
}));

vi.mock("../../../services/api/sandbox", () => ({
  DESKTOP_SHELL_PAT_NAME: "lambchat-desktop-shell",
  sandboxApi: {
    getStatus: mocks.getStatus,
    createPat: mocks.createPat,
  },
}));

vi.mock("../../../services/api/auth", () => ({
  authApi: { login: mocks.login },
}));

vi.mock("react-hot-toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { LocalSandboxSection } from "../LocalSandboxSection";

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
});

test("pure web renders only the desktop-required hint", async () => {
  mocks.isShellAvailable.mockReturnValue(false);
  mocks.getStatus.mockResolvedValue({ online: false });

  render(<LocalSandboxSection />);

  expect(
    screen.getByText(/requires the LambChat desktop app/i),
  ).toBeInTheDocument();
  // 纯 web：不渲染配对表单，也不探测壳内进程
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
  expect(mocks.daemonProcessStatus).not.toHaveBeenCalled();
});

test("pairing form runs login → pat → savePairing → restart in order", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.login.mockResolvedValue({
    access_token: "jwt",
    refresh_token: "r",
    token_type: "bearer",
  });
  mocks.createPat.mockResolvedValue({ token: "lcpat_pair", pat_id: "p1" });
  mocks.savePairing.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  const username = await screen.findByPlaceholderText(/username/i);
  fireEvent.change(username, { target: { value: "m1_smoke" } });
  fireEvent.change(screen.getByPlaceholderText(/password/i), {
    target: { value: "secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: /pair and start/i }));

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalled());

  expect(mocks.login).toHaveBeenCalledWith({
    username: "m1_smoke",
    password: "secret",
  });
  expect(mocks.createPat).toHaveBeenCalledWith("lambchat-desktop-shell");
  expect(mocks.savePairing).toHaveBeenCalledWith({
    serverUrl: expect.stringMatching(/^https?:\/\//),
    pat: "lcpat_pair",
    confirmPolicy: "all",
  });

  // 配对链路完成：login → createPat → savePairing → restartDaemon
  const [loginAt, patAt, saveAt, restartAt] = [
    mocks.login.mock.invocationCallOrder[0],
    mocks.createPat.mock.invocationCallOrder[0],
    mocks.savePairing.mock.invocationCallOrder[0],
    mocks.restartDaemon.mock.invocationCallOrder[0],
  ];
  expect(loginAt).toBeLessThan(patAt);
  expect(patAt).toBeLessThan(saveAt);
  expect(saveAt).toBeLessThan(restartAt);

  // 配对后触发状态刷新事件（hook 重新拉取）
  await waitFor(() => expect(mocks.getStatus.mock.calls.length).toBeGreaterThanOrEqual(2));
});

test("pairing failure surfaces an error toast and keeps the form", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.login.mockRejectedValue(new Error("bad credentials"));

  render(<LocalSandboxSection />);

  const username = await screen.findByPlaceholderText(/username/i);
  fireEvent.change(username, { target: { value: "m1_smoke" } });
  fireEvent.change(screen.getByPlaceholderText(/password/i), {
    target: { value: "wrong" },
  });
  fireEvent.click(screen.getByRole("button", { name: /pair and start/i }));

  await waitFor(() => expect(screen.getByRole("button", { name: /pair and start/i })).toBeInTheDocument());
  expect(mocks.savePairing).not.toHaveBeenCalled();
  const { toast } = await import("react-hot-toast");
  expect(toast.error).toHaveBeenCalled();
});

test("paired view shows status line and policy change rewrites the config", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });
  mocks.createPat.mockResolvedValue({ token: "lcpat_policy", pat_id: "p2" });
  mocks.savePairing.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  // 状态行：在线 + daemon 版本 + 进程运行中
  expect(await screen.findByText("Online")).toBeInTheDocument();
  expect(screen.getByText(/daemon 0\.1\.0/)).toBeInTheDocument();
  expect(screen.getByText("Running")).toBeInTheDocument();

  // 策略切换：createPat → savePairing（新策略）→ restartDaemon
  fireEvent.click(screen.getByText("Confirmation policy"));
  fireEvent.click(await screen.findByText("Confirm commands only"));

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalled());
  expect(mocks.savePairing).toHaveBeenCalledWith({
    serverUrl: expect.stringMatching(/^https?:\/\//),
    pat: "lcpat_policy",
    confirmPolicy: "commands",
  });
});

test("paired view opens whitelisted local folders via logical names", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });
  mocks.openLocalPath.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await screen.findByText("Online");
  fireEvent.click(screen.getByRole("button", { name: /open workspaces/i }));
  fireEvent.click(screen.getByRole("button", { name: /open audit/i }));

  await waitFor(() => expect(mocks.openLocalPath).toHaveBeenCalledTimes(2));
  expect(mocks.openLocalPath).toHaveBeenNthCalledWith(1, "workspaces");
  expect(mocks.openLocalPath).toHaveBeenNthCalledWith(2, "audit");
});

test("paired view restart button bounces the daemon", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await screen.findByText("Online");
  fireEvent.click(screen.getByRole("button", { name: /restart daemon/i }));

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalledTimes(1));
});
