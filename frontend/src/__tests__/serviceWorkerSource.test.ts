import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(import.meta.dirname, "../sw.ts"), "utf8");

test("service worker uses Workbox precaching with an injected Vite manifest", () => {
  expect(source).toMatch(/precacheAndRoute\(self\.__WB_MANIFEST\)/);
  expect(source).toMatch(/cleanupOutdatedCaches\(\)/);
});

test("service worker keeps dynamic LambChat backends out of runtime caches", () => {
  expect(source).toMatch(/getPwaRequestKind/);
  expect(source).not.toMatch(/registerRoute\([^]*\/api/);
  expect(source).not.toMatch(/registerRoute\([^]*text\/event-stream/);
});
