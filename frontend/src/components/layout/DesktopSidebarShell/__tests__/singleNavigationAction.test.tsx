/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
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
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.removeItem("lambchat_activity_rail_order");
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

test("destinations are shown directly when the rail has room", () => {
  access.memory = true;
  render(
    <MemoryRouter>
      <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button", { name: "nav.more" })).toBeNull();
  expect(screen.getByRole("button", { name: "nav.channels" })).toBeVisible();
  expect(
    screen.getByRole("button", { name: "nav.channels" }).querySelector("svg"),
  ).not.toBeNull();
  expect(screen.getByRole("button", { name: "nav.memory" })).toBeVisible();
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

test("assistants remains reachable from the activity rail when the chat sidebar is collapsed", () => {
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
    screen.getByRole("button", { name: "assistants.title" }),
  ).toBeVisible();
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

test("navigation can be reordered with the keyboard and survives remount", () => {
  access.memory = true;
  const mount = () =>
    render(
      <MemoryRouter>
        <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
      </MemoryRouter>,
    );
  const view = mount();
  fireEvent.keyDown(screen.getByRole("button", { name: "nav.memory" }), {
    key: "ArrowUp",
    altKey: true,
  });
  const destinations = () =>
    screen
      .getAllByRole("button")
      .map((button) => button.getAttribute("aria-label"));
  expect(destinations().indexOf("nav.memory")).toBeLessThan(
    destinations().indexOf("nav.channels"),
  );
  view.unmount();
  mount();
  expect(destinations().indexOf("nav.memory")).toBeLessThan(
    destinations().indexOf("nav.channels"),
  );
});

test("resizing folds overflow and allows dragging a hidden destination into the rail", () => {
  access.memory = true;
  access.persona = true;
  let height = 108;
  let resize = () => {};
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
    function (this: HTMLElement) {
      return {
        height: this.tagName === "BUTTON" ? 36 : height,
        width: 36,
        top: 0,
        bottom: 36,
        left: 0,
        right: 36,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      };
    },
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        resize = callback;
      }
      observe() {}
      disconnect() {}
    },
  );
  render(
    <MemoryRouter>
      <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button", { name: "nav.memory" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "nav.more" }));
  const dataTransfer = { setData: vi.fn(), effectAllowed: "", dropEffect: "" };
  fireEvent.dragStart(screen.getByRole("button", { name: "nav.memory" }), {
    dataTransfer,
  });
  fireEvent.dragOver(
    screen.getByRole("button", { name: "personaPresets.title" }),
    { dataTransfer },
  );
  fireEvent.drop(screen.getByRole("button", { name: "personaPresets.title" }), {
    dataTransfer,
  });
  expect(
    screen.getByRole("navigation").querySelector('[data-rail-path="/memory"]'),
  ).not.toBeNull();
  act(() => {
    height = 400;
    resize();
  });
  expect(screen.queryByRole("button", { name: "nav.more" })).toBeNull();
  expect(screen.getAllByRole("button", { name: "nav.memory" })).toHaveLength(1);
});

test("invalid saved order does not hide permitted navigation", () => {
  localStorage.setItem("lambchat_activity_rail_order", "invalid json");
  render(
    <MemoryRouter>
      <DesktopActivityRail collapsed onOpenChats={vi.fn()} />
    </MemoryRouter>,
  );
  expect(screen.getByRole("button", { name: "nav.channels" })).toBeVisible();
});
