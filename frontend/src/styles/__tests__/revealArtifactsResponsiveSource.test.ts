import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(
  new URL(
    "../../components/chat/ChatMessage/RevealArtifactsSummary.tsx",
    import.meta.url,
  ),
  "utf8",
);
const css = readFileSync(new URL("../components.css", import.meta.url), "utf8");

test("narrow artifact cards hide the batch download label and reclaim title space", () => {
  expect(source).toContain("reveal-artifacts-summary");
  expect(source).toContain("reveal-artifacts-toggle");
  expect(source).toContain('className="reveal-artifacts-download-label"');
  expect(source).toMatch(/aria-label=\{t\("chat.message.downloadAll"/);
  expect(source).toMatch(/<Tooltip content=\{t\("chat.message.downloadAll"/);
  expect(css).toMatch(
    /\.reveal-artifacts-summary\s*\{[^}]*container:\s*reveal-artifacts\s*\/\s*inline-size/,
  );
  expect(css).toMatch(
    /@container reveal-artifacts \(max-width: 399px\)\s*\{\s*\.reveal-artifacts-download-label\s*\{\s*display:\s*none;\s*\}\s*\.reveal-artifacts-toggle\s*\{\s*padding-right:\s*6rem;/,
  );
});

const renderer = readFileSync(
  new URL(
    "../../components/chat/ChatMessage/MessagePartRenderer.tsx",
    import.meta.url,
  ),
  "utf8",
);

test("artifact outline anchors do not occupy flex gaps", () => {
  const artifact = renderer.slice(
    renderer.indexOf('if (part.type === "artifact")'),
    renderer.indexOf('if (part.type === "tool")'),
  );
  expect(artifact).toContain('className="absolute h-0');
  expect(artifact).toContain("id={toolPartAnchorId}");
});
