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
  writeConfirmPolicy: vi.fn(),
  clearPairing: vi.fn(),
  readPairingPat: vi.fn(),
  getStatus: vi.fn(),
  createPat: vi.fn(),
  pairingLogin: vi.fn(),
  createPairingPat: vi.fn(),
  revokePairingPat: vi.fn(),
}));

vi.mock("../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: mocks.isShellAvailable,
  daemonProcessStatus: mocks.daemonProcessStatus,
  savePairing: mocks.savePairing,
  restartDaemon: mocks.restartDaemon,
  openLocalPath: mocks.openLocalPath,
  writeConfirmPolicy: mocks.writeConfirmPolicy,
  clearPairing: mocks.clearPairing,
  readPairingPat: mocks.readPairingPat,
}));

vi.mock("../../../services/api/sandbox", () => ({
  DESKTOP_SHELL_PAT_NAME: "lambchat-desktop-shell",
  sandboxApi: {
    getStatus: mocks.getStatus,
    createPat: mocks.createPat,
    pairingLogin: mocks.pairingLogin,
    createPairingPat: mocks.createPairingPat,
    revokePairingPat: mocks.revokePairingPat,
  },
}));

vi.mock("react-hot-toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { LocalSandboxSection } from "../LocalSandboxSection";

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
  window.localStorage.clear();
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

test("pairing runs side-effect-free login → pat → savePairing → restart in order", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.pairingLogin.mockResolvedValue("pairing-jwt");
  mocks.createPairingPat.mockResolvedValue({ token: "lcpat_pair", pat_id: "p1" });
  mocks.savePairing.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);
  const dispatchSpy = vi.spyOn(window, "dispatchEvent");

  render(<LocalSandboxSection />);

  const username = await screen.findByPlaceholderText(/username/i);
  fireEvent.change(username, { target: { value: "m1_smoke" } });
  fireEvent.change(screen.getByPlaceholderText(/password/i), {
    target: { value: "secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: /pair and start/i }));

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalled());

  // 无副作用登录：不落壳会话 token、不派发 auth:login 事件
  expect(mocks.pairingLogin).toHaveBeenCalledWith({
    username: "m1_smoke",
    password: "secret",
  });
  expect(window.localStorage.getItem("access_token")).toBeNull();
  expect(window.localStorage.getItem("refresh_token")).toBeNull();
  const loginEvents = dispatchSpy.mock.calls.filter(
    ([evt]) => (evt as CustomEvent).type === "auth:login",
  );
  expect(loginEvents).toHaveLength(0);

  // 铸 PAT 用的是配对账号的 JWT，不是壳会话
  expect(mocks.createPairingPat).toHaveBeenCalledWith("pairing-jwt");
  expect(mocks.createPat).not.toHaveBeenCalled();

  // savePairing 带上配对回执 pat_id
  expect(mocks.savePairing).toHaveBeenCalledWith({
    serverUrl: expect.stringMatching(/^https?:\/\//),
    pat: "lcpat_pair",
    confirmPolicy: "all",
    patId: "p1",
  });

  // 配对链路完成：pairingLogin → createPairingPat → savePairing → restartDaemon
  const [loginAt, patAt, saveAt, restartAt] = [
    mocks.pairingLogin.mock.invocationCallOrder[0],
    mocks.createPairingPat.mock.invocationCallOrder[0],
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
  mocks.pairingLogin.mockRejectedValue(new Error("bad credentials"));

  render(<LocalSandboxSection />);

  const username = await screen.findByPlaceholderText(/username/i);
  fireEvent.change(username, { target: { value: "m1_smoke" } });
  fireEvent.change(screen.getByPlaceholderText(/password/i), {
    target: { value: "wrong" },
  });
  fireEvent.click(screen.getByRole("button", { name: /pair and start/i }));

  await waitFor(() => expect(screen.getByRole("button", { name: /pair and start/i })).toBeInTheDocument());
  expect(mocks.savePairing).not.toHaveBeenCalled();
  expect(mocks.createPairingPat).not.toHaveBeenCalled();
  const { toast } = await import("react-hot-toast");
  expect(toast.error).toHaveBeenCalled();
});

test("paired view shows status line and policy change writes config only (no PAT remint)", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });
  mocks.writeConfirmPolicy.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  // 状态行：在线 + daemon 版本 + 进程运行中
  expect(await screen.findByText("Online")).toBeInTheDocument();
  expect(screen.getByText(/daemon 0\.1\.0/)).toBeInTheDocument();
  expect(screen.getByText("Running")).toBeInTheDocument();

  // 策略切换：writeConfirmPolicy（新策略）→ restartDaemon；绝不重铸 PAT
  fireEvent.click(screen.getByText("Confirmation policy"));
  fireEvent.click(await screen.findByText("Confirm commands only"));

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalled());
  expect(mocks.writeConfirmPolicy).toHaveBeenCalledWith("commands");
  expect(mocks.createPat).not.toHaveBeenCalled();
  expect(mocks.createPairingPat).not.toHaveBeenCalled();
  expect(mocks.savePairing).not.toHaveBeenCalled();
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

test("unpair revokes the stored PAT then clears local pairing", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });
  mocks.readPairingPat.mockResolvedValue("lcpat_stored");
  mocks.revokePairingPat.mockResolvedValue(undefined);
  mocks.clearPairing.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await screen.findByText("Online");
  fireEvent.click(screen.getByRole("button", { name: /unpair/i }));

  await waitFor(() => expect(mocks.clearPairing).toHaveBeenCalled());

  // 链路：readPairingPat → revokePairingPat(读到的 PAT) → clearPairing
  const [readAt, revokeAt, clearAt] = [
    mocks.readPairingPat.mock.invocationCallOrder[0],
    mocks.revokePairingPat.mock.invocationCallOrder[0],
    mocks.clearPairing.mock.invocationCallOrder[0],
  ];
  expect(mocks.revokePairingPat).toHaveBeenCalledWith("lcpat_stored");
  expect(readAt).toBeLessThan(revokeAt);
  expect(revokeAt).toBeLessThan(clearAt);

  const { toast } = await import("react-hot-toast");
  await waitFor(() => expect(toast.success).toHaveBeenCalled());
});

test("unpair still clears local pairing when server-side revoke fails", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });
  mocks.readPairingPat.mockResolvedValue("lcpat_stale");
  mocks.revokePairingPat.mockRejectedValue(
    Object.assign(new Error("PAT not found"), { status: 401, code: "pat_not_found" }),
  );
  mocks.clearPairing.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await screen.findByText("Online");
  fireEvent.click(screen.getByRole("button", { name: /unpair/i }));

  // 服务端吊销失败（已失效/离线）不阻塞本地清理
  await waitFor(() => expect(mocks.clearPairing).toHaveBeenCalled());
});

test("unpair proceeds without server revoke when no local PAT exists", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.clearPairing.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await screen.findByText("Online");
  fireEvent.click(screen.getByRole("button", { name: /unpair/i }));

  await waitFor(() => expect(mocks.clearPairing).toHaveBeenCalled());
  expect(mocks.revokePairingPat).not.toHaveBeenCalled();
});

test("paired view syncs policy display from daemon-reported confirm policy", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("running");
  mocks.getStatus.mockResolvedValue({
    online: true,
    daemon_version: "0.2.0",
    daemon_confirm_policy: "none",
  });

  render(<LocalSandboxSection />);

  // SelectRow 当前值跟随 daemon 上报（而非本地默认 all）
  expect(await screen.findByText("No confirmation")).toBeInTheDocument();
  expect(screen.queryByText("Confirm all actions")).not.toBeInTheDocument();
});
