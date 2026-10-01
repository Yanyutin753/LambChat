/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { DesktopSidebarShell } from "../DesktopSidebarShell";

vi.mock("../../../workspacePanel/WorkspacePanel", () => ({
  WorkspacePanel: () => null,
}));
afterEach(() => {
  cleanup();
  localStorage.clear();
});

test("sidebar resize keeps cursor feedback until capture ends and fits a narrowed window", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  localStorage.setItem("lambchat_desktop_sidebar_width", "480");
  const { container } = render(
    <MemoryRouter>
      <DesktopSidebarShell collapsed={false} onToggleCollapsed={vi.fn()}>
        <div>chats</div>
      </DesktopSidebarShell>
    </MemoryRouter>,
  );
  const handle = screen.getByRole("separator");
  fireEvent(
    handle,
    new MouseEvent("pointerdown", { bubbles: true, clientX: 480, button: 0 }),
  );
  expect(document.body.style.cursor).toBe("col-resize");
  expect(document.body.style.userSelect).toBe("none");
  fireEvent.lostPointerCapture(handle);
  expect(document.body.style.cursor).toBe("");
  expect(document.body.style.userSelect).toBe("");
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 640,
  });
  fireEvent(window, new Event("resize"));
  expect(
    (container.querySelector("[data-desktop-sidebar]") as HTMLElement).style
      .width,
  ).toBe("320px");
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  fireEvent(window, new Event("resize"));
  expect(
    (container.querySelector("[data-desktop-sidebar]") as HTMLElement).style
      .width,
  ).toBe("480px");
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 640,
  });
  fireEvent(window, new Event("resize"));
  fireEvent.keyDown(handle, { key: "ArrowLeft" });
  expect(
    (container.querySelector("[data-desktop-sidebar]") as HTMLElement).style
      .width,
  ).toBe("310px");
});

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { username: "tester" },
    hasAnyPermission: () => true,
    hasPermission: () => true,
  }),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ enableMemory: true }),
}));
