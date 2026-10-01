/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { DesktopSidebarShell } from "../DesktopSidebarShell";
import { DESKTOP_SIDEBAR_TOGGLE_EVENT } from "../desktopShellPlatform";

// File browsing has an independent API lifecycle; this check concerns the shell.
vi.mock("../../../workspacePanel/WorkspacePanel", () => ({
  WorkspacePanel: () => null,
}));
afterEach(cleanup);

test("collapsed sidebar disables its hidden controls and restores them on expansion", () => {
  const shell = (collapsed: boolean) => (
    <MemoryRouter>
      <DesktopSidebarShell collapsed={collapsed} onToggleCollapsed={() => {}}>
        <button>New chat</button>
      </DesktopSidebarShell>
    </MemoryRouter>
  );
  const { container, rerender } = render(shell(true));
  const sidebar = container.querySelector("[data-desktop-sidebar]")!;
  expect(sidebar.hasAttribute("inert")).toBe(true);
  rerender(shell(false));
  expect(sidebar.hasAttribute("inert")).toBe(false);
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

test("panels hide the wide sidebar while chat keeps its expanded preference", () => {
  function Routes() {
    const navigate = useNavigate();
    return (
      <>
        <button onClick={() => navigate("/scheduled-tasks")}>Tasks page</button>
        <button onClick={() => navigate("/settings")}>Settings page</button>
        <button onClick={() => navigate("/chat")}>Chat page</button>
        <DesktopSidebarShell collapsed={false} onToggleCollapsed={() => {}}>
          <button>New chat</button>
        </DesktopSidebarShell>
      </>
    );
  }
  const { container, getByText } = render(
    <MemoryRouter initialEntries={["/chat"]}>
      <Routes />
    </MemoryRouter>,
  );
  const sidebar = () => container.querySelector("[data-desktop-sidebar]")!;
  expect(sidebar().hasAttribute("inert")).toBe(false);
  fireEvent.click(getByText("Tasks page"));
  expect(sidebar().hasAttribute("inert")).toBe(true);
  fireEvent(window, new Event(DESKTOP_SIDEBAR_TOGGLE_EVENT));
  expect(sidebar().hasAttribute("inert")).toBe(false);
  fireEvent.click(getByText("Settings page"));
  expect(sidebar().hasAttribute("inert")).toBe(true);
  fireEvent.click(getByText("Chat page"));
  expect(sidebar().hasAttribute("inert")).toBe(false);
});
