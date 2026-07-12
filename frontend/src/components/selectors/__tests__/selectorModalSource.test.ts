import { existsSync, readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const modalSource = readSource("../shared/SelectorModal.tsx");
const shellSource = readSource("../shared/SelectorModalShell.tsx");
const headerSource = readSource("../shared/SelectorModalHeader.tsx");
const actionBarSource = readSource("../shared/SelectorActionBar.tsx");
const sharedIndexSource = readSource("../shared/index.ts");
const consumers = [
  "../AgentModeSelector.tsx",
  "../SkillSelector.tsx",
  "../ToolSelector.tsx",
];

test("selector modals share the portal overlay and viewport wrapper", () => {
  expect(modalSource).toMatch(/export function SelectorModalPortal\(/);
  expect(modalSource).toMatch(
    /className="fixed inset-0 z-\[300\] bg-black\/50 animate-fade-in"/,
  );
  expect(modalSource).toMatch(
    /className="safe-area-viewport-padding fixed z-\[301\] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in"/,
  );

  for (const relativePath of consumers) {
    const source = readSource(relativePath);

    expect(source).toMatch(/SelectorModalPortal/);
    expect(source).toMatch(/<SelectorModalPortal/);
    expect(source).not.toMatch(
      /fixed inset-0 z-\[300\] bg-black\/50 animate-fade-in/,
    );
    expect(source).not.toMatch(
      /safe-area-viewport-padding fixed z-\[301\] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in/,
    );
  }
});

test("selector modals share the content shell without changing its classes", () => {
  expect(shellSource).toMatch(/export const SELECTOR_MODAL_SHELL_CLASS/);
  expect(sharedIndexSource).toMatch(/export \{ SelectorModalShell \}/);
  expect(shellSource).toMatch(/sm:rounded-\[28px\] rounded-t-\[28px\]/);
  expect(shellSource).toMatch(/sm:w-\[min\(760px,calc\(100vw-2rem\)\)\]/);
  expect(shellSource).toMatch(
    /border border-white\/70 dark:border-stone-700\/80/,
  );
  expect(shellSource).toMatch(/background: "var\(--theme-bg-card\)"/);
  expect(shellSource).toMatch(
    /onClick=\{\(event\) => event\.stopPropagation\(\)\}/,
  );

  for (const relativePath of consumers) {
    const source = readSource(relativePath);
    expect(source).toMatch(/SelectorModalShell/);
    expect(source).toMatch(/<SelectorModalShell/);
  }
});

test("selector modals share the header and action bar styles", () => {
  expect(headerSource).toMatch(/export function SelectorModalHeader/);
  expect(headerSource).toMatch(
    /flex items-center justify-between gap-4 px-4 sm:px-6 py-4 sm:py-5 border-b/,
  );
  expect(headerSource).toMatch(
    /absolute left-1\/2 -translate-x-1\/2 top-2 w-10 h-1 rounded-full bg-stone-300\/80 dark:bg-stone-600 sm:hidden/,
  );
  expect(headerSource).toMatch(
    /p-2 rounded-full border border-stone-200\/80 bg-white\/80 text-stone-500 shadow-sm/,
  );

  expect(actionBarSource).toMatch(/export function SelectorActionBar/);
  expect(actionBarSource).toMatch(
    /sticky top-0 z-10 flex items-center gap-2 px-4 sm:px-6 py-2\.5 border-b/,
  );
  expect(actionBarSource).toMatch(
    /rounded-full border border-transparent px-3 py-2 sm:py-1\.5 text-xs font-semibold/,
  );
});

test("selector modals do not render redundant done footers", () => {
  for (const relativePath of consumers) {
    const source = readSource(relativePath);
    expect(source).not.toMatch(
      /safe-area-bottom \[--safe-area-bottom-extra:0\.75rem\]/,
    );
  }
});
