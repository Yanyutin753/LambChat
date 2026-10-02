import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";
test("web chat loads the shared workspace styles without requiring native chrome", () => {
  const root = resolve(import.meta.dirname, "../..");
  const shell = readFileSync(
    resolve(root, "components/layout/AppContent/AppShell.tsx"),
    "utf8",
  );
  const css = readFileSync(resolve(root, "styles/desktop.css"), "utf8");
  expect(shell).toContain('import "../../../styles/desktop.css"');
  expect(shell).toContain('data-workspace-ui={activeTab === "chat"');
  expect(css).toContain(":has([data-titlebar], [data-workspace-ui])");
});

test("docked panels reserve native titlebar space and keep even outer insets", () => {
  const css = readFileSync(
    resolve(import.meta.dirname, "../desktop.css"),
    "utf8",
  );
  expect(css).toContain("top: var(--titlebar-inset, 0px)");
  expect(css).toContain(
    "height: calc(100% - var(--titlebar-inset, 0px) - 1rem)",
  );
  expect(css).toContain("margin: 0.5rem");
});

test("assistant heading preserves serif typography and a stable centered line box", () => {
  const root = resolve(import.meta.dirname, "../..");
  const css = readFileSync(resolve(root, "styles/desktop.css"), "utf8");
  const headingRule =
    css.match(/\.chat-assistant-heading\s+\.font-serif\s*\{([^}]+)\}/)?.[1] ??
    "";
  expect(headingRule).not.toContain("font-family:");
  const message = readFileSync(
    resolve(root, "components/chat/ChatMessage/index.tsx"),
    "utf8",
  );
  expect(message).toMatch(
    /className="min-w-0 truncate[^"\n]*leading-none[^"\n]*font-serif"/,
  );
});

test("compact serif icon labels share an optical alignment correction", () => {
  const css = readFileSync(resolve(import.meta.dirname, "../desktop.css"), "utf8");
  expect(css).toMatch(
    /\.chat-input-toolbar\s+\.font-serif,\s*\.chat-assistant-heading\s+\.font-serif\s*\{[^}]*position: relative;[^}]*top: 1px;/,
  );
});

test("native titlebar spans the docked panel lane", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
  expect(css).toContain(
    "width: calc(100% + var(--right-panel-active-width, 0px))",
  );
});
