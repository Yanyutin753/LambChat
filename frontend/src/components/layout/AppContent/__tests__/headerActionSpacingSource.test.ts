import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("header puts more before workspace and avatar with a consistent gap", () => {
  const right = source.slice(source.indexOf("{/* Right */}"));
  expect(right).toContain('className="chat-header__actions flex items-center gap-0 sm:gap-1 flex-shrink-0"');
  expect(right.indexOf("<MoreHorizontal")).toBeLessThan(right.indexOf("{headerActions}"));
  expect(right.indexOf("{headerActions}")).toBeLessThan(right.indexOf("<UserMenu"));
});

test("header title can yield width to touch controls on narrow phones", () => {
  expect(source).toContain('chat-header__identity flex min-w-0');
  const css = readFileSync(new URL("../../../../styles/components.css", import.meta.url), "utf8");
  expect(css).toMatch(/\.chat-header__identity > \.relative\s*\{[^}]*min-width:\s*0;/);
  expect(css).toMatch(/\.tool-console-actions,\s*\.document-preview-toolbar-actions\s*\{[^}]*gap:\s*0;/);
});

test("header menu exposes open state and restores focus on Escape", () => {
  expect(source).toContain('aria-expanded={mobileMenuOpen || langMenuOpen}');
  expect(source).toContain('if (e.key !== "Escape") return;');
  expect(source).toContain('mobileMenuBtnRef.current?.focus();');
});
