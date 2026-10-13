import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("运行模式仅在桌面模型旁显示，不占用可编辑消息文本", () => {
  const chatInput = readRepoFile("src/components/chat/ChatInput.tsx");
  const composer = chatInput.match(/<RichChatComposer\s[\s\S]*?\/>/)?.[0];
  expect(composer).toBeDefined();
  expect(composer).not.toMatch(/runModes=/);
  expect(chatInput).toContain(
    "runModes: collectActiveRunModes(autoModeEnabled, goalModeEnabled)",
  );
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  expect(toolbar).toMatch(/data-composer-run-modes/);
  expect(toolbar).toMatch(/className="hidden shrink-0 items-center gap-1\.5 sm:flex"/);
  expect(toolbar.indexOf("data-composer-run-modes")).toBeGreaterThan(
    toolbar.indexOf("<ToolbarChip"),
  );
  expect(toolbar.indexOf("data-composer-run-modes")).toBeLessThan(
    toolbar.indexOf("flex shrink-0 items-center gap-1.5 self-center"),
  );
});

test("工具栏右侧操作区不再渲染运行模式文字按钮", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  expect(toolbar).not.toMatch(/t\("mode\.auto"/);
  expect(toolbar).not.toMatch(/t\("mode\.goal"/);
});

test("手机运行模式触发按钮显示激活状态角标", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  // 手机端模式文字隐藏后，由设置图标角标提示启用状态。
  const trigger = toolbar.match(/<button\s[^>]*data-run-mode-trigger[\s\S]*?<\/button>/)?.[0];
  expect(trigger).toBeDefined();
  expect(trigger).toContain("data-run-mode-status-dot");
  expect(trigger).toContain("sm:hidden");
  expect(trigger).not.toContain("data-sandbox-status-dot");
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
  expect(chip).toMatch(/min-w-0 truncate text-14/);
});

test("右簇沙箱 chip 手机端显示图标和状态角标，隐藏档位文字", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  // 手机端保留档位图标和 daemon 状态角标。
  expect(toolbar).toMatch(
    /labelClassName="composer-sandbox-label hidden sm:inline max-w-40"/,
  );
  expect(toolbar).toMatch(
    /absolute -top-0\.5 -right-0\.5 block h-\[5px\] w-\[5px\] rounded-full ring-2/,
  );
});

test("工具栏右簇与左行图标同轴居中，不再贴底错位", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  expect(toolbar).toMatch(
    /flex shrink-0 items-center gap-1\.5 self-center/,
  );
  expect(toolbar).not.toMatch(/self-end/);
});

test("工具栏左行不再横向滚动，手机端超宽靠 chip 截断降级", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  // 滚动容器会在手机端把 chip 裁切在不可见边界上，视觉上与右簇重叠；
  // 改为 chip shrink + truncate 优雅降级（FeatureMenu 触发键有 min-width 兜底）
  expect(toolbar).not.toMatch(/overflow-x-auto/);
});

test("沙箱 chip 归入右簇，不混入左侧身份 chip 行", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  const clusterIdx = toolbar.indexOf(
    "flex shrink-0 items-center gap-1.5 self-center",
  );
  const sandboxIdx = toolbar.indexOf("data-sandbox-status-dot");
  // 沙箱保留在右簇，用量入口已移到页头。
  expect(clusterIdx).toBeGreaterThan(-1);
  expect(sandboxIdx).toBeGreaterThan(clusterIdx);
  expect(toolbar).not.toContain("ComposerUsageChip");
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


test("桌面模式入口与模型之间用主题竖线分隔", () => {
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  const modes = toolbar.slice(toolbar.indexOf("data-composer-run-modes"));
  expect(modes).toMatch(/aria-hidden="true" className="h-4 w-px shrink-0 bg-theme-border"/);
  expect(modes.indexOf("bg-theme-border")).toBeLessThan(modes.indexOf("activeModes.map"));
});
