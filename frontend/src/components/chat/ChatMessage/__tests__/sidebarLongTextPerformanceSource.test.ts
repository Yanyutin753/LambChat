import { readFileSync } from "node:fs";

const sidebarSource = readFileSync(
  new URL("../SidebarMarkdownContent.tsx", import.meta.url),
  "utf8",
);
const panelSource = readFileSync(
  new URL("../SubagentPanelContent.tsx", import.meta.url),
  "utf8",
);
const thinkingSource = readFileSync(
  new URL("../ThinkingBlock.tsx", import.meta.url),
  "utf8",
);

test("thinking sidebars keep their long-text preview while subagents reuse the main chat renderer", () => {
  expect(sidebarSource).toMatch(/function SidebarMarkdownContent/);
  expect(sidebarSource).toMatch(/SIDEBAR_MARKDOWN_PREVIEW_LIMIT/);
  expect(sidebarSource).toMatch(/SUBAGENT_PARTS_PREVIEW_LIMIT/);
  expect(sidebarSource).toMatch(/const shouldUsePreview =/);
  expect(sidebarSource).toMatch(/w-full overflow-auto whitespace-pre-wrap/);
  expect(sidebarSource).toMatch(/from-theme-bg-card/);
  expect(sidebarSource).not.toMatch(/<pre className=/);

  expect(thinkingSource).toMatch(
    /<SidebarMarkdownContent\s+content=\{displayContent\}/,
  );
  expect(panelSource).toMatch(/import \{ ChatMessage \} from "\.\/index"/);
  expect(panelSource).toMatch(/<ChatMessage[\s\S]*?message=\{message\}/);
  expect(panelSource).not.toMatch(/SidebarMarkdownContent/);
});
