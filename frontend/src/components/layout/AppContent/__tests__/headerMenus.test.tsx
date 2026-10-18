import { LanguagePreferenceProvider } from "../../../../hooks/useLanguagePreference";
import type { ReactNode } from "react";
/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render as renderBase,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Header } from "../Header";
import userEvent from "@testing-library/user-event";
import { OPEN_NOTIFICATIONS_EVENT } from "../../DesktopSidebarShell/desktopShellPlatform";
const appearance = vi.hoisted(() => ({
  state: undefined as "saving" | "error" | undefined,
  retry: vi.fn(),
  language: vi.fn(),
  write: vi.fn().mockResolvedValue({}),
  userId: "first",
  quotaRead: vi.fn().mockResolvedValue(null),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "zh", changeLanguage: appearance.language },
  }),
}));
vi.mock("../../../../hooks/useFxRates", () => ({ useFxRates: () => null }));
vi.mock("../../../../hooks/useTodayUsageCost", () => ({
  TODAY_USAGE_REFRESH_EVENT: "today-usage-refresh",
  useTodayUsageCost: () => ({ stats: null }),
}));
vi.mock("../../../../services/api/fetch", () => ({ authFetch: vi.fn() }));
vi.mock("../../../../services/api/usage", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../../services/api/usage")>()),
  usageApi: { getQuota: (...args: unknown[]) => appearance.quotaRead(...args) },
}));
vi.mock("../../../common/SceneIllustration", () => ({
  SceneIllustration: () => null,
}));
vi.mock("../../../agent/ModelSelector", () => ({ ModelSelector: () => null }));
vi.mock("../../UserMenu", () => ({ UserMenu: () => null }));
vi.mock("../../../share/ShareDialog", () => ({ ShareDialog: () => null }));
vi.mock("../../../notification/NotificationDialog", () => ({
  NotificationDialog: () => null,
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: appearance.userId, permissions: [] } }),
}));
vi.mock("../../../../contexts/ThemeContext", () => ({
  useTheme: () => ({
    theme: "light",
    toggleTheme: vi.fn(),
    appearanceState: appearance.state,
    retryAppearance: appearance.retry,
  }),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({
    pinnedModelIds: [],
    togglePinnedModel: vi.fn(),
  }),
}));
vi.mock("../../../../hooks/useStickyDropdownPosition", () => ({
  useStickyDropdownPosition: () => ({ top: 44, right: 12 }),
}));
vi.mock("../../../../hooks/useSessionTitle", () => ({
  useSessionTitle: () => "",
}));
vi.mock("../../../../services/api/auth", () => ({
  authApi: { updateMetadata: appearance.write },
}));
vi.mock("../../../../services/api/notification", () => ({
  notificationApi: { getActive: () => Promise.resolve([]) },
}));
afterEach(() => {
  cleanup();
  appearance.state = undefined;
  appearance.retry.mockClear();
  appearance.language.mockClear();
  appearance.write.mockReset().mockResolvedValue({});
  appearance.userId = "first";
  appearance.quotaRead.mockReset().mockResolvedValue(null);
});

test("switching accounts aborts the old quota request and reloads the new account", async () => {
  appearance.quotaRead.mockImplementation(() => new Promise(() => {}));
  const props = {
    activeTab: "files" as const,
    setMobileSidebarOpen: vi.fn(),
    onNewSession: vi.fn(),
    onShowProfile: vi.fn(),
  };
  const view = render(
    <MemoryRouter>
      <Header {...props} />
    </MemoryRouter>,
  );
  await waitFor(() => expect(appearance.quotaRead).toHaveBeenCalledTimes(1));
  const signal = appearance.quotaRead.mock.calls[0][0] as AbortSignal;
  appearance.userId = "second";
  view.rerender(
    <MemoryRouter>
      <Header {...props} />
    </MemoryRouter>,
  );
  await waitFor(() => expect(appearance.quotaRead).toHaveBeenCalledTimes(2));
  expect(signal.aborted).toBe(true);
});
function renderHeader() {
  render(
    <MemoryRouter>
      <Header
        activeTab="files"
        setMobileSidebarOpen={vi.fn()}
        onNewSession={vi.fn()}
        onShowProfile={vi.fn()}
      />
    </MemoryRouter>,
  );
}

