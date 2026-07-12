import { readFileSync } from "node:fs";
import { join } from "node:path";

const baseCss = readFileSync(join(import.meta.dirname, "../base.css"), "utf8");

test("sidebar preview reserved canvas inherits the active theme background", () => {
  expect(baseCss).toMatch(
    /html\[data-sidebar-preview="open"\],\s*html\[data-sidebar-preview="open"\] body\s*\{[\s\S]*?background:\s*var\(--theme-bg\);/,
  );
  expect(baseCss).toMatch(
    /html\[data-sidebar-preview="open"\] body::before\s*\{[\s\S]*?width:\s*var\(--sidebar-preview-width, 60%\);[\s\S]*?background:\s*var\(--theme-bg\);[\s\S]*?z-index:\s*199;/,
  );
});

test("public scrolling pages avoid reserved scrollbar gutters beside sidebar previews", () => {
  expect(baseCss).toMatch(
    /html\.allow-scroll,\s*html\.allow-scroll body,\s*html\.allow-scroll #root\s*\{[\s\S]*?overflow-y:\s*auto;[\s\S]*?scrollbar-gutter:\s*auto;/,
  );
  expect(baseCss).not.toMatch(
    /html\.allow-scroll,\s*html\.allow-scroll body,\s*html\.allow-scroll #root\s*\{[\s\S]*?overflow-y:\s*scroll;/,
  );
  expect(baseCss).toMatch(
    /html\.allow-scroll\[data-sidebar-preview="open"\],\s*html\.allow-scroll\[data-sidebar-preview="open"\] body,\s*html\.allow-scroll\[data-sidebar-preview="open"\] #root\s*\{[\s\S]*?scrollbar-width:\s*none;/,
  );
  expect(baseCss).toMatch(
    /html\.allow-scroll\[data-sidebar-preview="open"\]::-webkit-scrollbar,[\s\S]*?display:\s*none;/,
  );
});
