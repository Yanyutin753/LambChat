import { readdirSync, readFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function listTsxFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return listTsxFiles(path);
    return entry.isFile() && entry.name.endsWith(".tsx") ? [path] : [];
  });
}

const sourceRoot = fileURLToPath(new URL("../../../", import.meta.url));
const directRenderers = listTsxFiles(sourceRoot)
  .map((path) => ({
    // Windows 下 relative() 产出反斜杠分隔符，统一为 / 便于断言
    path: relative(sourceRoot, path).split("\\").join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .filter(({ source }) => source.includes("<ReactMarkdown"));

test("tracks every direct ReactMarkdown renderer", () => {
  expect(directRenderers.map(({ path }) => path).sort()).toEqual([
    "components/chat/ChatMessage/MarkdownContent.tsx",
    "components/layout/AppContent/MessageTimelineRail.tsx",
    "components/layout/AppContent/TaskToastMarkdown.tsx",
    "components/panels/ApprovalPanel.tsx",
    "components/update/ReleaseNotesMarkdown.tsx",
  ]);
});

test.each(directRenderers)(
  "$path uses the shared CJK remark configuration",
  ({ path, source }) => {
    expect(source, path).toContain("...cjkGfmRemarkPlugins");
  },
);
