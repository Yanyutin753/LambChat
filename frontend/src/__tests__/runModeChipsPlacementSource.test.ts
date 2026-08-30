import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("运行模式 chip 作为消息内联节点接入编辑器", () => {
  const chatInput = readRepoFile("src/components/chat/ChatInput.tsx");
  expect(chatInput).toMatch(/runModes=\{buildRunModesOptions\(/);
  expect(chatInput).toMatch(
    /buildRunModesOptions\(\s*autoModeEnabled,\s*goalModeEnabled,\s*onToggleAutoMode,\s*onToggleGoalMode,/,
  );
  // 不再在输入框上方渲染独立的 chip 行
  expect(chatInput).not.toMatch(/<RunModeChips/);
});

test("工具栏右侧操作区不再渲染运行模式文字按钮", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  expect(toolbar).not.toMatch(/t\("mode\.auto"/);
  expect(toolbar).not.toMatch(/t\("mode\.goal"/);
});

test("运行模式触发按钮不再渲染激活状态圆点", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  // 模式状态已由输入框内的 chip 呈现，触发按钮无需再叠加圆点
  expect(toolbar).not.toMatch(/Status dot/);
  expect(toolbar).not.toMatch(/-right-0\.5/);
});

test("RunModeReferenceNode 复用 skill-chip 视觉并支持点击/退格关闭", () => {
  const chip = readRepoFile("src/components/chat/richComposer/RunModeChip.tsx");
  expect(chip).toMatch(/skill-chip-node/);
  expect(chip).toMatch(/skill-chip-node-avatar/);
  expect(chip).toMatch(/skill-chip-node-name/);

  const node = readRepoFile(
    "src/components/chat/richComposer/nodes/RunModeReferenceNode.tsx",
  );
  expect(node).toMatch(/TOGGLE_RUN_MODE_COMMAND/);

  const deletion = readRepoFile(
    "src/components/chat/richComposer/AtomicReferenceDeletionPlugin.tsx",
  );
  expect(deletion).toMatch(/RunModeReferenceNode/);

  const projection = readRepoFile(
    "src/components/chat/richComposer/composerProjection.ts",
  );
  expect(projection).toMatch(/run-mode-reference/);
});

test("用量 chip 在手机端仅显示图标", () => {
  const chip = readRepoFile("src/components/chat/ComposerUsageChip.tsx");
  // 金额文本在 sm 断点以下隐藏，只保留 Activity 图标
  expect(chip).toMatch(/hidden sm:inline/);
});

test("运行模式 chip 与相邻内容保留呼吸间距", () => {
  const chip = readRepoFile("src/components/chat/richComposer/RunModeChip.tsx");
  expect(chip).toMatch(/run-mode-chip-node/);

  const css = readRepoFile("src/styles/chat.css");
  expect(css).toMatch(/\.run-mode-chip-node\s*\{[^}]*margin/);
});

test("发送后的用户消息携带运行模式 chip", () => {
  const bubble = readRepoFile(
    "src/components/chat/ChatMessage/UserMessageBubble.tsx",
  );
  expect(bubble).toMatch(/RunModeChip/);
  // 只读展示：不渲染交互语义（role=button）
  expect(bubble).not.toMatch(/role="button"/);

  const messageView = readRepoFile("src/components/chat/ChatMessage/index.tsx");
  expect(messageView).toMatch(/runModes=\{message\.runModes\}/);
});
