import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("sidebar brand header exposes notifications with a count and opens the existing dialog", () => {
  const source = read("../SessionListContent.tsx");
  const header = source.slice(
    source.indexOf("data-sidebar-brand"),
    source.indexOf("{/* 桌面壳仅保留"),
  );
  expect(header).toContain('t("nav.notifications")');
  expect(header).toContain("<Bell size={16}");
  expect(header).toContain("notificationCount > 0");
  expect(header).toContain(
    'notificationCount > 99 ? "99+" : notificationCount',
  );
  expect(header).toMatch(
    /onCollapse\(\);[\s\S]*new Event\(OPEN_NOTIFICATIONS_EVENT\)/,
  );
  const owner = read("../../SessionSidebar.tsx");
  expect(owner).toContain("addEventListener(NOTIFICATION_COUNT_EVENT");
  expect(owner).toContain("removeEventListener(NOTIFICATION_COUNT_EVENT");
  expect(owner).toContain("      notificationCount,");
});

test("sidebar navigation glyphs share the header's 16px size", () => {
  for (const file of ["../SessionListContent.tsx", "../SidebarRail.tsx"]) {
    const source = read(file);
    expect(source).not.toContain("size={20}");
    expect(source).not.toContain("compactChrome ? 19 : 20");
    for (const icon of [
      "SquarePen",
      "Search",
      "CalendarClock",
      "FolderOpen",
      "MoreIcon",
    ]) {
      expect(source).toContain(`<${icon} size={16}`);
    }
  }
});

test("sidebar loads its badge count even when the initial header event was missed", () => {
  const source = read("../../SessionSidebar.tsx");
  expect(source).toContain("notificationApi.getActive().then");
  expect(source).toContain(
    "if (initialCountPending) setNotificationCount(items.length)",
  );
  expect(source).toContain("initialCountPending = false");
});
