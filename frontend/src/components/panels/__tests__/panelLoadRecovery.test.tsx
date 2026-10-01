/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { MemoryPanel } from "../MemoryPanel";
import { NotificationPanel } from "../NotificationPanel";
import { FeedbackPanel } from "../FeedbackPanel";
import { ScheduledTaskPanel } from "../ScheduledTaskPanel";
import { UsagePanel } from "../UsagePanel";
import { ChannelsPage } from "../../pages/ChannelsPage";

const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../../../services/api/memory", () => ({ memoryApi: { list } }));
vi.mock("../../../services/api/notification", () => ({
  notificationApi: { list },
}));
vi.mock("../../../services/api/feedback", () => ({ feedbackApi: { list } }));
vi.mock("../../../services/api/scheduledTask", () => ({
  scheduledTaskApi: { list },
}));
vi.mock("../../../services/api/usage", () => ({
  usageApi: { list, getDashboard: vi.fn().mockResolvedValue(null) },
}));
vi.mock("../../../services/api/channel", () => ({
  channelApi: { getTypes: list },
}));
vi.mock("../../../hooks/useFxRates", () => ({ useFxRates: () => ({}) }));
vi.mock("../../../services/api/personaPreset", () => ({
  personaPresetApi: { list: vi.fn().mockResolvedValue({ presets: [] }) },
}));
vi.mock("../../../services/api/team", () => ({
  teamApi: { list: vi.fn().mockResolvedValue({ teams: [] }) },
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ availableModels: [] }),
}));
afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("en");
  list
    .mockReset()
    .mockRejectedValueOnce(new Error("Network unavailable"))
    .mockResolvedValue({ memories: [], items: [], total: 0, stats: null });
});

test.each([
  ["memory", <MemoryPanel />, "No memories yet"],
  ["notifications", <NotificationPanel />, "No notifications"],
  ["feedback", <FeedbackPanel />, "No feedback yet"],
  ["scheduled tasks", <ScheduledTaskPanel agents={[]} />, "No scheduled tasks"],
  ["usage", <UsagePanel />, "No usage records"],
  ["channels", <ChannelsPage />, "No channels available"],
])(
  "%s keeps a failed load visible and retries the request",
  async (_, panel, emptyText) => {
    if (_ === "channels") list.mockResolvedValue([]);
    render(<MemoryRouter>{panel}</MemoryRouter>);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(i18n.t("common.loadFailed"));
    expect(screen.queryByText(emptyText, { exact: false })).toBeNull();
    fireEvent.click(
      within(alert).getByRole("button", { name: i18n.t("common.refresh") }),
    );
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  },
);
