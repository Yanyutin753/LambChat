import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SubagentBlocks.tsx", import.meta.url),
  "utf8",
);

test("thinking and subagent sidebars use a lightweight renderer for long or streaming text", () => {
  expect(source).toMatch(/function SidebarMarkdownContent/);
  expect(source).toMatch(/SIDEBAR_MARKDOWN_PREVIEW_LIMIT/);
  expect(source).toMatch(/SUBAGENT_PARTS_PREVIEW_LIMIT/);
  expect(source).toMatch(/const shouldUsePreview =/);
  expect(source).toMatch(/const shouldUsePartsPreview =/);
  expect(source).toMatch(/w-full overflow-auto whitespace-pre-wrap/);
  expect(source).toMatch(/from-theme-bg-card/);
  expect(source).not.toMatch(/<pre className=/);

  expect(source).toMatch(/<SidebarMarkdownContent\s+content=\{content\}/);
  expect(source).toMatch(/<SidebarMarkdownContent\s+content=\{data\.input\}/);
  expect(source).toMatch(/<SidebarMarkdownContent\s+content=\{data\.result\}/);
  expect(source).toMatch(/<SidebarMarkdownContent\s+content=\{partsText\}/);
});
