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
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ProfilePreferencesTab } from "../ProfilePreferencesTab";
const api = vi.hoisted(() => ({
  agents: vi.fn(),
  preference: vi.fn(),
  save: vi.fn(),
  reload: vi.fn(),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({
    availableModels: null,
    modelsLoading: false,
    modelsError: true,
    reloadModels: api.reload,
    enableMemory: false,
  }),
}));
vi.mock("../../../../contexts/ThemeContext", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "user", metadata: {} } }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../ThemeScheduleSection", () => ({ default: () => null }));
vi.mock("../../../../services/api", () => ({
  authApi: { updateMetadata: api.save },
  agentApi: { list: api.agents },
  agentConfigApi: {
    getUserPreference: api.preference,
    setUserPreference: api.save,
  },
}));
beforeEach(() => {
  api.agents.mockReset();
  api.preference.mockReset();
  api.save.mockReset();
  api.reload.mockReset();
});
afterEach(cleanup);
test("preference catalog errors offer independent retries without writing stored choices", async () => {
  let reject!: (error: Error) => void;
  const pending = new Promise((_resolve, r) => {
    reject = r;
  });
  api.agents.mockReturnValueOnce(pending).mockResolvedValue({
    agents: [{ id: "fast", name: "Fast" }],
    default_agent: "fast",
  });
  api.preference.mockResolvedValue({ default_agent_id: "fast" });
  render(<ProfilePreferencesTab />);
  expect(screen.getByRole("button", { name: "profile.language" })).toBeTruthy();
  const select = await screen.findByRole("button", {
    name: "agentConfig.defaultAgent",
  });
  expect(select).toBeDisabled();
  await act(async () => reject(new Error("Offline")));
  const retry = await screen.findByRole("button", {
    name: "common.retry: agentConfig.defaultAgent",
  });
  expect(select).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: profile.defaultModel" }),
  );
  expect(api.reload).toHaveBeenCalledOnce();
  fireEvent.click(retry);
  await waitFor(() => expect(select).toBeEnabled());
  expect(select).toHaveTextContent("agents.fast.name");
  expect(api.save).not.toHaveBeenCalled();
});

test("a failed saved preference is not silently replaced by the system default", async () => {
  api.agents.mockResolvedValue({
    agents: [
      { id: "fast", name: "Fast" },
      { id: "search", name: "Search" },
    ],
    default_agent: "fast",
  });
  api.preference
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({ default_agent_id: "search" });
  render(<ProfilePreferencesTab />);
  const retry = await screen.findByRole("button", {
    name: "common.retry: agentConfig.defaultAgent",
  });
  const select = screen.getByRole("button", {
    name: "agentConfig.defaultAgent",
  });
  expect(select).toBeDisabled();
  expect(select).not.toHaveTextContent("agents.fast.name");
  fireEvent.click(retry);
  await waitFor(() => expect(select).toHaveTextContent("agents.search.name"));
  expect(select).toBeEnabled();
  expect(api.save).not.toHaveBeenCalled();
});

function render(children: ReactNode) {
  return renderBase(children, { wrapper: LanguagePreferenceProvider });
}
