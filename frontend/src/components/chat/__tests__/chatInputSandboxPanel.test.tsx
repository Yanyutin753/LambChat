/** @vitest-environment jsdom */
// 沙箱选择器集成（统一面板 round）：
// 1. 同一时刻只允许一个选项模态打开（thinking / sandbox 互斥，FeaturePanel 各有独立 key）
// 2. RunModePopover 设置组提供"沙箱"条目（档位+设备 badge + daemon 在线状态点），点击打开 sandbox 面板
// 3. sandbox 面板为统一面板：档位（云端/本地）+ 执行设备同弹窗；点设备自动切本地档
// 4. 当前设备在设备行上标识（壳内 read_machine_id 比对命中）
// 5. 工具栏左侧提供"沙箱"chip（档位图标 + 档位·设备标签 + 本地档状态点），单击直达 sandbox 面板
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

const mocks = vi.hoisted(() => ({
  isShellAvailable: vi.fn(),
  readMachineId: vi.fn(),
  getStatus: vi.fn(),
  listMachines: vi.fn(),
  teamList: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: mocks.isShellAvailable,
  readMachineId: mocks.readMachineId,
}));

vi.mock("../../../services/api/sandbox", () => ({
  DESKTOP_SHELL_PAT_NAME: "lambchat-desktop-shell",
  sandboxApi: {
    getStatus: mocks.getStatus,
    createPat: vi.fn(),
  },
  sandboxApiMachines: { listMachines: mocks.listMachines },
}));

vi.mock("../../../services/api/team", () => ({
  teamApi: { list: mocks.teamList },
  subscribeTeamsChanged: () => () => {},
}));

