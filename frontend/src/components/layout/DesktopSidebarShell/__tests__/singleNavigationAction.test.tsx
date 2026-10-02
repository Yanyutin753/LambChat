/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { DesktopActivityRail } from "../DesktopActivityRail";
import { useMoreMenu } from "../../../../hooks/useMoreMenu";
import { Permission } from "../../../../types/auth";

const access = vi.hoisted(() => ({ channels: true, memory: false }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: null,
    hasPermission: () => false,
    hasAnyPermission: (permissions: string[]) =>
      access.channels && permissions.includes(Permission.CHANNEL_READ),
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
