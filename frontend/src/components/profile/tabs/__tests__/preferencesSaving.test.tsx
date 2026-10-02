/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ProfilePreferencesTab } from "../ProfilePreferencesTab";
import { ThemeProvider } from "../../../../contexts/ThemeContext";
import { ThemeToggle } from "../../../common/ThemeToggle";

const api = vi.hoisted(() => ({
  metadata: vi.fn(),
  agent: vi.fn(),
  toast: vi.fn(),
  user: { id: "first", metadata: { memoryEnabled: true } },
  language: "en",
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: api.user }),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({
    availableModels: [
      { id: "model-1", value: "provider/one", label: "Model One" },
      { id: "model-2", value: "provider/two", label: "Model Two" },
    ],
    modelsLoading: false,
    modelsError: false,
    enableMemory: true,
  }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: api.language,
      changeLanguage: (value: string) => {
        api.language = value;
      },
    },
  }),
}));
vi.mock("react-hot-toast", () => ({
  toast: { success: api.toast, error: api.toast },
}));
vi.mock("../../LocalSandboxSection", () => ({ default: () => null }));
vi.mock("../../../../services/api", () => ({
  authApi: { updateMetadata: api.metadata },
  agentApi: {
    list: () =>
      Promise.resolve({
        agents: [
          { id: "fast", name: "Fast" },
          { id: "search", name: "Search" },
        ],
        default_agent: "fast",
      }),
  },
  agentConfigApi: {
    getUserPreference: () => Promise.resolve({ default_agent_id: null }),
    setUserPreference: api.agent,
  },
}));

beforeEach(() => {
  api.metadata.mockReset().mockResolvedValue({});
  api.agent.mockReset().mockResolvedValue({});
  api.toast.mockClear();
  api.user = { id: "first", metadata: { memoryEnabled: true } };
  api.language = "en";
  localStorage.clear();
  localStorage.setItem("defaultModelId", "model-1");
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function preferences() {
  const view = render(
    <ThemeProvider>
      <ProfilePreferencesTab />
    </ThemeProvider>,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "agentConfig.defaultAgent" }),
    ).toBeEnabled(),
  );
  await screen.findByRole("switch", { name: "profile.themeScheduleToggle" });
  api.metadata.mockClear();
  return view;
}
function choose(label: string, option: string) {
  fireEvent.click(screen.getByRole("button", { name: label }));
  fireEvent.click(screen.getByRole("option", { name: option }));
}
function deferred() {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test("opening preferences restores appearance without writing it back to the server", async () => {
  render(
    <ThemeProvider>
      <ProfilePreferencesTab />
    </ThemeProvider>,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "agentConfig.defaultAgent" }),
    ).toBeEnabled(),
  );
  expect(api.metadata).not.toHaveBeenCalled();
});

test("the quick theme control offers retry instead of silently cycling past a failed save", async () => {
  api.metadata
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({});
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
  fireEvent.click(screen.getByRole("button"));
  const retry = await screen.findByRole("button", {
    name: "common.retry: profile.theme",
  });
  expect(retry).toHaveAttribute(
    "aria-description",
    "profile.preferenceSyncFailed",
  );
  fireEvent.click(retry);
  expect(retry).toBeDisabled();
  await waitFor(() => expect(retry).toBeEnabled());
  expect(api.metadata.mock.calls).toEqual([
    [{ theme: "dark", themeSchedule: null }],
    [{ theme: "dark", themeSchedule: null }],
  ]);
});

test("failed default agent keeps its draft and retries the same choice before publishing success", async () => {
  await preferences();
  const pending = deferred();
  api.agent.mockReturnValueOnce(pending.promise).mockResolvedValue({});
  const updated = vi.fn();
  window.addEventListener("agent-preference-updated", updated);
  try {
    choose("agentConfig.defaultAgent", "agents.search.name");
    const field = screen.getByRole("button", {
      name: "agentConfig.defaultAgent",
    });
    expect(field).toBeDisabled();
    expect(document.activeElement?.tagName).toBe("DIV");
    expect(await screen.findByRole("status")).toHaveTextContent(
      "common.saving",
    );
    await act(async () => pending.reject(new Error("Offline")));
    expect(field).toHaveTextContent("agents.search.name");
    expect(screen.getByRole("alert")).toHaveTextContent("common.saveFailed");
    expect(updated).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", {
        name: "common.retry: agentConfig.defaultAgent",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(api.agent.mock.calls).toEqual([["search"], ["search"]]);
    expect(updated).toHaveBeenCalledOnce();
    expect(document.activeElement?.tagName).toBe("DIV");
  } finally {
    window.removeEventListener("agent-preference-updated", updated);
  }
});

