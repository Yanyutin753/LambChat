import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("chat header does not display a project badge", () => {
  expect(source).not.toContain("{project.name}");
});

test("header orders more, workspace, usage and avatar with responsive spacing", () => {
  const right = source.slice(source.indexOf("/* Right */"));
  expect(right).toContain(
    'className="chat-header__actions flex items-center gap-1 sm:gap-2 flex-shrink-0"',
  );
  expect(right.indexOf("<MoreHorizontal")).toBeLessThan(
    right.indexOf("{headerActions}"),
  );
  expect(right.indexOf("{headerActions}")).toBeLessThan(
    right.indexOf("<ComposerUsageChip"),
  );
  expect(right.indexOf("<ComposerUsageChip")).toBeLessThan(
    right.indexOf("<UserMenu"),
  );
});

test("header title can yield width to touch controls on narrow phones", () => {
  expect(source).toContain("chat-header__identity flex min-w-0");
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\.chat-header__identity > \.relative\s*\{[^}]*min-width:\s*0;/,
  );
  expect(css).toMatch(
    /\.tool-console-actions,\s*\.document-preview-toolbar-actions\s*\{[^}]*gap:\s*0;/,
  );
});

test("header menu exposes open state and restores focus on Escape", () => {
  expect(source).toContain("aria-expanded={!!menu}");
  expect(source).toContain("<ResourceCardMenu");
  expect(source).toContain("onClose={closeMenu}");
  expect(source).toContain("mobileMenuBtnRef.current?.focus();");
});

test("mobile sidebar and model triggers use compact 36px touch heights", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\.chat-header__identity > button,\s*\.chat-header__identity > \.relative > button\s*\{[^}]*min-height:\s*2\.25rem;/,
  );
  expect(css).toMatch(
    /\.chat-header__identity > button\s*\{[^}]*min-width:\s*2\.25rem;/,
  );
});

test("header controls share 32px height and square icon slots", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\.chat-header__actions > \.relative > button,\s*\[data-sidebar-brand\] button\s*\{[^}]*height:\s*2rem;[^}]*min-height:\s*2rem;/,
  );
  expect(css).toMatch(
    /\.chat-header__actions > \.relative > button,\s*\[data-sidebar-brand\] button\s*\{[^}]*width:\s*2rem;[^}]*min-width:\s*2rem;/,
  );
  expect(css).toMatch(
    /\.chat-header__actions > button:has\(\.composer-usage-amount\)\s*\{[^}]*width:\s*auto;/,
  );
});

test("narrow header action slots share compact 36px touch targets", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /@media \(max-width: 639px\)\s*\{\s*\.chat-header__actions > button,\s*\.chat-header__actions > \.relative > button,\s*\[data-sidebar-brand\] button\s*\{[^}]*width:\s*2\.25rem;[^}]*height:\s*2\.25rem;[^}]*min-width:\s*2\.25rem;[^}]*min-height:\s*2\.25rem;/,
  );
});

test("header icons and text share the same 16px content scale", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toContain("--header-content-size: 1rem");
  expect(css).toContain("width: var(--header-content-size)");
  expect(css).toContain("font-size: var(--header-content-size)");
  expect(css).not.toContain(".header-control-avatar");
  expect(css).toContain("[data-sidebar-brand] [data-wordmark-style]");
  expect(css).toMatch(
    /\.chat-header \.interactive-action-icon > div,\s*\[data-sidebar-brand\] \.interactive-action-icon > div\s*\{[^}]*width:\s*var\(--header-content-size\);[^}]*height:\s*var\(--header-content-size\);/,
  );
  const workspace = readFileSync(
    new URL(
      "../../../workspacePanel/SessionWorkspaceButton.tsx",
      import.meta.url,
    ),
    "utf8",
  );
  expect(workspace).not.toContain("<FolderOpen size={18}");
});
