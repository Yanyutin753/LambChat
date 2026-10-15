import { fileURLToPath } from "node:url";
import postcss from "postcss";
import tailwindcss from "@tailwindcss/postcss";

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

test("Tailwind v4 compiles opacity for every theme color and the neutral scale", async () => {
  const source = [
    '@reference "../styles/tailwind.css";',
    ...THEME_COLORS.map(([name], index) => `.theme-probe-${index} { @apply text-theme-${name}/60; }`),
    ".neutral-probe { @apply bg-stone-900/50; }",
    ".opaque-probe { @apply text-theme-text; }",
  ].join("\n");
  const { css } = await postcss([tailwindcss()]).process(source, {
    from: fileURLToPath(new URL("./theme-alpha-test.css", import.meta.url)),
  });
  for (const [, cssVar] of THEME_COLORS) {
    expect(css).toContain(`var(${cssVar}) 60%`);
  }
  expect(css).toContain("var(--theme-neutral-900,");
  expect(css).toContain("50%, transparent");
  expect(css).toContain("color: var(--theme-text)");
  expect(css).not.toContain("100%, transparent");
});
