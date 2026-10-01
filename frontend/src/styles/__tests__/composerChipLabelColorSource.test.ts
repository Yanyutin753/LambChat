import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");

test("toolbar label tuning keeps chip label color intact", () => {
  const rule = css.match(/\.chat-input-toolbar\s+\.font-serif\s*\{[^}]*\}/);
  expect(rule).not.toBeNull();
  // 桌面端降噪只调字号/字重，不得声明 color——
  // 否则会以更高特异度压掉 ToolbarChip/ComposerUsageChip 标签的
  // text-blue-600 dark:text-blue-400（Agent 名/沙箱档位/当日费用全部变灰）
  expect(rule?.[0]).toMatch(/font-size/);
  expect(rule?.[0]).not.toMatch(/^\s*color:/m);
});
