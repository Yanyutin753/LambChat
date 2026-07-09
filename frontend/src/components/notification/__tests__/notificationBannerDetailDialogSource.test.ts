import { readFileSync } from "node:fs";
import { join } from "node:path";
const source = readFileSync(
  join(process.cwd(), "src/components/notification/NotificationBanner.tsx"),
  "utf8",
);

test("notification banner opens a detail dialog from the compact card", () => {
  expect(source).toMatch(/selectedNotification/);
  expect(source).toMatch(/setSelectedNotification\(current\)/);
  expect(source).toMatch(/createPortal/);
  expect(source).toMatch(/role="dialog"/);
  expect(source).toMatch(/aria-modal="true"/);
  expect(source).toMatch(/notification-banner-detail/);
});
