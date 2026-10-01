import { readFileSync } from "node:fs";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("keyboard viewport tracking covers public routes as well as authenticated chat", () => {
  expect(read("../../App.tsx")).toMatch(/useAppViewport\(\)/);
  expect(read("../../components/layout/AppContent/AppShell.tsx")).not.toMatch(
    /const updateViewportHeight/,
  );
});

test("portal dialogs and mobile editors fit above the keyboard", () => {
  const css = read("../utilities.css");
  expect(css).toMatch(
    /html\[data-mobile-keyboard="true"\][\s\S]*\.safe-area-viewport-padding-top/,
  );
  expect(css).toMatch(/max-height:\s*var\(--app-viewport-height/);
  expect(css).toMatch(/bottom:\s*var\(--app-keyboard-inset/);
  expect(css).toMatch(/\.editor-sidebar--mobile/);
});
