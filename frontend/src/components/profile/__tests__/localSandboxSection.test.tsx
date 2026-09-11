/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { _resetSandboxStatusStoreForTests } from "../../../stores/sandboxStatusStore";

const mocks = vi.hoisted(() => ({
  subscribeDaemonStatus: vi.fn(),
  isShellAvailable: vi.fn(),
  daemonProcessStatus: vi.fn(),
  savePairing: vi.fn(),
  restartDaemon: vi.fn(),
  openLocalPath: vi.fn(),
  writeConfirmPolicy: vi.fn(),
  clearPairing: vi.fn(),
  readPairingPat: vi.fn(),
  getStatus: vi.fn(),
  listMachines: vi.fn(),
  createPat: vi.fn(),
  pairingLogin: vi.fn(),
  createPairingPat: vi.fn(),
  revokePairingPat: vi.fn(),
  getValidAccessToken: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("../../../services/api/tokenManager", () => ({
  getValidAccessToken: mocks.getValidAccessToken,
}));

vi.mock("../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: mocks.isShellAvailable,
  subscribeDaemonStatus: mocks.subscribeDaemonStatus,
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
  sandboxApiMachines: {
    listMachines: mocks.listMachines,
  },
  machinePlatformLabel: (platform: string) => platform,
}));

vi.mock("react-hot-toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import {
  AUTO_PAIR_RETRY_DELAY_MS,
  LocalSandboxSection,
} from "../LocalSandboxSection";

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
  // 默认：非事件模式（resolve null → 组件回退轮询，与旧行为同构）
  mocks.subscribeDaemonStatus.mockImplementation(() => Promise.resolve(null));
  window.localStorage.clear();
  _resetSandboxStatusStoreForTests();
  mocks.listMachines.mockResolvedValue({
    machines: [],
    default_machine_id: null,
  });
});

test("pure web offline renders the pairing guidance with a download CTA", async () => {
  mocks.isShellAvailable.mockReturnValue(false);
  mocks.getStatus.mockResolvedValue({ online: false });

  render(<LocalSandboxSection />);

  expect(
    await screen.findByText(/pair it with the LambChat desktop app/i),
  ).toBeInTheDocument();
  // 离线引导卡：下载入口跳站内下载页（含桌面端/daemon + 教程）
  const downloadCta = await screen.findByRole("button", {
    name: /download local sandbox/i,
  });
  fireEvent.click(downloadCta);
  expect(mocks.navigate).toHaveBeenCalledWith("/download");
  // 纯 web：不渲染配对表单，也不探测壳内进程
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
  expect(mocks.daemonProcessStatus).not.toHaveBeenCalled();
});

test("pure web with an online daemon shows status and machines, not the dead-end hint", async () => {
  // 桌面端已配对连接：网页端能看到本地沙箱在线状态与机器列表
  //（会话里可选本地档 + 执行机器），而不是"需要桌面端"死提示
  mocks.isShellAvailable.mockReturnValue(false);
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.3.0" });
  mocks.listMachines.mockResolvedValue({
    machines: [
      {
        machine_id: "pc1",
        name: "yangyang",
        platform: "win32",
        version: "0.3.0",
        confirm_policy: "all",
        online: true,
      },
    ],
    default_machine_id: "pc1",
  });

  render(<LocalSandboxSection />);

  expect(await screen.findByText("Online")).toBeInTheDocument();
  expect(screen.getByText(/daemon 0\.3\.0/)).toBeInTheDocument();
  expect(
    screen.getByText(/managed by the paired desktop app/i),
  ).toBeInTheDocument();
  // 机器卡自带独立的 useSandboxStatus 实例（异步拉取），等待式断言
  expect(await screen.findByText("yangyang")).toBeInTheDocument();
  // 死提示与配对表单都不出现
  expect(
    screen.queryByText(/pair it with the LambChat desktop app/i),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
  expect(mocks.daemonProcessStatus).not.toHaveBeenCalled();
});

test("pairing runs side-effect-free login → pat → savePairing → restart in order", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.getValidAccessToken.mockResolvedValue(null);
  mocks.pairingLogin.mockResolvedValue("pairing-jwt");
  mocks.createPairingPat.mockResolvedValue({
    token: "lcpat_pair",
    pat_id: "p1",
  });
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
  await waitFor(() =>
    expect(mocks.getStatus.mock.calls.length).toBeGreaterThanOrEqual(2),
  );
});

