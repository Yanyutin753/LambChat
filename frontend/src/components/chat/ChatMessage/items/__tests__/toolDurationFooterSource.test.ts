import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

const componentsCss = readFileSync(
  resolve(__dirname, "../../../../../styles/components.css"),
  "utf8",
);

const footerConsumers = [
  "../EditFileItem.tsx",
  "../ExecuteItem.tsx",
  "../GlobItem.tsx",
  "../GrepItem.tsx",
  "../LsItem.tsx",
  "../ReadFileItem.tsx",
  "../WriteFileItem.tsx",
  "../../ToolCallItem.tsx",
];

test("tool item duration footers share one component and formatter", () => {
  const footer = readSource("../ToolDurationFooter.tsx");
  const helper = readSource("../toolDuration.ts");

  expect(helper).toMatch(/export function getToolDurationSeconds/);
  expect(helper).toMatch(/export function formatToolDuration/);
  expect(footer).toMatch(/export function ToolDurationFooter/);
  expect(footer).toMatch(
    /import \{ formatToolDuration, getToolDurationSeconds \}/,
  );
  expect(footer).not.toMatch(/export function formatToolDuration/);
  expect(footer).not.toMatch(/export function getToolDurationSeconds/);
  expect(footer).toMatch(/className="tool-duration-footer"/);
  expect(footer).toMatch(
    /<Clock size=\{11\} className="tool-duration-footer__icon shrink-0" \/>/,
  );
  expect(footer).toMatch(/<span className="tool-duration-footer__text">/);
  expect(componentsCss).toMatch(/\.tool-duration-footer\s*\{/);
  expect(componentsCss).toMatch(/display:\s*flex/);
  expect(componentsCss).toMatch(/align-items:\s*center/);
  expect(componentsCss).toMatch(/gap:\s*0\.375rem/);
  expect(componentsCss).toMatch(/padding:\s*0\.5rem 1rem/);
  expect(componentsCss).toMatch(/border-top:\s*1px solid/);
  expect(componentsCss).toMatch(/font-variant-numeric:\s*tabular-nums/);

  for (const relativePath of footerConsumers) {
    const source = readSource(relativePath);

    expect(source).toMatch(
      /import \{ ToolDurationFooter \} from "\.\/ToolDurationFooter"|import \{ ToolDurationFooter \} from "\.\/items\/ToolDurationFooter"/,
    );
    expect(source).toMatch(
      /<ToolDurationFooter startedAt=\{startedAt\} completedAt=\{completedAt\} \/>/,
    );
    expect(source).not.toMatch(/Math\.round\(ms \/ 1000\)/);
    expect(source).not.toMatch(
      /border-t border-stone-100 dark:border-stone-800/,
    );
  }
});