vi.mock("../ComposerUsageChip", () => ({
  ComposerUsageChip: () => null,
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("react-hot-toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { ChatInputSelectors } from "../ChatInputSelectors";
import { ChatInputToolbar } from "../ChatInputToolbar";
import { RunModePopover } from "../RunModePopover";
import { resolveSandboxPresentation } from "../sandboxOption";
import type { SandboxMachine } from "../../../services/api/sandbox";
import { _resetSandboxStatusStoreForTests } from "../../../stores/sandboxStatusStore";
import type { AgentOption } from "../../../types";

const THINKING_DESCRIPTION = "Control thinking intensity";
const SANDBOX_DESCRIPTION = "Choose where sandboxed commands run";

const MACHINES: SandboxMachine[] = [
  {
    machine_id: "mac1",
    name: "MacBook",
    platform: "darwin",
    version: "0.3.0",
    confirm_policy: "all",
    online: true,
  },
  {
    machine_id: "srv1",
    name: "Server",
    platform: "linux",
    version: "0.3.0",
    confirm_policy: "none",
    online: true,
  },
];

function buildAgentOptions(): Record<string, AgentOption> {
  return {
    enable_thinking: {
      type: "string",
      default: "medium",
      label: "Thinking",
      label_key: "agentOptions.enableThinking.label",
      description: THINKING_DESCRIPTION,
      description_key: "agentOptions.enableThinking.description",
      options: [
        { value: "low", label_key: "agentOptions.enableThinking.options.low" },
        {
          value: "medium",
          label_key: "agentOptions.enableThinking.options.medium",
        },
      ],
    },
    sandbox: {
      type: "string",
      default: "cloud",
      label: "Sandbox",
      label_key: "agentOptions.sandbox.label",
      description: SANDBOX_DESCRIPTION,
      description_key: "agentOptions.sandbox.description",
      options: [
        { value: "cloud", label_key: "agentOptions.sandbox.options.cloud" },
        { value: "local", label_key: "agentOptions.sandbox.options.local" },
      ],
    },
  };
}

function renderSelectors(
  activePanel: "thinking" | "sandbox",
  agentOptionValues: Record<string, boolean | string | number> = {},
  onToggleAgentOption: (
    key: string,
    value: boolean | string | number,
  ) => void = () => {},
) {
  return render(
    <ChatInputSelectors
      activePanel={activePanel}
      onActivePanelChange={() => {}}
      agentOptions={buildAgentOptions()}
      agentOptionValues={agentOptionValues}
      onToggleAgentOption={onToggleAgentOption}
    />,
  );
}

function renderToolbar(
  onActivePanelChange: (panel: "thinking" | "sandbox" | null) => void,
  agentOptionValues: Record<string, boolean | string | number> = {},
) {
  return render(
    <ChatInputToolbar
      activePanel={null}
      onActivePanelChange={onActivePanelChange}
      canSend
      isLoading={false}
      canSubmit
      hasUploadingAttachment={false}
      enabledToolsCount={0}
      totalToolsCount={0}
      enabledSkillsCount={0}
      totalSkillsCount={0}
      hasPersonaSelector={false}
      hasAgentSelector={false}
      hasThinkingOption={false}
      uploadCategories={[]}
      uploadFiles={() => {}}
      personaAvatar={null}
      agentOptions={buildAgentOptions()}
      agentOptionValues={agentOptionValues}
      onToggleAgentOption={() => {}}
      onStopClick={() => {}}
      onNoPermissionClick={() => {}}
    />,
  );
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.readMachineId.mockResolvedValue(null);
  mocks.getStatus.mockResolvedValue({ online: true });
  mocks.listMachines.mockResolvedValue({
    machines: [],
    default_machine_id: null,
  });
  mocks.teamList.mockResolvedValue({ total: 0, teams: [] });
  // useSandboxStatus 现在是全局单例 store 的薄壳：跨用例隔离状态
  _resetSandboxStatusStoreForTests();
});

test("thinking panel open renders only the thinking modal, not the sandbox modal", () => {
  renderSelectors("thinking");

  expect(screen.getByText(THINKING_DESCRIPTION)).toBeInTheDocument();
  expect(screen.queryByText(SANDBOX_DESCRIPTION)).not.toBeInTheDocument();
});

test("sandbox panel open renders only the sandbox modal, not the thinking modal", () => {
  renderSelectors("sandbox");

  expect(screen.getByText(SANDBOX_DESCRIPTION)).toBeInTheDocument();
  expect(screen.queryByText(THINKING_DESCRIPTION)).not.toBeInTheDocument();
});

test("run mode popover shows a sandbox entry that opens the sandbox panel", () => {
  const onActivePanelChange = vi.fn();
  renderToolbar(onActivePanelChange);

  fireEvent.click(document.querySelector("[data-run-mode-trigger]")!);
  // 设置组默认折叠，先展开再点击沙箱条目
  fireEvent.click(screen.getByText("Settings"));
  fireEvent.click(screen.getByText("Sandbox"));

  expect(onActivePanelChange).toHaveBeenCalledWith("sandbox");
});

test("sandbox popover entry shows the current tier badge and an online status dot", async () => {
  const onOpenSandboxPanel = vi.fn();
  render(
    <RunModePopover
      open
      onClose={() => {}}
      autoModeEnabled={false}
      goalModeEnabled={false}
      onToggleAutoMode={() => {}}
      onToggleGoalMode={() => {}}
      hasSandboxOption
      sandboxLabel="Local"
      onOpenSandboxPanel={onOpenSandboxPanel}
    />,
  );

  fireEvent.click(screen.getByText("Sandbox"));
  expect(onOpenSandboxPanel).toHaveBeenCalledTimes(1);

  // 当前档位 badge
  expect(screen.getByText("Local")).toBeInTheDocument();
  // daemon 在线状态点：绿=在线（getStatus mock 返回 online:true）
  const dot = document.querySelector("[data-sandbox-status-dot]");
  expect(dot).not.toBeNull();
  await waitFor(() => {
    // jsdom 会把 #22c55e 规范化为 rgb(34, 197, 94)
    const background = (dot as HTMLElement).style.background;
    expect(background).toMatch(/#22c55e|rgb\(34, 197, 94\)/);
  });
});

test("resolveSandboxPresentation reports presence and the stored tier label", () => {
  expect(resolveSandboxPresentation(undefined, {}, i18n.t)).toEqual({
    has: false,
  });

  const options = buildAgentOptions();
  // 已存 local：badge 显示本地档 label
  expect(
    resolveSandboxPresentation(options, { sandbox: "local" }, i18n.t),
  ).toEqual({ has: true, label: "Local computer" });
  // 未存值：回落 default（cloud）
  expect(resolveSandboxPresentation(options, {}, i18n.t)).toEqual({
    has: true,
    label: "Cloud computer",
  });
});

// ---------------------------------------------------------------------------
// 统一面板：档位 + 执行设备同弹窗（不再有独立 machine 面板）
// ---------------------------------------------------------------------------

test("sandbox panel lists machines in the same modal on the local tier", async () => {
  mocks.listMachines.mockResolvedValue({
    machines: MACHINES,
    default_machine_id: "mac1",
  });
  renderSelectors("sandbox", { sandbox: "local" });

  // 同一弹窗：档位描述 + 设备行（自动 + 机器名单）同帧渲染
  expect(await screen.findByText(SANDBOX_DESCRIPTION)).toBeInTheDocument();
  expect(await screen.findByText("MacBook")).toBeInTheDocument();
  expect(screen.getByText("Server")).toBeInTheDocument();
  expect(screen.getByText("Auto (default)")).toBeInTheDocument();
  // 思考模态互斥：不渲染
  expect(screen.queryByText(THINKING_DESCRIPTION)).not.toBeInTheDocument();
});

test("sandbox panel shows the machine section on the cloud tier for one-tap switching", async () => {
  mocks.listMachines.mockResolvedValue({
    machines: MACHINES,
    default_machine_id: null,
  });
  const onToggleAgentOption = vi.fn();
  renderSelectors("sandbox", { sandbox: "cloud" }, onToggleAgentOption);

  // 云端档也展示设备：点设备 = 一键切本地 + 指定执行目标
  fireEvent.click(await screen.findByText("MacBook"));
  expect(onToggleAgentOption).toHaveBeenCalledWith("sandbox", "local");
  expect(onToggleAgentOption).toHaveBeenCalledWith(
    "sandbox_machine_id",
    "mac1",
  );
});

test("sandbox panel hides the machine section when no machine is online", async () => {
  mocks.listMachines.mockResolvedValue({
    machines: [
      { ...MACHINES[0], online: false },
      { ...MACHINES[1], online: false },
    ],
    default_machine_id: null,
  });
  renderSelectors("sandbox", { sandbox: "local" });

  await screen.findByText(SANDBOX_DESCRIPTION);
  await waitFor(() =>
    expect(screen.queryByText("MacBook")).not.toBeInTheDocument(),
  );
});

test("sandbox panel blocks selecting an offline machine with a hint", async () => {
  mocks.listMachines.mockResolvedValue({
    machines: [
      ...MACHINES,
      {
        machine_id: "pc1",
        name: "Old PC",
        platform: "win32",
        version: "0.3.0",
        confirm_policy: "all",
        online: false,
      },
    ],
    default_machine_id: "mac1",
  });
  const onToggleAgentOption = vi.fn();
  renderSelectors("sandbox", { sandbox: "local" }, onToggleAgentOption);

  // 离线机置灰保留展示：点击只提示，不落选为目标机
  const offlineRow = await screen.findByText(/Old PC · offline/);
  fireEvent.click(offlineRow);
  const { toast } = await import("react-hot-toast");
  expect(toast.error).toHaveBeenCalledWith(
    "That computer is offline and can't be selected as the execution target",
  );
  expect(onToggleAgentOption).not.toHaveBeenCalled();

  // 在线机正常可选（档位已是 local，仅更新目标机）
  fireEvent.click(screen.getByText("MacBook"));
  expect(onToggleAgentOption).toHaveBeenCalledWith("sandbox_machine_id", "mac1");
  expect(onToggleAgentOption).not.toHaveBeenCalledWith("sandbox", "local");
});

test("sandbox panel marks the current device on its machine row", async () => {
  mocks.readMachineId.mockResolvedValue("srv1");
  mocks.listMachines.mockResolvedValue({
    machines: MACHINES,
    default_machine_id: null,
  });
  renderSelectors("sandbox", { sandbox: "local" });

  await screen.findByText("Server");
  // 当前设备标识只落在命中的行上
  const badges = screen
    .getAllByText("This device")
    .map((el) => el.closest("[data-sandbox-machine-row]"));
  expect(badges).toHaveLength(1);
  expect(badges[0]).not.toBeNull();
  expect(badges[0]!.textContent).toContain("Server");
});

test("thinking panel does not stack the machine selector modal", async () => {
  // 回归防护：设备行只属于 sandbox 面板，不得挂到 thinking 面板上
  mocks.listMachines.mockResolvedValue({
    machines: MACHINES,
    default_machine_id: null,
  });
  renderSelectors("thinking", { sandbox: "local" });

  await waitFor(() => {
    expect(screen.getByText(THINKING_DESCRIPTION)).toBeInTheDocument();
  });
  expect(screen.queryByText("MacBook")).not.toBeInTheDocument();
});

test("sandbox panel on offline web keeps the local tier visible with a download entry", async () => {
  // 纯 web + daemon 离线：本地档不再隐藏——置灰显示 + 面板底部下载引导
  mocks.isShellAvailable.mockReturnValue(false);
  mocks.getStatus.mockResolvedValue({ online: false });
  renderSelectors("sandbox");

  const localRow = await screen.findByText("Local computer");
  expect(localRow).toBeInTheDocument();

  const downloadEntry = await screen.findByText("Download local sandbox");
  fireEvent.click(downloadEntry);
  expect(mocks.navigate).toHaveBeenCalledWith("/download");
});

test("sandbox panel online hides the download entry", async () => {
  mocks.isShellAvailable.mockReturnValue(false);
  mocks.getStatus.mockResolvedValue({ online: true });
  renderSelectors("sandbox");

  // 等下载入口消失而非等"Local"出现：档位 chip 首帧即渲染，getStatus
  // 异步落地前离线引导仍在，同步断言会竞态（CI 高负载下抖动）
  await waitFor(() =>
    expect(
      screen.queryByText("Download local sandbox"),
    ).not.toBeInTheDocument(),
  );
});

// ---------------------------------------------------------------------------
// 工具栏沙箱 chip：拉出设置组，单击直达沙箱面板
// ---------------------------------------------------------------------------

test("toolbar shows a sandbox chip with the current tier that opens the sandbox panel in one click", () => {
  const onActivePanelChange = vi.fn();
  renderToolbar(onActivePanelChange);

  // 默认云端档：chip 标签直接显示当前档位，无需打开任何浮层
  const chip = screen.getByTitle("Sandbox · Cloud computer");
  expect(chip).toHaveTextContent("Cloud computer");

  fireEvent.click(chip);
  expect(onActivePanelChange).toHaveBeenCalledTimes(1);
  expect(onActivePanelChange).toHaveBeenCalledWith("sandbox");
});

test("sandbox chip reflects the stored local tier in the label", () => {
  renderToolbar(vi.fn(), { sandbox: "local" });

  expect(screen.getByTitle("Sandbox · Local computer")).toHaveTextContent("Local computer");
});

test("sandbox chip shows the selected machine in the label on the local tier", async () => {
  mocks.listMachines.mockResolvedValue({
    machines: MACHINES,
    default_machine_id: null,
  });
  renderToolbar(vi.fn(), { sandbox: "local", sandbox_machine_id: "mac1" });

  // chip：档位 · 设备 一目了然
  const chip = await screen.findByTitle("Sandbox · Local computer · MacBook");
  expect(chip).toHaveTextContent("MacBook");
});

test("sandbox chip keeps the tier-only label on auto machine resolution", async () => {
  mocks.listMachines.mockResolvedValue({
    machines: MACHINES,
    default_machine_id: null,
  });
  renderToolbar(vi.fn(), { sandbox: "local", sandbox_machine_id: "" });

  await screen.findByTitle("Sandbox · Local computer");
  expect(screen.queryByTitle(/MacBook/)).not.toBeInTheDocument();
});

test("sandbox chip swaps to a cloud icon on the cloud tier and a monitor icon on the local tier", () => {
  // 手机端档位文字隐藏，仅靠图标区分档位：云端=云图标，本地=显示器图标
  renderToolbar(vi.fn(), { sandbox: "cloud" });
  expect(
    screen.getByTitle("Sandbox · Cloud computer").querySelector("svg.lucide-cloud"),
  ).not.toBeNull();

  cleanup();
  renderToolbar(vi.fn(), { sandbox: "local" });
  expect(
    screen.getByTitle("Sandbox · Local computer").querySelector("svg.lucide-monitor"),
  ).not.toBeNull();
});

test("sandbox chip shows a green dot on the local tier when the daemon is online", async () => {
  mocks.getStatus.mockResolvedValue({ online: true });
  renderToolbar(vi.fn(), { sandbox: "local" });

  const dot = await waitFor(() => {
    const el = document.querySelector("[data-sandbox-status-dot]");
    expect(el).not.toBeNull();
    return el as HTMLElement;
  });
  await waitFor(() => {
    // jsdom 会把 #22c55e 规范化为 rgb(34, 197, 94)
    expect(dot.style.background).toMatch(/#22c55e|rgb\(34, 197, 94\)/);
  });
});

test("sandbox chip shows a gray dot on the local tier when the daemon is offline", async () => {
  mocks.getStatus.mockResolvedValue({ online: false });
  renderToolbar(vi.fn(), { sandbox: "local" });

  const dot = await waitFor(() => {
    const el = document.querySelector("[data-sandbox-status-dot]");
    expect(el).not.toBeNull();
    return el as HTMLElement;
  });
  await waitFor(() => {
    expect(dot.style.background).toMatch(/#a8a29e|rgb\(168, 162, 158\)/);
  });
});

test("sandbox chip hides the status dot on the cloud tier", () => {
  // 云端档不依赖本地 daemon：无状态点、也不发起状态轮询
  mocks.getStatus.mockResolvedValue({ online: true });
  renderToolbar(vi.fn(), { sandbox: "cloud" });

  expect(document.querySelector("[data-sandbox-status-dot]")).toBeNull();
  expect(mocks.getStatus).not.toHaveBeenCalled();
});

test("toolbar hides the sandbox chip when the session has no sandbox option", () => {
  const withoutSandbox = Object.fromEntries(
    Object.entries(buildAgentOptions()).filter(([key]) => key !== "sandbox"),
  );
  render(
    <ChatInputToolbar
      activePanel={null}
      onActivePanelChange={() => {}}
      canSend
      isLoading={false}
      canSubmit
      hasUploadingAttachment={false}
      enabledToolsCount={0}
      totalToolsCount={0}
      enabledSkillsCount={0}
      totalSkillsCount={0}
      hasPersonaSelector={false}
      hasAgentSelector={false}
      hasThinkingOption={false}
      uploadCategories={[]}
      uploadFiles={() => {}}
      personaAvatar={null}
      agentOptions={withoutSandbox}
      agentOptionValues={{}}
      onToggleAgentOption={() => {}}
      onStopClick={() => {}}
      onNoPermissionClick={() => {}}
    />,
  );

  expect(screen.queryByTitle(/Sandbox · /)).not.toBeInTheDocument();
});
