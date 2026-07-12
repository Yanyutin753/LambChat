import { readFileSync } from "node:fs";
import { join } from "node:path";
const source = readFileSync(
  join(process.cwd(), "src/components/layout/AppContent/AppShell.tsx"),
  "utf8",
);

test("app shell no longer mounts a separate notification banner (announcements handled via header)", () => {
  expect(source).not.toMatch(/NotificationBanner/);
});
