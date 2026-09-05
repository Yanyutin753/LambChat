/** @vitest-environment jsdom */
// 沙箱选择器集成（fix round 1）：
// 1. 同一时刻只允许一个选项模态打开（thinking / sandbox 互斥，FeaturePanel 有独立 "sandbox" key）
// 2. RunModePopover 设置组提供"沙箱"条目（当前档位 badge + daemon 在线状态点），点击打开 sandbox 面板
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

const mocks = vi.hoisted(() => ({
  isShellAvailable: vi.fn(),
  getStatus: vi.fn(),
  teamList: vi.fn(),
}));

vi.mock("../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: mocks.isShellAvailable,
}));

vi.mock("../../../services/api/sandbox", () => ({
  DESKTOP_SHELL_PAT_NAME: "lambchat-desktop-shell",
  sandboxApi: {
    getStatus: mocks.getStatus,
    createPat: vi.fn(),
  },
}));

vi.mock("../../../services/api/team", () => ({
  teamApi: { list: mocks.teamList },
  subscribeTeamsChanged: () => () => {},
}));

vi.mock("../ComposerUsageChip", () => ({
  ComposerUsageChip: () => null,
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("react-hot-toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { ChatInputSelectors } from "../ChatInputSelectors";
import { ChatInputToolbar } from "../ChatInputToolbar";
import { RunModePopover } from "../RunModePopover";
import { resolveSandboxPresentation } from "../sandboxOption";
import type { AgentOption } from "../../../types";

const THINKING_DESCRIPTION = "Control thinking intensity";
const SANDBOX_DESCRIPTION = "Choose where sandboxed commands run";

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

function renderSelectors(activePanel: "thinking" | "sandbox") {
  return render(
    <ChatInputSelectors
      activePanel={activePanel}
      onActivePanelChange={() => {}}
      agentOptions={buildAgentOptions()}
      agentOptionValues={{}}
      onToggleAgentOption={() => {}}
    />,
  );
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
  mocks.isShellAvailable.mockReturnValue(true);
  mocks.getStatus.mockResolvedValue({ online: true });
  mocks.teamList.mockResolvedValue({ total: 0, teams: [] });
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
  render(
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
      agentOptionValues={{}}
      onToggleAgentOption={() => {}}
      onStopClick={() => {}}
      onNoPermissionClick={() => {}}
    />,
  );

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
  ).toEqual({ has: true, label: "Local" });
  // 未存值：回落 default（cloud）
  expect(resolveSandboxPresentation(options, {}, i18n.t)).toEqual({
    has: true,
    label: "Cloud",
  });
});
