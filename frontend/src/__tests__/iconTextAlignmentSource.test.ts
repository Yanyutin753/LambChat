import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("text-box-trim utility exists for ink-centered icon+text rows", () => {
  const utilities = readRepoFile("src/styles/utilities.css");

  expect(utilities).toMatch(
    /\.text-box-trim\s*\{[^}]*text-box-trim:\s*trim-both/s,
  );
  expect(utilities).toMatch(
    /\.text-box-trim\s*\{[^}]*text-box-edge:\s*text/s,
  );
});

test("ToolbarChip label opts into text-box-trim to align CJK text with icons", () => {
  const chip = readRepoFile("src/components/chat/ToolbarChip.tsx");
  const labelLine = chip
    .split("\n")
    .find((line) => line.includes("font-serif"));

  expect(labelLine).toContain("text-box-trim");
});

test("sidebar nav labels and section titles opt into text-box-trim", () => {
  const list = readRepoFile(
    "src/components/panels/SidebarParts/SessionListContent.tsx",
  );
  const trimmedSpans = (list.match(/<span[^>]*text-box-trim[^>]*>/g) ?? [])
    .length;

  expect(trimmedSpans).toBeGreaterThanOrEqual(8);
});

test("data table copy/export buttons wrap labels in text-box-trim", () => {
  const markdown = readRepoFile(
    "src/components/chat/ChatMessage/MarkdownContent.tsx",
  );

  expect((markdown.match(/text-box-trim/g) ?? []).length).toBeGreaterThanOrEqual(
    2,
  );
});

test("session item title opts into text-box-trim", () => {
  const item = readRepoFile("src/components/sidebar/SessionItem.tsx");

  expect(item).toMatch(/text-box-trim/);
});
