import { readFileSync } from "node:fs";
import { join } from "node:path";
const source = readFileSync(
  join(process.cwd(), "src/components/notification/NotificationBanner.tsx"),
  "utf8",
);
const helperSource = readFileSync(
  join(
    process.cwd(),
    "src/services/notifications/announcementNotifications.ts",
  ),
  "utf8",
);

test("notification banner surfaces active announcements through app-only notifications", () => {
  expect(source).toMatch(/surfaceAppAnnouncementNotifications/);
  expect(helperSource).toMatch(/appNotificationService/);
  expect(helperSource).toMatch(/announcement/);
  expect(helperSource).toMatch(
    /dedupeKey: `announcement:\$\{notification\.id\}`/,
  );
});
