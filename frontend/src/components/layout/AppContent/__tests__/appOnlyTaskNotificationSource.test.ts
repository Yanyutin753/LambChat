import { readFileSync } from "node:fs";
import { join } from "node:path";
const source = readFileSync(
  join(
    process.cwd(),
    "src/components/layout/AppContent/useWebSocketNotifications.tsx",
  ),
  "utf8",
);

test("task notifications skip browser notification delivery in native app runtimes", () => {
  expect(source).toMatch(
    /const isAppNotificationRuntime =\s+appNotificationRuntime !== "unsupported";/,
  );
  expect(source).toMatch(/!isAppNotificationRuntime/);
  expect(source).toMatch(/appNotificationService\.notify/);
});

test("task notifications attempt app delivery before suppressing active-session surfaces", () => {
  expect(source).toMatch(/shouldAttemptAppTaskNotification/);
  expect(source).toMatch(/const shouldAttemptAppNotification/);
  expect(source).toMatch(
    /if \(!shouldSurface && !shouldAttemptAppNotification\)/,
  );
});

test("task notifications do not show stale toasts while the page is hidden", () => {
  expect(source).toMatch(/if \(visibilityState !== "visible"\) \{/);
  expect(source).toMatch(/const toastDuration = notificationCopy\.isSuccess/);
});
