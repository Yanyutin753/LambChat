import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

const source = readFileSync(
  new URL("../CollapsiblePill.tsx", import.meta.url),
  "utf8",
);
const animationSource = readFileSync(
  new URL("../../../styles/animations.css", import.meta.url),
  "utf8",
);
const chatSource = readFileSync(
  new URL("../../../styles/chat.css", import.meta.url),
  "utf8",
);

describe("CollapsiblePill alignment", () => {
  test("uses the body text weight for disclosure labels and tool groups", () => {
    expect(animationSource).toMatch(/\.pill-btn\s*\{[^}]*font-normal/);
    expect(chatSource).toMatch(
      /\.chat-tool-category \.chat-tool-call-group__toggle\s*\{[^}]*font-weight:\s*400;/,
    );
  });
  test("sizes animated icon wrappers to match the shared search icon", () => {
    expect(animationSource).toMatch(
      /\.pill-btn__icon \.interactive-action-icon > div\s*\{[^}]*width:\s*1rem;[^}]*height:\s*1rem;/,
    );
  });

  test("uses the shared tool font for disclosure labels and groups", () => {
    expect(animationSource).toMatch(
      /\.pill-btn\s*\{[^}]*font-family:\s*var\(--chat-font-family\);[^}]*font-size:\s*var\(--tool-font-size\)/,
    );
    expect(chatSource).toMatch(
      /\.chat-tool-category \.chat-tool-call-group__toggle\s*\{[^}]*font-family:\s*var\(--chat-font-family\);[^}]*font-size:\s*var\(--tool-font-size\)/,
    );
    expect(animationSource).not.toContain(
      'font-family: theme("fontFamily.sans")',
    );
    expect(animationSource).toMatch(
      /\.pill-btn > span\s*\{[^}]*line-height: inherit;/,
    );
    expect(animationSource).toMatch(
      /\.pill-btn > svg\s*\{[^}]*block[^}]*size-3[^}]*shrink-0/,
    );
    expect(source).not.toContain("tracking-[0.01em]");
    expect(source).not.toContain("translate-y-px");
  });

  test("does not lift the pill on touch hover states", () => {
    expect(animationSource).toMatch(
      /@media \(hover: none\), \(pointer: coarse\)[\s\S]*?\.pill-btn:hover:not\(:disabled\)\s*\{[\s\S]*?transform:\s*none;/,
    );
  });

  test("does not lift the pill on any hover state", () => {
    expect(animationSource).not.toContain("transform: translateY(-1px);");
  });
});

test("shares one tool font across disclosures, panels, status and todos", () => {
  const tokens = readFileSync(
    new URL("../../../styles/tokens.css", import.meta.url),
    "utf8",
  );
  const components = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(tokens).toContain("--tool-font-size: 0.8125rem;");
  expect(animationSource).toMatch(
    /\.pill-btn > span\s*\{[^}]*font-size: inherit;/,
  );
  expect(animationSource).toMatch(
    /\.pill-btn__suffix \*\s*\{[^}]*font-size: inherit;/,
  );
  for (const selector of [
    ".tool-console-header",
    ".tool-console-title",
    ".tool-console-subtitle-pill",
    ".tool-duration-footer",
    ".tool-readable :is(pre, code)",
    ".tool-readable :is(.font-mono, .cm-editor, .cm-scroller)",
  ]) {
    const rule = components.split("\n" + selector + " {")[1]?.split("}")[0];
    expect(rule).toContain("font-size: var(--tool-font-size);");
  }
  expect(source).not.toContain("text-12");
});
