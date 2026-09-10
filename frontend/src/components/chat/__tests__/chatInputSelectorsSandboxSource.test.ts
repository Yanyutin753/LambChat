import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(
  join(process.cwd(), "src/components/chat/ChatInputSelectors.tsx"),
  "utf8",
);
const runModePopoverSource = readFileSync(
  join(process.cwd(), "src/components/chat/RunModePopover.tsx"),
  "utf8",
);

test("selectors adapt the sandbox option to shell and daemon availability", () => {
  // 双条件渲染分支：壳检测 + useSandboxStatus 在线状态
  expect(source).toMatch(/isShellAvailable/);
  expect(source).toMatch(/useSandboxStatus/);
  expect(source).toMatch(/adaptSandboxAgentOption/);
  expect(source).toMatch(/SANDBOX_AGENT_OPTION_KEY/);
});

test("sandbox selector opens on its own panel key, never the thinking panel", () => {
  // 独立 panel key：避免与思考档模态同帧双开（fix round 1 的 Critical 回归）
  expect(source).toMatch(/activePanel === "sandbox"/);
});

test("unified sandbox panel hosts the machine rows, no separate machine panel", () => {
  // 统一面板：设备行注入 sandbox 面板（belowOptions），独立 machine 面板已移除
  expect(source).toMatch(/belowOptions=\{machineSection\}/);
  expect(source).toMatch(/data-sandbox-machine-row/);
  expect(source).not.toMatch(/activePanel === "machine"/);
  expect(runModePopoverSource).not.toMatch(/data-machine-entry/);
});

test("unified sandbox panel marks the current device and switches tier on tap", () => {
  // 当前设备标识 + 云端档点设备一键切本地
  expect(source).toMatch(/data-current-device-badge/);
  expect(source).toMatch(/agentOptions\.sandboxMachine\.currentDevice/);
  expect(source).toMatch(/handleSelectMachineRow/);
});

test("offline local selection warns without blocking the change", () => {
  // 离线选本地档：五语提示 + 仍应用用户选择
  expect(source).toMatch(/agentOptions\.sandbox\.offlineHint/);
  expect(source).toMatch(/value === "local" && !sandboxOnline/);
});

test("offline sandbox panel offers a download entry to the in-app download page", () => {
  // 离线（壳内或纯 web，本地档置灰可见）：面板底部下载引导跳站内下载页
  expect(source).toMatch(/agentOptions\.sandbox\.downloadEntry/);
  expect(source).toMatch(/navigate\("\/download"\)/);
  expect(source).toMatch(/data-sandbox-download-entry/);
});

test("sandbox status dot anchors to the visible popover entry, not a closed-state wrapper", () => {
  // 状态点锚定在 RunModePopover 的可见"沙箱"条目上；不再挂在 external 模式关闭态
  // 渲染为 null 的 0×0 包装 span 里（否则永远不可见）。
  expect(runModePopoverSource).toMatch(/data-sandbox-status-dot/);
  expect(source).not.toMatch(/data-sandbox-status-dot/);
});

test("popover gates sandbox status polling on its open state; the selector stays always-on", () => {
  // 轮询门控（M4 T8）：RunModePopover 只在展开时拉取/轮询（浮层关闭期间
  // 状态点不可见，不空转 10s 轮询）；ChatInputSelectors 的常驻实例保持
  // always-on（选择器动态适配依赖它）。
  expect(runModePopoverSource).toMatch(
    /useSandboxStatus\(\{\s*enabled: open,?\s*\}\)/,
  );
  // 选择器实例不传参数（缺省 enabled=true 的常驻轮询）
  expect(source).toMatch(/useSandboxStatus\(\)/);
  expect(source).not.toMatch(/useSandboxStatus\(\{/);
});

test("policy change notifies the sandbox status store to resync status", () => {
  // 双显不同步根因：machines 走 presence 秒推、profile 页依赖的 status 只有
  // 60s 对账轮询——chat input 切换成功后必须发 SANDBOX_STATUS_REFRESH 事件
  expect(source).toMatch(/notifySandboxStatusRefresh\(\);/);
  const successIdx = source.indexOf("agentOptions.sandboxPolicy.updated");
  const notifyIdx = source.indexOf("notifySandboxStatusRefresh();");
  expect(successIdx).toBeGreaterThan(-1);
  expect(notifyIdx).toBeGreaterThan(-1);
  expect(notifyIdx).toBeLessThan(successIdx);
});
