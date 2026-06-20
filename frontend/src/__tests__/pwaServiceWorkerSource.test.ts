import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const swSource = readFileSync(resolve(import.meta.dirname, "../sw.ts"), "utf8");

test("service worker activates fresh deployments without serving a stale app shell", () => {
  assert.match(swSource, /addEventListener\("install"/);
  assert.match(swSource, /self\.skipWaiting\(\)/);
  assert.match(swSource, /addEventListener\("activate"/);
  assert.match(swSource, /clients\.claim\(\)/);
  assert.match(swSource, /client\.navigate\(client\.url\)/);
  assert.doesNotMatch(swSource, /new NetworkFirst/);
  assert.doesNotMatch(swSource, /lambchat-app-shell-v2";/);
});
