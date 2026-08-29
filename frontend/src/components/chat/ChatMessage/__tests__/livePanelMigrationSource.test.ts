import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

const rendererSource = readFileSync(
  resolve(
    import.meta.dirname,
    "../MessagePartRenderer.tsx",
  ),
  { encoding: "utf8" },
);

const chatViewSource = readFileSync(
  resolve(import.meta.dirname, "../../../layout/AppContent/ChatView.tsx"),
  { encoding: "utf8" },
);

const subagentBlockSource = readFileSync(
  resolve(import.meta.dirname, "../SubagentBlock.tsx"),
  { encoding: "utf8" },
);

/** 专属工具项名单（与 MessagePartRenderer 的路由一一对应） */
const DEDICATED_ITEMS = [
  "ReadFileItem",
  "EditFileItem",
  "WriteFileItem",
  "GrepItem",
  "LsItem",
  "GlobItem",
  "ExecuteItem",
  "EvalItem",
  "ImageGenerateItem",
  "ImageAnalyzeItem",
  "AudioTranscribeItem",
  "UploadUrlToSandboxItem",
  "TransferItem",
  "ScheduledTaskItem",
  "EnvVarItem",
  "PersonaItem",
  "TeamItem",
  "MemoryRecallItem",
  "MemoryStoreItem",
  "AskHumanItem",
  "ToolSearchItem",
] as const;

test("every dedicated tool item receives the part id for live panel wiring", () => {
  for (const item of DEDICATED_ITEMS) {
    const used = rendererSource.includes(`<${item}`);
    if (!used) continue;
    const segment = rendererSource.split(`<${item}`)[1]?.split("</")[0] ?? "";
    // FileReveal/ProjectReveal 等不需要 panelKey；专属工具项必须能拿到 part.id
    expect(
      segment.includes("id={part.id}"),
      `${item} should receive id={part.id}`,
    ).toBe(true);
  }
});

test("dedicated tool items open live panels through openToolLivePanel", () => {
  const itemsDir = resolve(import.meta.dirname, "../items");
  for (const item of DEDICATED_ITEMS) {
    const source = readFileSync(resolve(itemsDir, `${item}.tsx`), "utf8");
    if (!source.includes("onPanelOpen")) continue;
    expect(
      source.includes("openToolLivePanel"),
      `${item} should open its panel via openToolLivePanel`,
    ).toBe(true);
    // 静态快照只允许作为 fallback 参数出现
    expect(
      source.includes("openPersistentToolPanel({"),
      `${item} must not open a static-snapshot panel directly`,
    ).toBe(false);
  }
});

test("subagent panel data survives message virtualization", () => {
  // 卸载即删数据会让侧边栏内容在滚动时消失；数据生命周期由 ChatView 管理
  expect(subagentBlockSource).not.toMatch(/subagentPanelStore\.delete/);
  expect(subagentBlockSource).not.toMatch(/subagentPanelStore\.set\(/);
});

test("ChatView keeps both panel stores in sync with the message list", () => {
  expect(chatViewSource).toMatch(/syncToolCallPanelStore\(messages\)/);
  expect(chatViewSource).toMatch(/syncSubagentPanelStore\(messages\)/);
  // 会话切换时统一清理，替代组件卸载清理
  expect(chatViewSource).toMatch(/toolCallPanelStore\.clear\(\)/);
  expect(chatViewSource).toMatch(/subagentPanelStore\.clear\(\)/);
});
