import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const imageGenerateSource = readSource("../ImageGenerateItem.tsx");
const editFileSource = readSource("../EditFileItem.tsx");
const markdownSource = readSource("../../MarkdownContent.tsx");
const componentCss = readSource("../../../../../styles/components.css");
const markdownCss = readSource("../../../../../styles/markdown.css");
const chatInputSource = readSource("../../../ChatInput.tsx");
const collapsiblePillSource = readSource(
  "../../../../common/CollapsiblePill.tsx",
);

describe("focused AIcss-inspired component upgrade", () => {
  test("gives pending image generation a dedicated shimmering canvas", () => {
    expect(imageGenerateSource).toContain("ai-image-generation-frame");
    expect(imageGenerateSource).toMatch(/data-state=\{status\}/);
    expect(imageGenerateSource).toMatch(
      /isPending[\s\S]*ai-image-generation-frame/,
    );
    expect(imageGenerateSource).not.toContain("🎨");
    expect(componentCss).toContain(".ai-image-generation-frame");
    expect(componentCss).toContain("@keyframes ai-image-generation-shimmer");
  });

  test("presents file edits as one structured diff surface", () => {
    expect(editFileSource).toContain("ai-file-diff");
    expect(editFileSource).toContain('data-kind="removed"');
    expect(editFileSource).toContain('data-kind="added"');
    expect(componentCss).toContain(".ai-file-diff__header");
    expect(componentCss).toContain(
      '.ai-file-diff__section[data-kind="removed"]',
    );
    expect(componentCss).toContain('.ai-file-diff__section[data-kind="added"]');
  });

  test("uses a quiet framed header for Markdown code blocks", () => {
    expect(markdownSource).toContain("ai-code-block");
    expect(markdownSource).toContain("ai-code-block__header");
    expect(markdownSource).toContain("ai-code-block__copy");
    expect(markdownCss).toContain(".ai-code-block");
    expect(markdownCss).toContain(".ai-code-block__header");
  });

  test("shows a single lightweight caret only while Markdown is streaming", () => {
    expect(markdownSource).toContain(
      "data-streaming={isStreaming || undefined}",
    );
    expect(markdownSource).toContain("aria-busy={isStreaming || undefined}");
    expect(markdownSource).not.toContain("setInterval");
    expect(markdownCss).toContain(
      '.ai-streaming-text[data-streaming="true"] > :last-child::after',
    );
    expect(markdownCss).toContain("@keyframes ai-streaming-caret-blink");
  });

  test("keeps Markdown tables semantic while giving them a tidy data surface", () => {
    expect(markdownSource).toContain("ai-data-table");
    expect(markdownSource).toContain("ai-data-table__toolbar");
    expect(markdownSource).toContain("ai-data-table__table");
    expect(markdownSource).toMatch(/<table[\s\S]*ref=\{tableRef\}/);
    expect(markdownSource).toContain("handleCopy");
    expect(markdownSource).toContain("handleExport");
    expect(markdownCss).toContain(".ai-data-table__head");
    expect(markdownCss).toContain(".ai-data-table__row");
  });

  test("renders comparison values with accessible icon states", () => {
    expect(markdownSource).toContain("getComparisonCellState");
    expect(markdownSource).toContain("data-comparison-state={comparisonState");
    expect(markdownSource).toContain("ai-comparison-value");
    expect(markdownSource).toContain(
      '<span className="sr-only">{cellText}</span>',
    );
    expect(markdownCss).toContain(
      '.ai-data-table__cell[data-comparison-state="included"]',
    );
    expect(markdownCss).toContain(
      '.ai-data-table__cell[data-comparison-state="excluded"]',
    );
  });

  test("honors reduced motion without changing the global chat chrome", () => {
    expect(componentCss).toMatch(
      /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.ai-image-generation-frame/,
    );
    expect(chatInputSource).not.toContain("chat-agent-composer");
    expect(collapsiblePillSource).not.toContain("agent-activity-trigger");
    expect(markdownCss).toMatch(
      /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.ai-streaming-text/,
    );
  });
});
