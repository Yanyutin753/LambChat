import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = (name: string) =>
  readFileSync(new URL(`../${name}.tsx`, import.meta.url), "utf8");

test("tool copy controls do not force a bordered background or compress the shared hit area", () => {
  for (const name of [
    "MemoryStoreItem",
    "ImageGenerateItem",
    "ReadFileItem",
    "TeamItem",
    "PersonaItem",
  ]) {
    const copies = source(name).match(
      /<(?:ToolHoverCopyButton|CopyButton)\b[^>]*\/>/g,
    );
    expect(copies?.join("\n")).not.toMatch(
      /(?:copyButtonClassName|className)="[^"]*!(?:h-6|w-6|bg-theme-bg-card\/80|border)/,
    );
  }
});

test("tool metadata uses the same badge primitive across result families", () => {
  for (const name of [
    "MemoryStoreItem",
    "MemoryRecallItem",
    "TeamItem",
    "PersonaItem",
    "SkillSearchItem",
    "ImageGenerateItem",
    "ScheduledTaskItem",
    "ToolSearchItem",
    "AudioTranscribeItem",
    "DocumentParseItem",
    "GrepItem",
    "ConversationHistoryItem",
    "EvalItem",
  ]) {
    expect(source(name)).toContain("<TagBadge");
  }
});

test("built-in and MCP detail containers own their section spacing", () => {
  const css = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\.tool-readable \.tool-panel-content\s*\{[^}]*display: flex;[^}]*gap: 1\.25rem;/,
  );
});

test("desktop card decoration cannot restore a rounded frame around flat tool sections", () => {
  const css = readFileSync(
    new URL("../../../../../styles/desktop.css", import.meta.url),
    "utf8",
  );
  expect(css).not.toContain(
    ":is(.collapsible-section-card--default, .tool-detail-section)",
  );
});
