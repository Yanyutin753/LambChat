import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SubagentBlock.tsx", import.meta.url),
  "utf8",
);

test("subagent card uses shared theme surfaces and status text without redundant icons", () => {
  expect(source).toContain("border border-theme-border-subtle");
  expect(source).toContain("bg-theme-bg-card");
  expect(source).not.toContain("SubagentStatusIcon");
  expect(source).toContain("chat.message.toolSubagentFailed");
  expect(source).toContain("chat.cancelled");
  expect(source).not.toMatch(/ring-(?:stone|amber|emerald|red)-/);
  expect(source).not.toMatch(/subagent-border-pulse/);
});

test("subagent card has a keyboard accessible full-width trigger", () => {
  expect(source).toContain("<button");
  expect(source).toContain("min-h-11");
  expect(source).toContain("focus-visible:outline");
});

test("subagent sidebar timestamp is rendered in the panel footer", () => {
  // 时间戳页脚工厂迁至 subagentPanelState：面板 host 与 SubagentBlock 共用，
  // 面板打开期间的时间戳/状态由 host 实时刷新（与虚拟化滚动无关）
  const panelStateSource = readFileSync(
    new URL("../subagentPanelState.tsx", import.meta.url),
    "utf8",
  );
  expect(panelStateSource).toMatch(/export function createSubagentPanelFooter/);
  expect(source).toMatch(/footer: createSubagentPanelFooter\(subtitle\)/);
  expect(source).not.toMatch(
    /subtitle,\s*\n\s*panelKey,\s*\n\s*children: <SubagentPanelContent/,
  );
});