test("pairing failure surfaces an error toast and keeps the form", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.getValidAccessToken.mockResolvedValue(null);
  mocks.pairingLogin.mockRejectedValue(new Error("bad credentials"));

  render(<LocalSandboxSection />);

  const username = await screen.findByPlaceholderText(/username/i);
  fireEvent.change(username, { target: { value: "m1_smoke" } });
  fireEvent.change(screen.getByPlaceholderText(/password/i), {
    target: { value: "wrong" },
  });
  fireEvent.click(screen.getByRole("button", { name: /pair and start/i }));

  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: /pair and start/i }),
    ).toBeInTheDocument(),
  );
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
  fireEvent.click(screen.getByRole("button", { name: /open logs/i }));

  await waitFor(() => expect(mocks.openLocalPath).toHaveBeenCalledTimes(3));
  expect(mocks.openLocalPath).toHaveBeenNthCalledWith(1, "workspaces");
  expect(mocks.openLocalPath).toHaveBeenNthCalledWith(2, "audit");
  expect(mocks.openLocalPath).toHaveBeenNthCalledWith(3, "logs");
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
    Object.assign(new Error("PAT not found"), {
      status: 401,
      code: "pat_not_found",
    }),
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

// ---------- 登录即配对：会话 JWT 自动铸 PAT / 已有 PAT 自动拉起 ----------

test("auto-pairs with session token when unpaired and no local PAT", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.getValidAccessToken.mockResolvedValue("jwt-session");
  mocks.createPairingPat.mockResolvedValue({
    token: "lcpat_auto",
    pat_id: "p-auto",
  });
  mocks.savePairing.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalled());
  expect(mocks.createPairingPat).toHaveBeenCalledWith("jwt-session");
  expect(mocks.savePairing).toHaveBeenCalledWith(
    expect.objectContaining({ pat: "lcpat_auto", patId: "p-auto" }),
  );
});

test("auto-pair mints the PAT with the refreshed token, not the raw stored one", async () => {
  // 过期 access token 场景：裸 localStorage 值已 401，必须走可刷新的
  // token 通道（getValidAccessToken）铸 PAT，否则静默回落密码表单
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.readPairingPat.mockResolvedValue(null);
  window.localStorage.setItem("access_token", "jwt-stale");
  mocks.getValidAccessToken.mockResolvedValue("jwt-refreshed");
  mocks.createPairingPat.mockResolvedValue({
    token: "lcpat_auto",
    pat_id: "p-auto",
  });
  mocks.savePairing.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalled());
  expect(mocks.createPairingPat).toHaveBeenCalledWith("jwt-refreshed");
  expect(mocks.createPairingPat).not.toHaveBeenCalledWith("jwt-stale");
});

test("auto-pair retries with backoff after a transient failure", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.getValidAccessToken.mockResolvedValue("jwt-session");
  mocks.createPairingPat
    .mockRejectedValueOnce(new Error("transient network error"))
    .mockResolvedValue({ token: "lcpat_retry", pat_id: "p-retry" });
  mocks.savePairing.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  vi.useFakeTimers();
  try {
    render(<LocalSandboxSection />);

    // 先冲挂载异步链（daemonProcessStatus → 未配对确认 → 调度首次尝试）
    await act(async () => {});
    // 首次尝试（0ms 延迟）发起并瞬态失败
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mocks.createPairingPat).toHaveBeenCalledTimes(1);
    expect(mocks.restartDaemon).not.toHaveBeenCalled();

    // 重试间隔到点后自动再试一次并成功
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTO_PAIR_RETRY_DELAY_MS);
    });
    expect(mocks.createPairingPat).toHaveBeenCalledTimes(2);
    expect(mocks.restartDaemon).toHaveBeenCalledTimes(1);
    expect(mocks.savePairing).toHaveBeenCalledWith(
      expect.objectContaining({ pat: "lcpat_retry", patId: "p-retry" }),
    );
  } finally {
    vi.useRealTimers();
    // clearAllMocks 不清 once 队列：断言失败时未消费的 once 实现会泄漏到后续测试
    mocks.createPairingPat.mockReset();
  }
});

test("auto-restarts daemon without re-minting when PAT already on disk", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.readPairingPat.mockResolvedValue("lcpat_existing");
  mocks.restartDaemon.mockResolvedValue(undefined);

  render(<LocalSandboxSection />);

  await waitFor(() => expect(mocks.restartDaemon).toHaveBeenCalled());
  expect(mocks.createPairingPat).not.toHaveBeenCalled();
  expect(mocks.savePairing).not.toHaveBeenCalled();
});

