import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const selectorSource = readFileSync(
  resolve(currentDir, "../PersonaPresetSelector.tsx"),
  "utf8",
);

test("persona selector keeps the manage entry in the sheet header", () => {
  // 管理角色入口与关闭按钮同处头部，手机端收敛为纯图标，不再挤占搜索区
  expect(selectorSource).toMatch(
    /border-b px-5 py-4[\s\S]*?personaPresets\.manage[\s\S]*?<X size=\{18\}/,
  );
  expect(selectorSource).toMatch(
    /<span className="hidden sm:inline">\s*\{t\("personaPresets\.manage"/,
  );
  expect(selectorSource).not.toContain('className="ml-auto');
});

test("persona selector renders clear-current inline with the search input", () => {
  // 清除使用紧跟搜索框容器（同一 flex 行），去掉搜索框上方的独立按钮行
  expect(selectorSource).toMatch(
    /flex items-center gap-2">\s*<div className="relative min-w-0 flex-1">/,
  );
  expect(selectorSource).toMatch(
    /<\/div>\s*\{selectedPresetId && \(\s*<button[\s\S]{0,700}?personaPresets\.clear/,
  );
  expect(selectorSource).not.toContain("|| selectedPresetId ? (");
});
