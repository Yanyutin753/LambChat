import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");
test("sandbox control is only in the workspace strip", () => {
  expect(read("../ChatInputToolbar.tsx")).not.toContain(
    "data-sandbox-status-dot",
  );
  expect(read("../ChatInput.tsx")).toContain("<ComposerSandboxChip");
});
test("usage stays in the composer toolbar", () => {
  expect(read("../../layout/AppContent/Header.tsx")).not.toContain(
    "<ComposerUsageChip",
  );
  expect(read("../ChatInputToolbar.tsx")).toContain("<ComposerUsageChip");
});

test("workspace controls remain one horizontally scrollable row in the composer and skeleton", () => {
  for (const path of [
    "../ChatInput.tsx",
    "../../skeletons/ChatSkeletons.tsx",
  ]) {
    expect(read(path)).toMatch(/composer-workspace-strip[^"\n]*flex-nowrap/);
  }
  const css = read("../../../styles/chat.css");
  expect(css).toMatch(
    /\.composer-workspace-strip > \*\s*\{[^}]*flex:\s*0 0 auto;/,
  );
  expect(css).toMatch(
    /\.composer-workspace-strip\s*\{[^}]*overflow-x:\s*auto;/,
  );
});

test("local directory selection lives in the workspace strip while the submit guard stays mounted", () => {
  const input = read("../ChatInput.tsx");
  const strip = input.slice(
    input.indexOf('className="composer-workspace-strip'),
    input.indexOf("ref={containerRef}"),
  );
  expect(strip).toContain('agentOptionValues.sandbox === "local"');
  expect(strip).toContain("ref={setWorkspaceHost}");
  expect(input).not.toContain("ComposerProjectSelector");
  expect(input).toContain("host={workspaceHost}");
  expect(read("../ChatInputSelectors.tsx")).not.toContain("onWorkspaceHost");
  expect(read("../ComposerSandboxChip.tsx")).not.toContain(
    "resolveSandboxButtonLabel",
  );
});

test("narrow workspace strip compensates its smaller margin to preserve the icon edge", () => {
  const css = read("../../../styles/chat.css");
  const narrow = css.match(
    /@container workspace \(max-width: 40rem\) \{([\s\S]*?)\n\}/,
  )?.[1];
  expect(narrow).toMatch(
    /\.composer-workspace-strip\s*\{[^}]*margin-inline:\s*0?\.5rem;[^}]*padding-left:\s*0?\.5rem;/,
  );
});
