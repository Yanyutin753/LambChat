import { afterEach, expect, test, vi } from "vitest";
import { isAndroidLocalDevice } from "../localDevice";

afterEach(() => vi.unstubAllGlobals());

test("only an Android app with the local device bridge may pair", () => {
  for (const [platform, available, expected] of [
    ["android", true, true],
    ["android", false, false],
    ["ios", true, false],
    ["web", true, false],
  ] as const) {
    vi.stubGlobal("Capacitor", {
      isNativePlatform: () => platform !== "web",
      getPlatform: () => platform,
      isPluginAvailable: () => available,
    });
    expect(isAndroidLocalDevice()).toBe(expected);
  }
});
