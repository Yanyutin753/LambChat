/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Header } from "../Header";
import userEvent from "@testing-library/user-event";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "zh" } }),
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
  useAuth: () => ({ user: { permissions: [] } }),
}));
vi.mock("../../../../contexts/ThemeContext", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
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
vi.mock("../../../../services/api", () => ({ authApi: {} }));
vi.mock("../../../../services/api/notification", () => ({
  notificationApi: { getActive: () => Promise.resolve([]) },
}));
afterEach(cleanup);
function openLanguages() {
  render(
    <MemoryRouter>
      <Header
        activeTab="files"
        setMobileSidebarOpen={vi.fn()}
        currentProjectId={null}
        projectManager={{ projects: [] }}
        onNewSession={vi.fn()}
        onShowProfile={vi.fn()}
      />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "common.menu" }));
  fireEvent.click(screen.getByRole("button", { name: "common.language" }));
}
test("opening the sidebar dismisses the header language menu", async () => {
  openLanguages();
  await new Promise((resolve) => setTimeout(resolve, 0));
  fireEvent.click(
    screen.getByRole("button", { name: "sidebar.expandSidebar" }),
  );
  expect(screen.queryByRole("button", { name: "English" })).toBeNull();
  expect(
    screen
      .getByRole("button", { name: "common.menu" })
      .getAttribute("aria-expanded"),
  ).toBe("false");
});
test("Escape closes the language menu and restores focus to its trigger", () => {
  openLanguages();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("button", { name: "English" })).toBeNull();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "common.menu" }),
  );
});

test("keyboard focus stays inside the language submenu after opening it", async () => {
  openLanguages();
  // Return to the parent menu and open its language action with the keyboard.
  fireEvent.click(screen.getByRole("button", { name: "common.language" }));
  screen.getByRole("button", { name: "common.language" }).focus();
  await userEvent.keyboard("{Enter}");
  expect(screen.getByRole("button", { name: "English" })).toBeTruthy();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "common.language" }),
  );
  await userEvent.keyboard("{Enter}");
  expect(screen.queryByRole("button", { name: "English" })).toBeNull();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "common.language" }),
  );
});
