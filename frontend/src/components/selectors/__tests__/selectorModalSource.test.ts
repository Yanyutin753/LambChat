import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

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
  assert.match(modalSource, /export function SelectorModalPortal\(/);
  assert.match(
    modalSource,
    /className="fixed inset-0 z-\[300\] bg-black\/50 animate-fade-in"/,
  );
  assert.match(
    modalSource,
    /className="safe-area-viewport-padding fixed z-\[301\] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in"/,
  );

  for (const relativePath of consumers) {
    const source = readSource(relativePath);

    assert.match(
      source,
      /SelectorModalPortal/,
      `${relativePath} should import SelectorModalPortal from shared selector infrastructure`,
    );
    assert.match(
      source,
      /<SelectorModalPortal/,
      `${relativePath} should render selector modals through the shared portal`,
    );
    assert.doesNotMatch(
      source,
      /fixed inset-0 z-\[300\] bg-black\/50 animate-fade-in/,
      `${relativePath} should not duplicate the modal overlay classes`,
    );
    assert.doesNotMatch(
      source,
      /safe-area-viewport-padding fixed z-\[301\] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in/,
      `${relativePath} should not duplicate the modal viewport wrapper classes`,
    );
  }
});

test("selector modals share the content shell without changing its classes", () => {
  assert.match(shellSource, /export const SELECTOR_MODAL_SHELL_CLASS/);
  assert.match(sharedIndexSource, /export \{ SelectorModalShell \}/);
  assert.match(shellSource, /sm:rounded-\[28px\] rounded-t-\[28px\]/);
  assert.match(shellSource, /sm:w-\[min\(760px,calc\(100vw-2rem\)\)\]/);
  assert.match(
    shellSource,
    /border border-white\/70 dark:border-stone-700\/80/,
  );
  assert.match(shellSource, /background: "var\(--theme-bg-card\)"/);
  assert.match(
    shellSource,
    /onClick=\{\(event\) => event\.stopPropagation\(\)\}/,
  );

  for (const relativePath of consumers) {
    const source = readSource(relativePath);
    assert.match(
      source,
      /SelectorModalShell/,
      `${relativePath} should import SelectorModalShell from shared selector infrastructure`,
    );
    assert.match(
      source,
      /<SelectorModalShell/,
      `${relativePath} should render the shared selector content shell`,
    );
  }
});

test("selector modals share the header and action bar styles", () => {
  assert.match(headerSource, /export function SelectorModalHeader/);
  assert.match(
    headerSource,
    /flex items-center justify-between gap-4 px-4 sm:px-6 py-4 sm:py-5 border-b/,
  );
  assert.match(
    headerSource,
    /absolute left-1\/2 -translate-x-1\/2 top-2 w-10 h-1 rounded-full bg-stone-300\/80 dark:bg-stone-600 sm:hidden/,
  );
  assert.match(
    headerSource,
    /p-2 rounded-full border border-stone-200\/80 bg-white\/80 text-stone-500 shadow-sm/,
  );

  assert.match(actionBarSource, /export function SelectorActionBar/);
  assert.match(
    actionBarSource,
    /sticky top-0 z-10 flex items-center gap-2 px-4 sm:px-6 py-2\.5 border-b/,
  );
  assert.match(
    actionBarSource,
    /rounded-full border border-transparent px-3 py-2 sm:py-1\.5 text-xs font-semibold/,
  );
});

test("selector modals do not render redundant done footers", () => {
  for (const relativePath of consumers) {
    const source = readSource(relativePath);
    assert.doesNotMatch(
      source,
      /safe-area-bottom \[--safe-area-bottom-extra:0\.75rem\]/,
      `${relativePath} should close through the header or backdrop instead of a footer Done button`,
    );
  }
});