test("default model applies locally, retains its choice on sync failure and retries without replaying local events", async () => {
  await preferences();
  const pending = deferred();
  api.metadata.mockReturnValueOnce(pending.promise).mockResolvedValue({});
  const updated = vi.fn();
  window.addEventListener("model-preference-updated", updated);
  try {
    choose("profile.defaultModel", "Model Two");
    const field = screen.getByRole("button", { name: "profile.defaultModel" });
    expect(field).toBeDisabled();
    expect(localStorage.getItem("defaultModelId")).toBe("model-2");
    await act(async () => pending.reject(new Error("Offline")));
    expect(field).toHaveTextContent("Model Two");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "profile.preferenceSyncFailed",
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "common.retry: profile.defaultModel",
      }),
    );
    await waitFor(() => expect(field).toBeEnabled());
    expect(api.metadata.mock.calls).toEqual([
      [{ defaultModel: "provider/two", defaultModelId: "model-2" }],
      [{ defaultModel: "provider/two", defaultModelId: "model-2" }],
    ]);
    expect(updated).toHaveBeenCalledOnce();
  } finally {
    window.removeEventListener("model-preference-updated", updated);
  }
});

test.each([
  ["profile.language", "日本語", { language: "ja" }],
  ["profile.fontSize", "profile.fontSizeLarge", { fontScale: "large" }],
  [
    "profile.newlineModifier",
    "profile.newlineShift",
    { newlineModifier: "shift" },
  ],
  [
    "profile.defaultThinking",
    "agentOptions.enableThinking.options.high",
    { defaultThinkingLevel: "high" },
  ],
])(
  "%s keeps device settings and exposes a retry for cloud sync",
  async (label, option, payload) => {
    await preferences();
    api.metadata
      .mockRejectedValueOnce(new Error("Offline"))
      .mockResolvedValue({});
    choose(label, option);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "profile.preferenceSyncFailed",
    );
    expect(screen.getByRole("button", { name: label })).toHaveTextContent(
      option,
    );
    fireEvent.click(
      screen.getByRole("button", { name: `common.retry: ${label}` }),
    );
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(api.metadata.mock.calls).toEqual([[payload], [payload]]);
  },
);

test("memory has a native disabled switch while saving, then preserves a failed choice for retry", async () => {
  await preferences();
  const pending = deferred();
  api.metadata.mockReturnValueOnce(pending.promise).mockResolvedValue({});
  const field = screen.getByRole("switch", { name: "profile.memoryToggle" });
  fireEvent.click(field);
  expect(field).toBeDisabled();
  fireEvent.click(field);
  await act(async () => pending.reject(new Error("Offline")));
  expect(field).toHaveAttribute("aria-checked", "false");
  expect(screen.getByRole("alert")).toHaveTextContent("common.saveFailed");
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: profile.memoryToggle" }),
  );
  await waitFor(() => expect(field).toBeEnabled());
  expect(api.metadata.mock.calls).toEqual([
    [{ memoryEnabled: false }],
    [{ memoryEnabled: false }],
  ]);
});

test("cloud confirmation failure is explicitly unsaved and retries its selected policy", async () => {
  await preferences();
  api.metadata
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({});
  choose(
    "profile.localSandbox.policy",
    "profile.localSandbox.policyOptions.all",
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "common.saveFailed",
  );
  expect(
    screen.getByRole("button", { name: "profile.localSandbox.policy" }),
  ).toHaveTextContent("profile.localSandbox.policyOptions.all");
  fireEvent.click(
    screen.getByRole("button", {
      name: "common.retry: profile.localSandbox.policy",
    }),
  );
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(api.metadata.mock.calls).toEqual([
    [{ sandboxCloudConfirmPolicy: "all" }],
    [{ sandboxCloudConfirmPolicy: "all" }],
  ]);
});

