/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { vi } from "vitest";
import { SettingsPanel } from "../SettingsPanel";

const mocks = vi.hoisted(() => ({
  resetAll: vi.fn(async () => true),
  hasPermission: () => true,
  navigation: undefined as { id: string; categories: never[] }[] | undefined,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../i18n", () => ({ default: { language: "en" } }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: mocks.hasPermission }),
}));
vi.mock("../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({
    settings: {
      navigation: mocks.navigation,
      settings: {
        frontend: [
          {
            key: "THEME",
            category: "frontend",
            subcategory: "display",
            description: "Theme",
            type: "string",
            value: "light",
            default_value: "light",
          },
        ],
        llm: [
          {
            key: "MODEL",
            category: "llm",
            subcategory: "general",
            description: "Model",
            type: "string",
            value: "default",
            default_value: "default",
          },
        ],
      },
    },
    isLoading: false,
    error: null,
    savingKeys: new Set(),
    resetAllSettings: mocks.resetAll,
  }),
}));
vi.mock("../../../services/api", () => ({
  roleApi: { list: async () => ({ roles: [] }) },
  agentApi: { list: async () => ({ agents: [] }) },
  modelApi: { list: async () => ({ models: [] }) },
}));
vi.mock("../../common/AboutDialog", () => ({ AboutDialog: () => null }));
vi.mock("../SystemHealthSection", () => ({ SystemHealthSection: () => null }));
vi.mock("../JsonSchemaEditor", () => ({ JsonSchemaEditor: () => null }));
vi.mock("../../common", async () => import("../../common/ui"));
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn() } }));

beforeEach(() => {
  mocks.navigation = undefined;
  mocks.resetAll.mockReset().mockResolvedValue(true);
  Element.prototype.scrollTo = vi.fn();
});
afterEach(cleanup);

test("empty navigation does not expose missing translation keys", () => {
  mocks.navigation = [];
  render(<SettingsPanel />);
  expect(screen.queryByText("settings.navigation.groups.undefined")).toBeNull();
  expect(
    screen.queryByText("settings.navigation.descriptions.undefined"),
  ).toBeNull();
});

test.each([0, 1])(
  "reset all entry %i requires explicit confirmation and cancel preserves settings",
  async (index) => {
    render(<SettingsPanel />);
    fireEvent.click(
      screen.getAllByRole("button", { name: "common.resetAll" })[index],
    );
    expect(screen.getByText("settings.resetAllConfirmMessage")).toBeTruthy();
    expect(mocks.resetAll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByText("settings.resetAllConfirmMessage")).toBeNull();
    expect(mocks.resetAll).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getAllByRole("button", { name: "common.resetAll" })[index],
    );
    // The last button is inside the confirmation dialog portal.
    fireEvent.click(
      screen.getAllByRole("button", { name: "common.resetAll" }).at(-1)!,
    );
    await waitFor(() => expect(mocks.resetAll).toHaveBeenCalledTimes(1));
  },
);

test("category navigation exits global search and keeps unsaved input", async () => {
  render(<SettingsPanel />);
  fireEvent.change(screen.getByDisplayValue("light"), {
    target: { value: "dark" },
  });
  fireEvent.change(
    screen.getByRole("textbox", {
      name: "settings.navigation.searchPlaceholder",
    }),
    { target: { value: "MODEL" } },
  );
  expect(
    screen.getByRole("heading", { name: "settings.navigation.searchResults" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /categories.frontend/ }));
  await waitFor(() => expect(screen.getByDisplayValue("dark")).toBeTruthy());
  expect(
    (
      screen.getByRole("textbox", {
        name: "settings.navigation.searchPlaceholder",
      }) as HTMLInputElement
    ).value,
  ).toBe("");
});

test("reset confirmation blocks repeated submission while the reset is pending", async () => {
  let finish!: (success: boolean) => void;
  mocks.resetAll.mockImplementationOnce(
    () =>
      new Promise<boolean>((resolve) => {
        finish = resolve;
      }),
  );
  render(<SettingsPanel />);
  fireEvent.click(
    screen.getAllByRole("button", { name: "common.resetAll" })[0],
  );
  const confirm = screen
    .getAllByRole("button", { name: "common.resetAll" })
    .at(-1)! as HTMLButtonElement;
  fireEvent.click(confirm);
  expect(confirm.disabled).toBe(true);
  fireEvent.click(confirm);
  expect(mocks.resetAll).toHaveBeenCalledTimes(1);
  finish(true);
  await waitFor(() =>
    expect(screen.queryByText("settings.resetAllConfirmMessage")).toBeNull(),
  );
});

test("failed reset keeps the confirmation available for retry", async () => {
  mocks.resetAll.mockResolvedValueOnce(false);
  render(<SettingsPanel />);
  fireEvent.click(
    screen.getAllByRole("button", { name: "common.resetAll" })[0],
  );
  fireEvent.click(
    screen.getAllByRole("button", { name: "common.resetAll" }).at(-1)!,
  );
  await waitFor(() => expect(mocks.resetAll).toHaveBeenCalledTimes(1));
  expect(screen.queryByText("settings.resetAllConfirmMessage")).toBeTruthy();
});
