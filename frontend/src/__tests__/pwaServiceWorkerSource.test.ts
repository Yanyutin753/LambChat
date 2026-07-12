import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const swSource = readFileSync(resolve(import.meta.dirname, "../sw.ts"), "utf8");

test("service worker activates fresh deployments without serving a stale app shell", () => {
  expect(swSource).toMatch(/addEventListener\("install"/);
  expect(swSource).toMatch(/self\.skipWaiting\(\)/);
  expect(swSource).toMatch(/addEventListener\("activate"/);
  expect(swSource).toMatch(/clients\.claim\(\)/);
  expect(swSource).toMatch(/client\.navigate\(client\.url\)/);
  expect(swSource).not.toMatch(/new NetworkFirst/);
  expect(swSource).not.toMatch(/lambchat-app-shell-v2";/);
});
