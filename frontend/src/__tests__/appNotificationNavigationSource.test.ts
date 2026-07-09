import { readFileSync } from "node:fs";
import { join } from "node:path";
const appSource = readFileSync(join(process.cwd(), "src/App.tsx"), "utf8");
const serviceSource = readFileSync(
  join(process.cwd(), "src/services/notifications/appNotificationService.ts"),
  "utf8",
);

test("App registers native notification route navigation inside the router", () => {
  expect(appSource).toMatch(/appNotificationService\.setNavigator/);
  expect(appSource).toMatch(/initializeNativeClickHandlers/);
});

test("app notification service handles Capacitor local notification clicks", () => {
  expect(serviceSource).toMatch(/localNotificationActionPerformed/);
  expect(serviceSource).toMatch(/payload\.notification\.extra\?\.route/);
});
