import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const toolTypeSource = readFileSync(
  new URL("../../../types/tool.ts", import.meta.url),
  "utf8",
);
const selectorSource = readFileSync(
  new URL("../ToolSelector.tsx", import.meta.url),
  "utf8",
);

const localeFiles = ["en", "zh", "ja", "ko", "ru"].map((locale) =>
  new URL(`../../../i18n/locales/${locale}.json`, import.meta.url),
);

function readJson(url: URL) {
  return JSON.parse(readFileSync(url, "utf8")) as {
    tools?: { categories?: { internal?: unknown } };
  };
}

test("tool selector supports internal tools without MCP toggle semantics", () => {
  assert.match(toolTypeSource, /\| "internal"/);
  assert.match(selectorSource, /internal:\s*Workflow/);
  assert.match(selectorSource, /const isToggleableCategory = cat === "mcp"/);
  assert.match(
    selectorSource,
    /const isToggleableTool =\s*tool\.category === "mcp" && !tool\.system_disabled/,
  );
  assert.match(selectorSource, /disabled=\{!isToggleableCategory\}/);
  assert.match(selectorSource, /disabled=\{!isToggleableTool\}/);
  assert.match(
    selectorSource,
    /if \(isToggleableTool\) onToggleTool\(tool\.name\)/,
  );

  for (const localeFile of localeFiles) {
    const locale = readJson(localeFile);
    const label = locale.tools?.categories?.internal;
    assert.equal(typeof label, "string");
    if (typeof label !== "string") assert.fail("internal label is missing");
    assert.notEqual(label.trim(), "");
  }
});
