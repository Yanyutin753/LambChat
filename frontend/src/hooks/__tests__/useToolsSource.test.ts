import { readFileSync } from "node:fs";
const useToolsSource = readFileSync(
  new URL("../useTools.ts", import.meta.url),
  "utf8",
);

test("does not fetch tools before an agent-specific refresh is requested", () => {
  expect(useToolsSource).not.toMatch(
    /\/\/ 初始加载\s*useEffect\(\(\) => \{\s*fetchTools\(\);\s*\}, \[fetchTools\]\);/,
  );
  expect(useToolsSource).toMatch(/refreshToolsForAgent = useCallback/);
});
