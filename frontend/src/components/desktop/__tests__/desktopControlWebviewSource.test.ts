import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const read = (path: string) =>
  readFileSync(
    new URL(`../../../../src-tauri/${path}`, import.meta.url),
    "utf8",
  );

test("the control WebView shares the configured main browser arguments", () => {
  const source = read("src/commands/desktop_control.rs");
  expect(source).toMatch(/\.find\(\|window\| window\.label == "main"\)/);
  expect(source).toMatch(
    /\.and_then\(\|window\| window\.additional_browser_args\.as_deref\(\)\)/,
  );
  expect(source).toMatch(/builder = builder\.additional_browser_args\(args\)/);
});

test("native control acceptance retains a main WebView to expose shared-process conflicts", () => {
  const source = read("examples/desktop_control_smoke.rs");
  expect(source).not.toMatch(/app\.windows\.clear\(\)/);
  expect(source).toContain('"about:blank"');
  expect(source).toContain('get_webview_window("main")');
});
