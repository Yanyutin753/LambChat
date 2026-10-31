import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");
test("sandbox control is only in the workspace strip", () => {
  expect(read("../ChatInputToolbar.tsx")).not.toContain(
    "data-sandbox-status-dot",
  );
  expect(read("../ChatInput.tsx")).toContain("<ComposerSandboxChip");
});
test("usage stays in the composer toolbar", () => {
  expect(read("../../layout/AppContent/Header.tsx")).not.toContain(
    "<ComposerUsageChip",
  );
  expect(read("../ChatInputToolbar.tsx")).toContain("<ComposerUsageChip");
});

test("workspace controls remain one horizontally scrollable row in the composer and skeleton", () => {
  for (const path of [
    "../ChatInput.tsx",
    "../../skeletons/ChatSkeletons.tsx",
  ]) {
    expect(read(path)).toMatch(/composer-workspace-strip[^"\n]*flex-nowrap/);
  }
  const css = read("../../../styles/chat.css");
  expect(css).toMatch(
    /\.composer-workspace-strip > \*\s*\{[^}]*flex:\s*0 0 auto;/,
  );
  expect(css).toMatch(
    /\.composer-workspace-strip\s*\{[^}]*overflow-x:\s*auto;/,
  );
});

test("workspace strip keeps a compact vertical rhythm and aligns with the editor column", () => {
  // 本地电脑/工作区上下文条只留极小上下留白（2026-10-28 用户反馈"上下间距小一点点"）；
  // 横向与编辑区文字列对齐（2026-10-31 条带与输入卡融合为同一张卡）
  const css = read("../../../styles/chat.css");
  expect(css).toMatch(
    /\.composer-workspace-strip\s*\{[^}]*padding:\s*0\.25rem calc\(var\(--chat-content-inset\) - 1px\) 1rem;/,
  );
});

test("local directory selection lives in the workspace strip while the submit guard stays mounted", () => {
  const input = read("../ChatInput.tsx");
  const strip = input.slice(
    input.indexOf('className="composer-workspace-strip'),
    input.indexOf("ref={containerRef}"),
  );
  expect(strip).toContain('agentOptionValues.sandbox === "local"');
  expect(strip).toContain("ref={setWorkspaceHost}");
  expect(input).not.toContain("ComposerProjectSelector");
  expect(input).toContain("host={workspaceHost}");
  expect(read("../ChatInputSelectors.tsx")).not.toContain("onWorkspaceHost");
  expect(read("../ComposerSandboxChip.tsx")).not.toContain(
    "resolveSandboxButtonLabel",
  );
});

test("narrow workspace strip stays fused to the card without horizontal insets", () => {
  // 条带与输入卡同宽融合后,窄视口不得重新引入横向 margin/padding 覆盖,
  // 否则条带会比卡片窄、左右错位（横向缩进统一由 --chat-content-inset 驱动）。
  const css = read("../../../styles/chat.css");
  const narrow = css.match(
    /@container workspace \(max-width: 40rem\) \{([\s\S]*?)\n\}/,
  )?.[1];
  expect(narrow).toMatch(/\.composer-workspace-strip\s*\{/);
  expect(narrow).not.toMatch(/margin-inline|padding-left/);
});
