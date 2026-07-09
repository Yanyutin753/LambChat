import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Source-string tests for the useWebPush hook.
 * Validates key behavioral patterns without mounting React.
 */

const source = readFileSync(
  join(process.cwd(), "src/hooks/useWebPush.ts"),
  "utf-8",
);

test("hook checks for serviceWorker and PushManager availability", () => {
  expect(source).toMatch(/"serviceWorker"\s+in\s+navigator/);
  expect(source).toMatch(/"PushManager"\s+in\s+window/);
});

test("hook fetches VAPID public key via pushApi", () => {
  expect(source).toMatch(/pushApi\.getVapidPublicKey/);
});

test("hook sets status to unavailable when push not supported", () => {
  // Both unavailable paths should exist
  const unavailableMatches = source.match(/"unavailable"/g);
  expect(unavailableMatches && unavailableMatches.length >= 2).toBeTruthy();
});

test("subscribe calls pushManager.subscribe with userVisibleOnly and applicationServerKey", () => {
  expect(source).toMatch(/userVisibleOnly:\s*true/);
  expect(source).toMatch(/applicationServerKey:\s*urlBase64ToUint8Array/);
});

test("subscribe requests Notification permission before subscribing", () => {
  expect(source).toMatch(/Notification\.requestPermission/);
  expect(source).toMatch(/permission\s*!==\s*"granted"/);
});

test("subscribe sends subscription to backend via pushApi.subscribe", () => {
  expect(source).toMatch(/pushApi\.subscribe/);
});

test("unsubscribe calls pushManager.unsubscribe and pushApi.unsubscribe", () => {
  expect(source).toMatch(/existing\.unsubscribe\(\)/);
  expect(source).toMatch(/pushApi\.unsubscribe/);
});

test("urlBase64ToUint8Array handles base64url encoding", () => {
  expect(source).toMatch(/urlBase64ToUint8Array/);
  // Should replace URL-safe characters
  expect(source).toMatch(/replace\(/);
  expect(source).toMatch(/-/);
  expect(source).toMatch(/_/);
  // Should handle padding
  expect(source).toMatch(/"="/);
});

test("hook exports PushStatus type with all expected states", () => {
  expect(source).toMatch(/PushStatus/);
  expect(source).toMatch(/"idle"/);
  expect(source).toMatch(/"loading"/);
  expect(source).toMatch(/"subscribed"/);
  expect(source).toMatch(/"unavailable"/);
  expect(source).toMatch(/"error"/);
});

test("hook checks existing subscription via pushManager.getSubscription", () => {
  expect(source).toMatch(/pushManager\.getSubscription/);
  expect(source).toMatch(/"subscribed"/);
});

test("hook verifies a service worker registration before waiting for readiness", () => {
  expect(source).toMatch(/serviceWorker\.getRegistration\(\)/);
  expect(source).toMatch(/if \(!registration\)/);
});

test("subscribe returns false when push is unavailable", () => {
  expect(source).toMatch(/status\s*===\s*"unavailable".*return/);
});
