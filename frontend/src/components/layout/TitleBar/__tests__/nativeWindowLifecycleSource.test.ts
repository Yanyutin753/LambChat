import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("Dock reopen uses the same window restoration path as the tray", () => {
  const source = readFileSync(
    new URL("../../../../../src-tauri/src/lib.rs", import.meta.url),
    "utf8",
  );
  // RunEvent::Reopen is non-exhaustive: it cannot be constructed outside Tauri.
  expect(source).toMatch(/RunEvent::Reopen\s*\{\s*\.\.\s*\}\s*=>\s*true/);
  expect(source).toMatch(
    /if should_restore_main_window\(&event\)\s*\{\s*tray::show_main_window\(app_handle\)/,
  );
});
