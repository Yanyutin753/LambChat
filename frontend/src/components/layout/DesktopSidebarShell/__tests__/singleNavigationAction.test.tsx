/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { DesktopActivityRail } from "../DesktopActivityRail";
import { useMoreMenu } from "../../../../hooks/useMoreMenu";
import { Permission } from "../../../../types/auth";

const access = vi.hoisted(() => ({
  channels: true,
  memory: false,
  persona: false,
  assistants: false,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: null,
    hasPermission: (permission: string) =>
      access.assistants && permission === Permission.SESSION_READ,
    hasAnyPermission: (permissions: string[]) =>
      (access.assistants && permissions.includes(Permission.SESSION_READ)) ||
      (access.channels && permissions.includes(Permission.CHANNEL_READ)) ||
      (access.memory && permissions.includes(Permission.MEMORY_READ)) ||
      (access.persona && permissions.includes(Permission.PERSONA_PRESET_READ)),
  }),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ enableMemory: access.memory }),
}));
vi.mock("../../../panels/SidebarParts/SidebarUserRow", () => ({
  SidebarUserRow: () => null,
}));
afterEach(() => {
  cleanup();
  access.channels = true;
  access.memory = false;
  access.persona = false;
  access.assistants = false;
});
function Location() {
  return <output>{useLocation().pathname}</output>;
}

test("a single permitted rail destination navigates directly", () => {
  render(
    <MemoryRouter>
      <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
      <Location />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button", { name: "nav.more" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "nav.channels" }));
  expect(screen.getByRole("status")).toHaveTextContent("/channels");
});

test("two permitted rail destinations keep their menu", () => {
  access.memory = true;
  render(
    <MemoryRouter>
      <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "nav.more" }));
  expect(screen.getByText("nav.channels")).toBeInTheDocument();
  expect(screen.getByText("nav.memory")).toBeInTheDocument();
});

function SidebarNavigation() {
  const menu = useMoreMenu({ isCollapsed: false, isMobile: true });
  return (
    <button onClick={menu.toggleMoreMenu}>
      {menu.singleMoreMenuItem?.label ?? "nav.more"}
    </button>
  );
}

test("a single permitted sidebar destination navigates directly", () => {
  access.channels = false;
  access.persona = true;
  render(
    <MemoryRouter>
      <SidebarNavigation />
      <Location />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button", { name: "nav.more" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "personaPresets.title" }));
  expect(screen.getByRole("status")).toHaveTextContent("/persona");
});

test("chat and channels use distinct navigation symbols", () => {
  render(
    <MemoryRouter>
      <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
    </MemoryRouter>,
  );
  const shape = (name: string) =>
    Array.from(
      screen.getByRole("button", { name }).querySelectorAll("svg path"),
    )
      .map((path) => path.getAttribute("d"))
      .join(" ");
  expect(shape("nav.channels")).not.toBe(shape("workspacePanel.viewChats"));
});

test("assistants has one fallback entry only when the chat sidebar is collapsed", () => {
  access.assistants = true;
  const view = render(
    <MemoryRouter>
      <DesktopActivityRail collapsed={false} onOpenChats={vi.fn()} />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button", { name: "assistants.title" })).toBeNull();
  view.rerender(
    <MemoryRouter>
      <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
    </MemoryRouter>,
  );
  expect(
    screen.getAllByRole("button", { name: "assistants.title" }),
  ).toHaveLength(1);
});

test("assistants does not duplicate the dedicated sidebar entry in More", () => {
  access.assistants = true;
  access.channels = false;
  render(
    <MemoryRouter>
      <SidebarNavigation />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button", { name: "assistants.title" })).toBeNull();
});
