import { readFileSync } from "node:fs";
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
  expect(toolTypeSource).toMatch(/\| "internal"/);
  expect(selectorSource).toMatch(/internal:\s*Workflow/);
  expect(selectorSource).toMatch(/const isToggleableCategory = cat === "mcp"/);
  expect(selectorSource).toMatch(/const isToggleableTool =\s*tool\.category === "mcp" && !tool\.system_disabled/);
  expect(selectorSource).toMatch(/disabled=\{!isToggleableCategory\}/);
  expect(selectorSource).toMatch(/disabled=\{!isToggleableTool\}/);
  expect(selectorSource).toMatch(/if \(isToggleableTool\) onToggleTool\(tool\.name\)/);

  for (const localeFile of localeFiles) {
    const locale = readJson(localeFile);
    const label = locale.tools?.categories?.internal;
    expect(typeof label).toBe("string");
    if (typeof label !== "string") throw new Error("internal label is missing");
    expect(label.trim()).not.toBe("");
  }
});
