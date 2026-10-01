/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT } from "../desktopShellPlatform";
import { DesktopSidebarShellGate } from "../DesktopSidebarShell";
vi.mock("../../../workspacePanel/WorkspacePanel", () => ({
  WorkspacePanel: () => <div>workspace files</div>,
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("native sidebar toggle opens the drawer at mobile widths", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  const toggleMobile = vi.fn();
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate
        collapsed={false}
        mobileOpen={false}
        onToggleMobile={toggleMobile}
        onToggleCollapsed={vi.fn()}
      >
        <div>chats</div>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  fireEvent(window, new Event("lambchat:desktop-sidebar-toggle"));
  expect(toggleMobile).toHaveBeenCalledWith(true);
});

test("desktop header omits collapse and gives notification and search equal spacing", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate collapsed={false} onToggleCollapsed={vi.fn()}>
        <div>chats</div>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  expect(
    screen.queryByRole("button", { name: "sidebar.collapseSidebar" }),
  ).toBeNull();
  const notifications = screen.getByRole("button", { name: "nav.notifications" });
  const search = screen.getByRole("button", { name: "sidebar.searchSessions" });
  expect(notifications.parentElement).toBe(search.parentElement);
  expect(notifications).toHaveClass("size-8");
  expect(search).toHaveClass("size-8");
});

test("brand header opens the existing search and notification surfaces", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  const search = vi.fn();
  const notification = vi.fn();
  window.addEventListener(DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT, search);
  window.addEventListener("lambchat:open-notifications", notification);
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate collapsed={false} onToggleCollapsed={vi.fn()}>
        <div>chats</div>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "sidebar.searchSessions" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "nav.notifications" }));
  expect(search).toHaveBeenCalledOnce();
  expect(notification).toHaveBeenCalledOnce();
  window.removeEventListener(DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT, search);
  window.removeEventListener("lambchat:open-notifications", notification);
});

test("resizing across the mobile breakpoint preserves sidebar state", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate collapsed={false} onToggleCollapsed={vi.fn()}>
        <input aria-label="sidebar draft" />
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "keep" } });
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  fireEvent(window, new Event("resize"));
  expect(screen.getByRole("textbox")).toHaveValue("keep");
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  fireEvent(window, new Event("resize"));
  expect(screen.getByRole("textbox")).toHaveValue("keep");
});

test("the left sidebar never mounts workspace files, including a saved legacy files view", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  localStorage.setItem("lambchat_desktop_sidebar_view", "files");
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate collapsed={false} onToggleCollapsed={vi.fn()}>
        <div>chats</div>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  expect(screen.queryByText("workspace files")).toBeNull();
  expect(
    screen.queryByRole("button", { name: "workspacePanel.title" }),
  ).toBeNull();
  expect(screen.getByText("chats")).toBeVisible();
  localStorage.removeItem("lambchat_desktop_sidebar_view");
});

test("activity navigation remains available when the list is collapsed", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  const profile = vi.fn();
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate
        collapsed
        onToggleCollapsed={vi.fn()}
        onShowProfile={profile}
      >
        <div>chats</div>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("button", { name: "fileLibrary.title" }),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "nav.more" }));
  expect(screen.getByRole("button", { name: "nav.more" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: "tester" }));
  expect(profile).toHaveBeenCalledOnce();
});

test("narrow browsers retain the mobile sidebar instead of a hidden desktop shell", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate collapsed={false} onToggleCollapsed={vi.fn()}>
        <button>mobile navigation</button>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("button", { name: "mobile navigation" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "workspacePanel.title" }),
  ).toBeNull();
});

test("the shared sidebar preserves the LambChat brand above the workspace tabs", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate collapsed={false} onToggleCollapsed={vi.fn()}>
        <div>chats</div>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  expect(screen.getByRole("img", { name: "LambChat" })).toBeVisible();
  expect(screen.getByRole("link", { name: "LambChat" })).toHaveAttribute(
    "href",
    "/chat",
  );
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

test("activity rail exposes creation tools and keeps only secondary features in More", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  render(
    <MemoryRouter>
      <DesktopSidebarShellGate collapsed onToggleCollapsed={vi.fn()}>
        <div>chats</div>
      </DesktopSidebarShellGate>
    </MemoryRouter>,
  );
  const rail = screen.getByRole("navigation", { name: "sidebarView" });
  for (const name of [
    "personaPresets.title",
    "nav.team",
    "nav.skills",
    "nav.mcp",
  ]) {
    const button = within(rail).getByRole("button", { name });
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");
  }
  fireEvent.click(within(rail).getByRole("button", { name: "nav.more" }));
  expect(screen.getByRole("button", { name: "nav.channels" })).toBeVisible();
  expect(screen.getByRole("button", { name: "nav.memory" })).toBeVisible();
  expect(screen.getAllByRole("button", { name: "nav.skills" })).toHaveLength(1);
});