test("theme is written once, including disabled automatic switching, with a recoverable local sync state", async () => {
  localStorage.setItem(
    "lambchat-theme-schedule",
    JSON.stringify({
      enabled: true,
      start: "22:00",
      end: "07:00",
      nightTheme: "sepia",
    }),
  );
  await preferences();
  api.metadata
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({});
  choose("profile.theme", "profile.darkTheme");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "profile.preferenceSyncFailed",
  );
  expect(
    screen.getByRole("button", { name: "profile.theme" }),
  ).toHaveTextContent("profile.darkTheme");
  expect(
    screen.getByRole("switch", { name: "profile.themeScheduleToggle" }),
  ).toHaveAttribute("aria-checked", "false");
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: profile.theme" }),
  );
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  const payload = {
    theme: "dark",
    themeSchedule: {
      enabled: false,
      start: "22:00",
      end: "07:00",
      nightTheme: "sepia",
    },
  };
  expect(api.metadata.mock.calls).toEqual([[payload], [payload]]);
});

test("scheduled appearance reports cloud failure and retries its exact locally applied schedule", async () => {
  await preferences();
  api.metadata
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({});
  const field = screen.getByRole("switch", {
    name: "profile.themeScheduleToggle",
  });
  fireEvent.click(field);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "profile.preferenceSyncFailed",
  );
  expect(field).toHaveAttribute("aria-checked", "true");
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: profile.theme" }),
  );
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(api.metadata.mock.calls).toHaveLength(2);
  expect(api.metadata.mock.calls[1]).toEqual(api.metadata.mock.calls[0]);
});

test("choosing another theme after failure also synchronizes the locally disabled schedule", async () => {
  const schedule = {
    enabled: true,
    start: "22:00",
    end: "07:00",
    nightTheme: "sepia",
  };
  localStorage.setItem("lambchat-theme-schedule", JSON.stringify(schedule));
  await preferences();
  api.metadata
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({});
  choose("profile.theme", "profile.darkTheme");
  await screen.findByRole("alert");
  choose("profile.theme", "profile.sepiaTheme");
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(api.metadata.mock.calls[1]).toEqual([
    { theme: "sepia", themeSchedule: { ...schedule, enabled: false } },
  ]);
});

test("enabling the schedule after a failed theme write synchronizes the effective theme too", async () => {
  await preferences();
  api.metadata
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({});
  choose("profile.theme", "profile.sepiaTheme");
  await screen.findByRole("alert");
  fireEvent.click(
    screen.getByRole("switch", { name: "profile.themeScheduleToggle" }),
  );
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  const schedule = JSON.parse(localStorage.getItem("lambchat-theme-schedule")!);
  expect(api.metadata.mock.calls[1]).toEqual([
    { theme: localStorage.getItem("lambchat-theme"), themeSchedule: schedule },
  ]);
});

test("late agent success cannot publish an old user's preference into a newly mounted profile", async () => {
  const view = await preferences();
  const pending = deferred();
  api.agent.mockReturnValue(pending.promise);
  const updated = vi.fn();
  window.addEventListener("agent-preference-updated", updated);
  try {
    choose("agentConfig.defaultAgent", "agents.search.name");
    await waitFor(() => expect(api.agent).toHaveBeenCalledOnce());
    api.user = { id: "second", metadata: { memoryEnabled: true } };
    view.rerender(
      <ThemeProvider>
        <ProfilePreferencesTab />
      </ThemeProvider>,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "agentConfig.defaultAgent" }),
      ).toHaveTextContent("agents.fast.name"),
    );
    await act(async () => pending.resolve());
    expect(updated).not.toHaveBeenCalled();
    expect(api.toast).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
  } finally {
    window.removeEventListener("agent-preference-updated", updated);
  }
});

test("switching accounts before a queued write starts prevents sending the old draft", async () => {
  const view = await preferences();
  choose("agentConfig.defaultAgent", "agents.search.name");
  api.user = { id: "second", metadata: { memoryEnabled: true } };
  view.rerender(
    <ThemeProvider>
      <ProfilePreferencesTab />
    </ThemeProvider>,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "agentConfig.defaultAgent" }),
    ).toHaveTextContent("agents.fast.name"),
  );
  expect(api.agent).not.toHaveBeenCalled();
});
