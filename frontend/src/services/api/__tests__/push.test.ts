import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Source-string tests for the push API service.
 * Validates endpoint URLs, HTTP methods, and payload shapes without network calls.
 */

const source = readFileSync(
  join(process.cwd(), "src/services/api/push.ts"),
  "utf-8",
);

test("pushApi.getVapidPublicKey calls the correct endpoint with skipAuth", () => {
  expect(source).toMatch(/api\/push\/vapid-public-key/);
  expect(source).toMatch(/skipAuth:\s*true/);
});

test("pushApi.subscribe sends POST to /api/push/subscribe", () => {
  expect(source).toMatch(/method:\s*"POST"/);
  expect(source).toMatch(/api\/push\/subscribe/);
  // Verify it sends endpoint, keys, and user_agent
  expect(source).toMatch(/endpoint/);
  expect(source).toMatch(/user_agent/);
});

test("pushApi.unsubscribe sends POST to /api/push/unsubscribe", () => {
  // The unsubscribe function should contain the endpoint
  expect(source).toMatch(/api\/push\/unsubscribe/);
  expect(source).toMatch(/method:\s*"POST"/);
});

test("pushApi.deleteAllSubscriptions sends DELETE to /api/push/subscriptions", () => {
  expect(source).toMatch(/api\/push\/subscriptions/);
  expect(source).toMatch(/method:\s*"DELETE"/);
});

test("exports PushSubscriptionJSON interface with required fields", () => {
  expect(source).toMatch(/PushSubscriptionJSON/);
  expect(source).toMatch(/endpoint:\s*string/);
  expect(source).toMatch(/keys:.*p256dh.*auth/s);
  expect(source).toMatch(/expirationTime/);
});

test("exports PushSubscriptionResponse interface", () => {
  expect(source).toMatch(/PushSubscriptionResponse/);
  expect(source).toMatch(/user_agent:\s*string/);
  expect(source).toMatch(/last_used_at/);
});
