import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(__dirname, "../SessionSidebar.tsx"),
  "utf8",
);

function mobileSidebarPanelClass() {
  return Array.from(
    source.matchAll(/className=\{`(?<className>[^`]*fixed left-0[\s\S]*?)`\}/g),
  )
    .map((match) => match.groups?.className ?? "")
    .find((className) => className.includes("bg-[var(--theme-bg-sidebar)]"));
}

function mobileSidebarPanelStyle() {
  const panelClass = mobileSidebarPanelClass();
  if (!panelClass) return undefined;
  const classStart = source.indexOf(`className={\`${panelClass}\`}`);
  return source.slice(classStart).match(/style=\{\{(?<style>[\s\S]*?)\}\}/)
    ?.groups?.style;
}

test("mobile sidebar overlay starts below the iOS safe-area top inset", () => {
  const overlayBlock = source.match(
    /className=\{`fixed left-0 right-0 z-\[60\][\s\S]*?style=\{\{(?<style>[\s\S]*?)\}\}/,
  )?.groups?.style;

  expect(overlayBlock).toBeTruthy();
  expect(overlayBlock).toMatch(
    /top:\s*"var\(--app-safe-area-top-active, var\(--app-safe-area-top, 0px\)\)"/,
  );
  expect(overlayBlock).toMatch(
    /height:\s*"calc\(var\(--app-viewport-height, 100dvh\) - var\(--app-safe-area-top-active, var\(--app-safe-area-top, 0px\)\) - var\(--app-safe-area-bottom-active, var\(--app-safe-area-bottom, 0px\)\)\)"/,
  );
});

test("mobile sidebar panel starts below the iOS safe-area top inset", () => {
  const panelBlock = mobileSidebarPanelStyle();

  expect(panelBlock).toBeTruthy();
  expect(panelBlock).toMatch(
    /top:\s*"var\(--app-safe-area-top-active, var\(--app-safe-area-top, 0px\)\)"/,
  );
  expect(panelBlock).toMatch(
    /height:\s*"calc\(var\(--app-viewport-height, 100dvh\) - var\(--app-safe-area-top-active, var\(--app-safe-area-top, 0px\)\) - var\(--app-safe-area-bottom-active, var\(--app-safe-area-bottom, 0px\)\)\)"/,
  );
  expect(panelBlock).not.toMatch(/paddingTop:\s*"env\(safe-area-inset-top\)"/);
});

test("mobile sidebar panel uses a fixed drawer width", () => {
  const panelClass = mobileSidebarPanelClass();

  expect(panelClass).toBeTruthy();
  expect(panelClass).toMatch(/\bw-64\b/);
  expect(panelClass).toMatch(/\brounded-r-lg\b/);
});
