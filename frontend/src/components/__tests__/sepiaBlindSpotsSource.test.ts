import { readFileSync } from "node:fs";
import { join } from "node:path";

// 护眼（sepia）盲区扫尾守卫（proto/sepia-blindspots 评审线）：
// 升级带入的新 UI（桌面壳/会话列表/设置/工作区/聊天条目/auth）沿用
// 个人信息模块的结论——浅色路径硬编码 stone/green/red 不随 sepia 变暖。
// 本测试扫描下列文件的「生效类名」：剥掉 dark: 变体与
// protoCls("after", "before") 评审包装的 before 参数后，浅色路径
// 不得再出现硬编码中性色/状态色（实心红 CTA 与 amber 品牌强调豁免，
// 与 profileSepiaTokenSource.test.ts 同规则）。

const files = [
  "layout/DesktopSidebarShell/DesktopSidebarShell.tsx",
  "sidebar/SessionItem.tsx",
  "panels/SidebarParts/SessionListContent.tsx",
  "workspacePanel/WorkspacePanel.tsx",
  "panels/SettingsPanel.tsx",
  "chat/ChatMessage/MermaidDiagram.tsx",
  "documents/previews/MermaidDiagram.tsx",
  "chat/ChatMessage/items/ExecuteItem.tsx",
  "chat/ChatMessage/items/ScheduledTaskItem.tsx",
  "chat/ChatMessage/items/WebFetchItem.tsx",
  "auth/AuthPage.tsx",
  "auth/ForgotPassword.tsx",
  "auth/ResetPassword.tsx",
  "auth/ServerSetupScreen.tsx",
  "update/UpdateDialog.tsx",
  "mcp/MCPServerCard.tsx",
  "panels/UsagePanel/UsageLogsTable.tsx",
  "panels/ModelPanel/tabs/BatchCreateModal.tsx",
  "persona/PersonaPresetSelector.tsx",
  "common/Dialog.tsx",
];

/** 去掉 dark: 变体段与 protoCls 评审包装的 before 参数，只留生效的浅色路径 */
function effectiveLightPath(source: string): string {
  return source
    .replace(
      /protoCls\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"(?:[^"\\]|\\.)*"\s*,?\s*\)/gs,
      "$1",
    )
    .replace(/(?:[a-zA-Z-]+:)*dark:[^\s"'`{}]+/g, "");
}

const BANNED_PATTERNS: { name: string; pattern: RegExp }[] = [
  {
    name: "stone/slate-*（冷灰中性色）",
    pattern:
      /(?:bg|text|border|ring|from|to|via)-(?:stone|slate)-[\d/]+/,
  },
  { name: "border-white", pattern: /\bborder-white\b/ },
  {
    name: "green-*（状态色请用 theme-success）",
    pattern: /(?:bg|text|border|ring)-(?:green|emerald)-[\d/]+/,
  },
  {
    name: "red-*（文字/边框/浅底）",
    pattern:
      /(?:(?:hover:)?(?:text|border|ring)-(?:red|rose)-[\d/]+)|(?:bg-(?:red|rose)-[1-4][\d/]*\b)/,
  },
];

// 刻意设计为「全主题恒深色」的表面（如 Mermaid 全屏查看器的代码台），
// 不是护眼盲区：这些精确子串在扫描前移除。新增豁免须在此注明理由。
const INTENTIONAL_DARK_SUBSTRINGS = [
  "border-l border-white/10 bg-stone-900",
  "border-b border-white/10",
  "text-stone-300 font-mono",
  "text-green-400",
];

test.each(files)("%s 浅色路径不依赖硬编码中性色/状态色", (file) => {
  const source = readFileSync(
    join(import.meta.dirname, "..", file),
    "utf8",
  );
  let lightPath = effectiveLightPath(source);
  for (const substring of INTENTIONAL_DARK_SUBSTRINGS) {
    lightPath = lightPath.split(substring).join("");
  }
  for (const { name, pattern } of BANNED_PATTERNS) {
    const match = lightPath.match(pattern);
    expect(
      match,
      `${file} 浅色路径出现硬编码 ${name}（"${match?.[0]}"），` +
        `请用 protoCls 包装为 theme-* token（或确认豁免理由）`,
    ).toBeNull();
  }
});
