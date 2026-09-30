import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("macOS positions native controls beside the centered 40px toolbar", () => {
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
    trafficLightPosition: { x: 16, y: 18 },
  });
});

test("desktop frame reserves the platform titlebar height during loading", () => {
  const frame = readFileSync(
    new URL("../DesktopTitlebarFrame.tsx", import.meta.url),
    "utf8",
  );
  expect(frame).toContain('"40px"');
  expect(frame).toContain('className="h-10 shrink-0"');
});
