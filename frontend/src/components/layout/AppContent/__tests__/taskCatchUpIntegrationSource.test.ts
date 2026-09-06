import { readFileSync } from "node:fs";
import { join } from "node:path";

const notificationsSource = readFileSync(
  join(
    process.cwd(),
    "src/components/layout/AppContent/useWebSocketNotifications.tsx",
  ),
  "utf8",
);

const chatAppContentSource = readFileSync(
  join(process.cwd(), "src/components/layout/AppContent/ChatAppContent.tsx"),
  "utf8",
);

test("task notifications dedupe across websocket and catch-up delivery", () => {
  expect(notificationsSource).toMatch(/hasTaskNotified/);
  expect(notificationsSource).toMatch(/markTaskNotified/);
});

test("websocket notifications re-check finished tasks when the app resumes", () => {
  expect(notificationsSource).toMatch(/visibilitychange/);
  expect(notificationsSource).toMatch(/selectCatchUpCandidates/);
  expect(notificationsSource).toMatch(/document\.visibilityState === "hidden"/);
});

test("first chat submission prompts for native notification permission once", () => {
  expect(chatAppContentSource).toMatch(/promptAppNotificationPermissionOnce/);
  expect(chatAppContentSource).toMatch(
    /appNotificationService\.getRuntime\(\)/,
  );
});
