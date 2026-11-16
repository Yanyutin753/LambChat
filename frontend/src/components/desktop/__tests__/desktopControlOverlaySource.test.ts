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

test("fullscreen overlays use native backdrop effects without blurring the toolbar", () => {
  const overlay = native.slice(
    native.indexOf("fn show_overlays("),
    native.indexOf("fn hide_surfaces("),
  );
  expect(overlay).toContain("Effect::Blur");
  expect(overlay).not.toContain("Effect::Acrylic");
  expect(overlay).toContain("Effect::HudWindow");
  expect(overlay).toContain(".effects(");
  const toolbar = native.slice(
    native.indexOf("fn show(app:"),
    native.indexOf("fn show_overlays("),
  );
  expect(toolbar).not.toContain(".effects(");
});

test("overlay is realized before Linux cursor passthrough accesses its native window", () => {
  const show = native.slice(
    native.indexOf("fn show_overlays("),
    native.indexOf("fn hide_surfaces("),
  );
  expect(show.indexOf("window.show()")).toBeGreaterThanOrEqual(0);
  expect(show.indexOf("window.show()")).toBeLessThan(
    show.indexOf(".set_ignore_cursor_events(true)"),
  );
});

test("the single takeover toolbar starts inside the top work area", () => {
  const position = native.slice(
    native.indexOf("fn takeover_position("),
    native.indexOf("fn show(app:"),
  );
  expect(position.replace(/\s+/g, "")).toContain(
    "margin.max(0).min(area.size.height.saturating_sub(size.height)asi32)",
  );
});
