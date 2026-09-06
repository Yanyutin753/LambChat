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

test("machine selector opens on its own panel key, never the thinking panel", () => {
  // 机器选择器独立 panel key：注入机器选项后不得再挂 thinking 面板同帧双开
  expect(source).toMatch(/activePanel === "machine"/);
});

test("popover offers a machine sub-entry under the sandbox entry for the local tier", () => {
  // 多机选机入口：沙箱条目下的"机器"子条目（本地档 + 在线机器时显示）
  expect(runModePopoverSource).toMatch(/data-machine-entry/);
  expect(runModePopoverSource).toMatch(/SANDBOX_LOCAL_VALUE/);
});

test("offline local selection warns without blocking the change", () => {
  // 离线选本地档：五语提示 + 仍应用用户选择
  expect(source).toMatch(/agentOptions\.sandbox\.offlineHint/);
  expect(source).toMatch(/value === "local" && !sandboxOnline/);
});

test("restored local value carries an offline note on pure web", () => {
  expect(source).toMatch(/agentOptions\.sandbox\.restoredOffline/);
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
    /useSandboxStatus\(\{ enabled: open \}\)/,
  );
  // 选择器实例不传参数（缺省 enabled=true 的常驻轮询）
  expect(source).toMatch(/useSandboxStatus\(\)/);
  expect(source).not.toMatch(/useSandboxStatus\(\{/);
});
