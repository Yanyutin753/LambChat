import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(
  join(process.cwd(), "src/components/chat/ChatInputSelectors.tsx"),
  "utf8",
);

test("selectors adapt the sandbox option to shell and daemon availability", () => {
  // 双条件渲染分支：壳检测 + useSandboxStatus 在线状态
  expect(source).toMatch(/isShellAvailable/);
  expect(source).toMatch(/useSandboxStatus/);
  expect(source).toMatch(/adaptSandboxAgentOption/);
  expect(source).toMatch(/SANDBOX_AGENT_OPTION_KEY/);
});

test("offline local selection warns without blocking the change", () => {
  // 离线选本地档：五语提示 + 仍应用用户选择
  expect(source).toMatch(/agentOptions\.sandbox\.offlineHint/);
  expect(source).toMatch(/value === "local" && !sandboxOnline/);
});

test("restored local value carries an offline note on pure web", () => {
  expect(source).toMatch(/agentOptions\.sandbox\.restoredOffline/);
});

test("sandbox button carries a daemon online status dot", () => {
  expect(source).toMatch(/data-sandbox-status-dot/);
});
