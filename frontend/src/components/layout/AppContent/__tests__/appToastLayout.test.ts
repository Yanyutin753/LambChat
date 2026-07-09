import { getAppToastSidebarOffset } from "../appToastLayout.ts";

test("uses the rail width as the toast sidebar offset when the sidebar is collapsed", () => {
  expect(getAppToastSidebarOffset({ sidebarCollapsed: true })).toBe(
    "var(--sidebar-rail-width)",
  );
});

test("uses the full sidebar width as the toast sidebar offset when the sidebar is expanded", () => {
  expect(getAppToastSidebarOffset({ sidebarCollapsed: false })).toBe(
    "var(--sidebar-width)",
  );
});
