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

test("身份 chip 自适应截断：空间足够完整显示，不足才出省略号", () => {
  const chip = readRepoFile("src/components/chat/ToolbarChip.tsx");
  // Tailwind 截断正解：标签 min-w-0 + truncate（无 max-w 上限，自然宽度完整
  // 显示、行内受挤先出 …）；按钮 overflow-hidden 兜底，链路再断也只裁自己
  // 不重叠
  expect(chip).toMatch(/shrink min-w-0 overflow-hidden/);
  expect(chip).toMatch(/min-w-0 truncate text-sm/);
});

test("右簇沙箱 chip 手机端仅图标（与用量图标一致）", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  // 档位文字与 daemon 状态点都在 sm 断点以下隐藏，只留档位图标
  expect(toolbar).toMatch(/labelClassName="hidden sm:inline"/);
  expect(toolbar).toMatch(
    /hidden sm:inline h-1\.5 w-1\.5 shrink-0 rounded-full/,
  );
});

test("工具栏右簇与左行图标同轴居中，不再贴底错位", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  expect(toolbar).toMatch(
    /flex shrink-0 items-center gap-1 sm:gap-1\.5 self-center/,
  );
  expect(toolbar).not.toMatch(/self-end/);
});

test("工具栏左行不再横向滚动，手机端超宽靠 chip 截断降级", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  // 滚动容器会在手机端把 chip 裁切在不可见边界上，视觉上与右簇重叠；
  // 改为 chip shrink + truncate 优雅降级（FeatureMenu 触发键有 min-width 兜底）
  expect(toolbar).not.toMatch(/overflow-x-auto/);
});

test("沙箱 chip 归入右簇与用量监控同组，不混入左侧身份 chip 行", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  const clusterIdx = toolbar.indexOf(
    "flex shrink-0 items-center gap-1 sm:gap-1.5 self-center",
  );
  const sandboxIdx = toolbar.indexOf("data-sandbox-status-dot");
  const usageIdx = toolbar.indexOf("<ComposerUsageChip");
  // 顺序：右簇开标签 < 沙箱 chip < 用量 chip（沙箱在簇内最左）
  expect(clusterIdx).toBeGreaterThan(-1);
  expect(sandboxIdx).toBeGreaterThan(clusterIdx);
  expect(usageIdx).toBeGreaterThan(sandboxIdx);
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
