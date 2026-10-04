import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("macOS lets measured native alignment own the overlay controls", () => {
  const config = JSON.parse(
    readFileSync(
      new URL(
        "../../../../../src-tauri/tauri.macos.conf.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  expect(config.app.windows[0]).toMatchObject({
    decorations: true,
    titleBarStyle: "Overlay",
    hiddenTitle: true,
  });
  // Tao/Wry would reposition the container on resize and overwrite our centering.
  expect(config.app.windows[0]).not.toHaveProperty("trafficLightPosition");
});

test("desktop frame reserves the platform titlebar height during loading", () => {
  const frame = readFileSync(
    new URL("../DesktopTitlebarFrame.tsx", import.meta.url),
    "utf8",
  );
  expect(frame).toContain('os === "mac" ? "36px" : "40px"');
  expect(frame).toContain('os === "mac" ? "h-9 shrink-0" : "h-10 shrink-0"');
  const native = readFileSync(
    new URL("../../../../../src-tauri/src/titlebar.rs", import.meta.url),
    "utf8",
  );
  expect(native).toContain("const TITLEBAR_HEIGHT: f64 = 36.0;");
});
