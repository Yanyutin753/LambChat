import { readFileSync } from "node:fs";
function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("app shell reserves native mobile status bar safe area", () => {
  const shell = readSource("../AppShell.tsx");
  const tokens = readSource("../../../../styles/tokens.css");

  expect(tokens).toMatch(
    /--app-safe-area-top:\s*env\(safe-area-inset-top, 0px\)/,
  );
  expect(tokens).toMatch(/--app-fullscreen-safe-area-top:\s*0px/);
  expect(tokens).toMatch(/--app-fullscreen-safe-area-bottom:\s*0px/);
  expect(tokens).toMatch(
    /@media \(display-mode: standalone\), \(display-mode: fullscreen\)\s*\{[\s\S]*--app-fullscreen-safe-area-top:\s*12px/,
  );
  expect(tokens).toMatch(
    /@media \(display-mode: standalone\), \(display-mode: fullscreen\)\s*\{[\s\S]*--app-fullscreen-safe-area-bottom:\s*12px/,
  );
  expect(shell).toMatch(/boxSizing:\s*"content-box"/);
  expect(shell).toMatch(/paddingTop:\s*appSafeAreaTop/);
  expect(shell).toMatch(/paddingBottom:\s*appSafeAreaBottom/);
  expect(shell).toMatch(
    /height:\s*`calc\(var\(--app-viewport-height, 100dvh\) - \$\{appSafeAreaTop\} - \$\{appSafeAreaBottom\}\)`/,
  );
});
