import { readFileSync } from "node:fs";
function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("mobile navigation fits the workspace below the desktop titlebar", () => {
  const sidebar = readSource("../../../panels/SessionSidebar.tsx");
  const heights = [...sidebar.matchAll(/height:\s*\n?\s*"(calc\([^"\n]+)"/g)];
  expect(heights).toHaveLength(2);
  for (const [, height] of heights) {
    expect(height).toContain("- var(--titlebar-inset, 0px)");
  }
});

test("app shell reserves native mobile status bar safe area", () => {
  const shell = readSource("../AppShell.tsx");
  const tokens = readSource("../../../../styles/tokens.css");

  // Android WebView 里 env() 恒为 0，须与原生注入的 --app-native-safe-area-* 取 max 合并
  expect(tokens).toMatch(
    /--app-safe-area-top:\s*max\(\s*env\(safe-area-inset-top, 0px\),\s*var\(--app-native-safe-area-top, 0px\)\s*\)/,
  );
  expect(tokens).toMatch(/--app-fullscreen-safe-area-top:\s*0px/);
  // 底部不预留安全区（产品决策：内容铺满到屏幕底边），只允许 0px
  expect(tokens).toMatch(/--app-safe-area-bottom:\s*0px/);
  expect(tokens).not.toMatch(/--app-safe-area-bottom:\s*max\(/);
  expect(tokens).toMatch(/--app-fullscreen-safe-area-bottom:\s*0px/);
  expect(tokens).toMatch(
    /@media \(max-width: 767px\) and \(display-mode: standalone\),\s*\(max-width: 767px\) and \(display-mode: fullscreen\)\s*\{[\s\S]*--app-fullscreen-safe-area-top:\s*12px/,
  );
  expect(tokens).not.toMatch(/--app-fullscreen-safe-area-bottom:\s*12px/);
  expect(shell).toMatch(/boxSizing:\s*"content-box"/);
  expect(shell).toMatch(/paddingTop:\s*appSafeAreaTop/);
  expect(shell).toMatch(/paddingBottom:\s*appSafeAreaBottom/);
  expect(shell).toMatch(
    /height:\s*`calc\(var\(--app-viewport-height, 100dvh\) - \$\{appSafeAreaTop\} - \$\{appSafeAreaBottom\} - var\(--titlebar-inset, 0px\)\)`/,
  );
});
