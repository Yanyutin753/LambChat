import { readFileSync } from "node:fs";
import { join } from "node:path";

const baseCss = readFileSync(join(import.meta.dirname, "../base.css"), "utf8");

test("the active docked right-panel canvas inherits the active theme background", () => {
  expect(baseCss).toMatch(
    /html\[data-right-panel-presentation="docked"\],\s*html\[data-right-panel-presentation="docked"\] body\s*\{[\s\S]*?background:\s*var\(--theme-bg\);/,
  );
  expect(baseCss).toMatch(
    /html\[data-right-panel-presentation="docked"\] body::before\s*\{[\s\S]*?width:\s*var\(--right-panel-active-width, 0px\);[\s\S]*?background:\s*var\(--theme-bg\);[\s\S]*?z-index:\s*199;/,
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
    /html\.allow-scroll\[data-right-panel-presentation="docked"\],\s*html\.allow-scroll\[data-right-panel-presentation="docked"\] body,\s*html\.allow-scroll\[data-right-panel-presentation="docked"\] #root\s*\{[\s\S]*?scrollbar-width:\s*none;/,
  );
  expect(baseCss).toMatch(
    /html\.allow-scroll\[data-right-panel-presentation="docked"\]::-webkit-scrollbar,[\s\S]*?display:\s*none;/,
  );
});