test("panel navigation groups the page title and actions and returns through history", async () => {
  function Location() {
    return <output data-testid="location">{useLocation().pathname}</output>;
  }
  render(
    <MemoryRouter initialEntries={["/chat", "/mcp"]} initialIndex={1}>
      <Header
        activeTab="mcp"
        setMobileSidebarOpen={vi.fn()}
        onNewSession={vi.fn()}
        onShowProfile={vi.fn()}
        headerActions={<button>Create server</button>}
      />
      <Location />
    </MemoryRouter>,
  );
  const navigation = within(
    screen.getByRole("navigation", { name: "nav.mcp" }),
  );
  expect(navigation.getByRole("heading", { name: "nav.mcp" })).toBeTruthy();
  expect(
    navigation.getByRole("button", { name: "Create server" }),
  ).toBeTruthy();
  expect(navigation.getByRole("button", { name: "common.menu" })).toBeTruthy();
  await userEvent.click(
    navigation.getByRole("button", { name: "common.back" }),
  );
  expect(screen.getByTestId("location").textContent).toBe("/chat");
});
function openLanguages() {
  renderHeader();
  fireEvent.click(screen.getByRole("button", { name: "common.menu" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "common.language" }));
}
test("a failed appearance sync is reachable as a retry in the header menu", () => {
  appearance.state = "error";
  renderHeader();
  fireEvent.click(screen.getByRole("button", { name: "common.menu" }));
  fireEvent.click(
    screen.getByRole("menuitem", { name: "common.retry: profile.theme" }),
  );
  expect(appearance.retry).toHaveBeenCalledOnce();
});
test("opening notifications externally dismisses the header menu first", () => {
  renderHeader();
  fireEvent.click(screen.getByRole("button", { name: "common.menu" }));
  fireEvent(window, new CustomEvent(OPEN_NOTIFICATIONS_EVENT));
  expect(screen.queryByRole("menu")).toBeNull();
});
test("external notification actions retain their actual opener focus", async () => {
  renderHeader();
  render(
    <button
      onClick={() =>
        window.dispatchEvent(new CustomEvent(OPEN_NOTIFICATIONS_EVENT))
      }
    >
      Sidebar notifications
    </button>,
  );
  const opener = screen.getByRole("button", { name: "Sidebar notifications" });
  await userEvent.click(opener);
  expect(opener).toHaveFocus();
});
test("header actions use a named menu with arrow navigation and focus return", async () => {
  renderHeader();
  const trigger = screen.getByRole("button", { name: "common.menu" });
  fireEvent.click(trigger);
  const menu = screen.getByRole("menu", { name: "common.menu" });
  expect(trigger).toHaveAttribute("aria-controls", menu.id);
  const notifications = screen.getByRole("menuitem", {
    name: "nav.notifications",
  });
  expect(notifications).toHaveFocus();
  await userEvent.keyboard("{ArrowDown}");
  expect(
    screen.getByRole("menuitem", { name: "theme.switchToDark" }),
  ).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  expect(screen.queryByRole("menu")).toBeNull();
  expect(trigger).toHaveFocus();
});
test("opening the sidebar dismisses the header language menu", async () => {
  openLanguages();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await userEvent.click(
    screen.getByRole("button", { name: "sidebar.expandSidebar" }),
  );
  expect(screen.queryByRole("menuitemradio", { name: "English" })).toBeNull();
  expect(
    screen
      .getByRole("button", { name: "common.menu" })
      .getAttribute("aria-expanded"),
  ).toBe("false");
});
test("Escape closes the language menu and restores focus to its trigger", () => {
  openLanguages();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menuitemradio", { name: "English" })).toBeNull();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "common.menu" }),
  );
});

test("language choices expose selection and returning focuses the parent action", async () => {
  openLanguages();
  expect(screen.getByRole("menu", { name: "common.language" })).toBeTruthy();
  expect(screen.getByRole("menuitemradio", { name: "中文" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  expect(screen.getByRole("menuitem", { name: "common.back" })).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  expect(
    screen.getByRole("menuitem", { name: "common.language" }),
  ).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  expect(screen.getByRole("menuitemradio", { name: "English" })).toBeTruthy();
  await userEvent.keyboard("{ArrowDown}");
  expect(screen.getByRole("menuitemradio", { name: "English" })).toHaveFocus();
});

test("header language sync exposes failure and retries without changing local language twice", async () => {
  let reject!: (reason: Error) => void;
  appearance.write.mockReturnValueOnce(
    new Promise((_yes, no) => {
      reject = no;
    }),
  );
  openLanguages();
  fireEvent.click(screen.getByRole("menuitemradio", { name: "English" }));
  await waitFor(() =>
    expect(appearance.write).toHaveBeenCalledWith({ language: "en" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "common.menu" }));
  expect(
    screen.getByRole("menuitem", { name: "common.language · common.saving" }),
  ).toBeDisabled();
  await act(async () => reject(new Error("fixture failed")));
  fireEvent.click(
    screen.getByRole("menuitem", { name: "common.retry: common.language" }),
  );
  await waitFor(() => expect(appearance.write).toHaveBeenCalledTimes(2));
  expect(appearance.write).toHaveBeenLastCalledWith({ language: "en" });
  expect(appearance.language).toHaveBeenCalledExactlyOnceWith("en");
});

function render(children: ReactNode) {
  return renderBase(children, { wrapper: LanguagePreferenceProvider });
}

test("wide-screen header opener dispatches the sidebar toggle event", () => {
  const toggle = vi.fn();
  const previousWidth = window.innerWidth;
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  window.addEventListener("lambchat:desktop-sidebar-toggle", toggle);
  try {
    renderHeader();
    fireEvent.click(
      screen.getByRole("button", { name: "sidebar.expandSidebar" }),
    );
    expect(toggle).toHaveBeenCalledOnce();
  } finally {
    window.removeEventListener("lambchat:desktop-sidebar-toggle", toggle);
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: previousWidth,
    });
  }
});
