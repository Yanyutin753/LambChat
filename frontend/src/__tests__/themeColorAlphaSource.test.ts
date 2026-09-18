import { readFileSync } from "node:fs";
import { join } from "node:path";

// theme-* 工具色若以裸 var() 字符串声明，Tailwind v3 无法为透明度修饰符
// 注入 alpha：border-theme-border/60 这类 class 会静默不生成，边框色回落
// preflight 默认 #e5e7eb，深色模式下呈现刺眼白边（web_search 来源胶囊即
// 此 bug）。守护：theme 色板必须走 color-mix + <alpha-value> 模式，
// 无修饰符时 100% 混合等于原色，视觉零回归。
const tailwindConfig = readFileSync(
  join(import.meta.dirname, "../../tailwind.config.js"),
  "utf8",
);

const THEME_COLORS: [name: string, cssVar: string][] = [
  ["text", "--theme-text"],
  ["text-secondary", "--theme-text-secondary"],
  ["text-tertiary", "--theme-text-tertiary"],
  ["bg", "--theme-bg"],
  ["bg-card", "--theme-bg-card"],
  ["bg-elevated", "--theme-bg-elevated"],
  ["bg-subtle", "--theme-bg-subtle"],
  ["bg-code", "--theme-bg-code"],
  ["border", "--theme-border"],
  ["border-hover", "--theme-border-hover"],
  ["border-subtle", "--theme-border-subtle"],
  ["border-faint", "--theme-border-faint"],
  ["primary", "--theme-primary"],
  ["primary-hover", "--theme-primary-hover"],
  ["primary-light", "--theme-primary-light"],
  ["toggle-knob", "--theme-toggle-knob"],
  ["success", "--theme-success"],
  ["error", "--theme-error"],
  ["warning", "--theme-warning"],
  ["info", "--theme-info"],
];

test.each(THEME_COLORS)("theme 色 %s 支持透明度修饰符", (name, cssVar) => {
  expect(
    tailwindConfig,
    `theme.${name} 需以 color-mix(in srgb, var(${cssVar}) calc(<alpha-value> * 100%), transparent) 声明，` +
      `否则 /透明度 修饰符的 class 静默不生成（深色模式白边 bug）`,
  ).toMatch(
    new RegExp(
      `"?${name}"?\\s*:\\s*"color-mix\\(in srgb, var\\(${cssVar}\\) calc\\(<alpha-value> \\* 100%\\), transparent\\)"`,
    ),
  );
});
