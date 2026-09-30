/** @vitest-environment jsdom */
import { render, cleanup } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { SidebarSkeleton } from "../SidebarSkeleton";
import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "../../../hooks/useAuth";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

for (const collapsed of [false, true]) {
  test(`keeps the activity rail while the chat sidebar is ${
    collapsed ? "collapsed" : "expanded"
  }`, () => {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(collapsed));
    const { container } = render(<SidebarSkeleton />);
    const rail = container.querySelector("[data-desktop-activity-rail]");
    expect(rail).not.toBeNull();
    expect(rail?.querySelectorAll("[data-rail-icon]")).toHaveLength(8);
    expect(Boolean(container.querySelector("[data-desktop-sidebar]"))).toBe(
      !collapsed,
    );
    expect(container.firstElementChild?.className).toContain("hidden sm:flex");
  });
}
