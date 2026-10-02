import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("macOS positions native controls beside the centered 36px toolbar", () => {
  const config = JSON.parse(
    readFileSync(
      new URL(
        "../../../../../src-tauri/tauri.macos.conf.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  // Tao's y is a titlebar container inset, not the painted control center.
  // Keep the native position paired with the 36px toolbar height.
  expect(config.app.windows[0]).toMatchObject({
    decorations: true,
    titleBarStyle: "Overlay",
    hiddenTitle: true,
    trafficLightPosition: { x: 12, y: 21.5 },
  });
});

test("desktop frame reserves the platform titlebar height during loading", () => {
  const frame = readFileSync(
    new URL("../DesktopTitlebarFrame.tsx", import.meta.url),
    "utf8",
  );
  expect(frame).toContain('os === "mac" ? "36px" : "40px"');
  expect(frame).toContain('os === "mac" ? "h-9 shrink-0" : "h-10 shrink-0"');
});