test("auto-pair failure falls back to the manual pairing form", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.getValidAccessToken.mockResolvedValue("jwt-session");
  mocks.createPairingPat.mockRejectedValue(new Error("401"));

  render(<LocalSandboxSection />);

  expect(await screen.findByPlaceholderText(/username/i)).toBeInTheDocument();
});

// ---------- 一键配对：当前登录账号铸 PAT（OAuth 用户唯一可用路径） ----------

test("unpaired form offers one-click pairing with the current signed-in account", async () => {
  // OAuth 用户没有密码，密码表单对他们不可用——"当前账号配对"按钮用
  // 壳会话 token 直接铸 PAT。假时钟扣住 0ms 自动尝试，让按钮成为
  // 唯一执行路径（避免两条路径抢 mock 造成的竞态）。
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.getValidAccessToken.mockResolvedValue("jwt-current");
  mocks.createPairingPat.mockResolvedValue({
    token: "lcpat_cur",
    pat_id: "p-cur",
  });
  mocks.savePairing.mockResolvedValue(undefined);
  mocks.restartDaemon.mockResolvedValue(undefined);

  vi.useFakeTimers();
  try {
    render(<LocalSandboxSection />);
    // 冲挂载异步链（表单渲染就绪），0ms 自动尝试保持挂起
    await act(async () => {});

    fireEvent.click(
      screen.getByRole("button", { name: /pair with current account/i }),
    );
    await act(async () => {});

    // 不走密码通道：一键配对只用当前会话 token，链路走完并提示成功
    expect(mocks.pairingLogin).not.toHaveBeenCalled();
    expect(mocks.createPairingPat).toHaveBeenCalledWith("jwt-current");
    expect(mocks.savePairing).toHaveBeenCalledWith(
      expect.objectContaining({ pat: "lcpat_cur", patId: "p-cur" }),
    );
    expect(mocks.restartDaemon).toHaveBeenCalledTimes(1);
    const { toast } = await import("react-hot-toast");
    expect(toast.success).toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});

test("one-click pairing surfaces an error toast when signed out", async () => {
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.getStatus.mockResolvedValue({ online: false });
  mocks.readPairingPat.mockResolvedValue(null);
  mocks.getValidAccessToken.mockResolvedValue(null);

  render(<LocalSandboxSection />);

  fireEvent.click(
    await screen.findByRole("button", { name: /pair with current account/i }),
  );

  const { toast } = await import("react-hot-toast");
  await waitFor(() => expect(toast.error).toHaveBeenCalled());
  expect(mocks.createPairingPat).not.toHaveBeenCalled();
  expect(mocks.savePairing).not.toHaveBeenCalled();
});

test("daemon process status follows shell status events instead of polling", async () => {
  // 壳推送模式：订阅成功后不再起 10s 轮询，状态随事件翻转
  let eventListener: ((event: {
    running: boolean;
    unsupported: boolean;
    generation: number;
    restarts: number;
  }) => void) | null = null;
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.daemonProcessStatus.mockResolvedValue("stopped");
  mocks.subscribeDaemonStatus.mockImplementation(
    (_listener: unknown) =>
      new Promise<() => void>((resolve) => {
        eventListener = _listener as typeof eventListener;
        resolve(() => {});
      }),
    );
  mocks.getStatus.mockResolvedValue({ online: true, daemon_version: "0.1.0" });

  render(<LocalSandboxSection />);
  // 初始对账一次（stopped → 配对表单）
  await waitFor(() =>
    expect(mocks.daemonProcessStatus).toHaveBeenCalledTimes(1),
  );

  // 事件：daemon 拉起 → 配对视图出现（策略行等在线控制项）
  act(() => {
    eventListener?.({
      running: true,
      unsupported: false,
      generation: 1,
      restarts: 0,
    });
  });
  await waitFor(() =>
    expect(screen.getByText("Online")).toBeInTheDocument(),
  );

  // 事件：daemon 退出 → 回到配对表单（服务端在线徽章仍在，进程态翻为 Stopped）
  act(() => {
    eventListener?.({
      running: false,
      unsupported: false,
      generation: 2,
      restarts: 1,
    });
  });
  await waitFor(() =>
    expect(screen.getByText("Stopped")).toBeInTheDocument(),
  );
  // 事件模式下不追加轮询（仅初始对账那一次）
  expect(mocks.daemonProcessStatus).toHaveBeenCalledTimes(1);
});
