import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

const native = readFileSync(
  resolve(
    import.meta.dirname,
    "../../../../src-tauri/src/commands/desktop_control.rs",
  ),
  "utf8",
);

test("display-wide indicators never intercept input and every surface acknowledges readiness", () => {
  expect(native).toContain("available_monitors()");
  expect(native).toContain("set_ignore_cursor_events(true)");
  expect(native).toContain(".transparent(true)");
  expect(native).toContain("overlay_ready");
});

test("terminal execution removes control surfaces without granting resume to overlays", () => {
  expect(native).toContain('Some("ended")');
  expect(native).toContain("hide_surfaces");
  expect(native).toContain("check(&window)?");
});

test("daemon cleanup failure reaches the unavailable control state", () => {
  expect(native).toMatch(/Some\("unavailable"\)\s*=>/);
});
