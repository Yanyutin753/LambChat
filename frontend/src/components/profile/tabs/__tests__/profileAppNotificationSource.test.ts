import { readFileSync } from "node:fs";
import { join } from "node:path";
const source = readFileSync(
  join(process.cwd(), "src/components/profile/tabs/ProfileNotificationTab.tsx"),
  "utf8",
);

test("profile notification settings expose the app-only notification service", () => {
  expect(source).toMatch(/appNotificationService/);
  expect(source).toMatch(/requestPermission/);
  expect(source).toMatch(/getRuntime/);
});
