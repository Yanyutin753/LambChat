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
    path: relative(sourceRoot, path),
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
