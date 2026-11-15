import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("immediate Android notifications do not request exact-alarm access", () => {
  const source = readFileSync(new URL("../appNotificationService.ts", import.meta.url), "utf8");
  const adapter = source.slice(source.indexOf("function createCapacitorAndroidAdapter"));
  expect(adapter).toMatch(/LocalNotifications\.schedule\([\s\S]*isExactNotification:\s*false/);
});
