import { existsSync, readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const componentSource = readSource("../McpSelectorEmptyState.tsx");
const consumers = ["../EnvKeysSelector.tsx", "../RoleSelector.tsx"];

test("mcp selector dropdown empty states share one presentation component", () => {
  expect(componentSource).toMatch(/export function McpSelectorEmptyState\(/);
  expect(componentSource).toMatch(
    /className="py-3 text-center text-xs text-stone-400 dark:text-stone-500"/,
  );

  for (const relativePath of consumers) {
    const source = readSource(relativePath);
    expect(source).toMatch(
      /import \{ McpSelectorEmptyState \} from "\.\/McpSelectorEmptyState"/,
    );
    expect(source).toMatch(/<McpSelectorEmptyState>/);
    expect(source).not.toMatch(
      /py-3 text-center text-xs text-stone-400 dark:text-stone-500/,
    );
  }
});
