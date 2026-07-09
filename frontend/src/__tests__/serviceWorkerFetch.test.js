import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../sw.ts", import.meta.url), "utf8");

test("service worker keeps a local offline navigation fallback", () => {
  expect(source).toMatch(/const OFFLINE_URL = "\/offline\.html"/);
  expect(source).toMatch(/new NetworkFirst/);
  expect(source).toMatch(/getOfflineFallback/);
});

test("offline page offers retry and app return actions", () => {
  const offlineSource = readFileSync(
    new URL("../../public/offline.html", import.meta.url),
    "utf8",
  );

  expect(offlineSource).toMatch(/location\.reload\(\)/);
  expect(offlineSource).toMatch(/href="\/chat"/);
});

test("service worker preserves push notification routing", () => {
  expect(source).toMatch(/addEventListener\("push"/);
  expect(source).toMatch(/showNotification/);
  expect(source).toMatch(/addEventListener\("notificationclick"/);
  expect(source).toMatch(/openWindow/);
});
