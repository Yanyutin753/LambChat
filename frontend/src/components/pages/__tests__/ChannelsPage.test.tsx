/** @vitest-environment jsdom */
import { render, screen, cleanup, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { test, expect, vi, afterEach } from "vitest";
import { ChannelsPage } from "../ChannelsPage";
import { channelApi } from "../../../services/api/channel";
import i18n from "../../../i18n";
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../panels/ChannelPanel", () => ({
  ChannelPanel: ({ onClose }: { onClose: () => void }) => (
    <button
      onClick={() => {
        const background = document.getElementById("simulated-background");
        background?.setAttribute("inert", "");
        onClose();
        background?.removeAttribute("inert");
      }}
    >
      Close editor
    </button>
  ),
}));
vi.mock("../../panels/channel/feishu/FeishuPanel", () => ({
  FeishuPanel: () => null,
}));
vi.mock("../../../services/api/channel", () => ({
  channelApi: { getTypes: vi.fn(), listByType: vi.fn(), getStatus: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.resetAllMocks();
});
const metadata = {
  channel_type: "slack" as const,
  display_name: "Slack",
  description: "Team messaging",
  icon: "BotMessageSquare",
  capabilities: [],
  config_schema: {},
  requires_webhook: false,
  requires_websocket: true,
  config_fields: [],
  setup_guide: [],
};
const instance = {
  instance_id: "fixture",
  channel_type: "slack" as const,
  user_id: "fixture",
  name: "Long channel name with several words",
  enabled: true,
  config: {},
  capabilities: [],
};
function mount(path = "/channels/slack") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/channels/:channelType?/:instanceId?"
          element={<ChannelsPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}
test("failed instance list remains distinct from empty and retry restores native links without duplicate reads", async () => {
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType)
    .mockRejectedValueOnce(new Error("List unavailable"))
    .mockResolvedValue([instance]);
  vi.mocked(channelApi.getStatus).mockResolvedValue({
    channel_type: "slack",
    enabled: true,
    connected: true,
  });
  mount();
  await screen.findByRole("alert");
  expect(screen.queryByText(i18n.t("channel.noInstances"))).toBeNull();
  expect(channelApi.listByType).toHaveBeenCalledTimes(1);
  await userEvent.setup().click(
    screen.getByRole("button", {
      name: i18n.t("common.refresh"),
      exact: true,
    }),
  );
  const link = await screen.findByRole("link", {
    name: new RegExp(instance.name),
  });
  expect(link).toHaveAttribute("href", "/channels/slack/fixture");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(channelApi.listByType).toHaveBeenCalledTimes(2);
  expect(document.activeElement).not.toBe(document.body);
});
test("pending list does not show a false empty state", async () => {
  let finish!: (value: (typeof instance)[]) => void;
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  mount();
  await waitFor(() => expect(channelApi.listByType).toHaveBeenCalled());
  expect(screen.queryByText(i18n.t("channel.noInstances"))).toBeNull();
  await act(async () => finish([]));
  expect(await screen.findByText(i18n.t("channel.noInstances"))).toBeVisible();
});
test.each(["/channels", "/channels/slack"])(
  "catalog failure remains recoverable at %s and preserves focus",
  async (path) => {
    vi.mocked(channelApi.getTypes)
      .mockRejectedValueOnce(new Error("Catalog unavailable"))
      .mockResolvedValue(path === "/channels" ? [] : [metadata]);
    vi.mocked(channelApi.listByType).mockResolvedValue([]);
    mount(path);
    await screen.findByRole("alert");
    expect(screen.queryByText(i18n.t("channel.noInstances"))).toBeNull();
    await userEvent.setup().click(
      screen.getByRole("button", {
        name: i18n.t("common.refresh"),
        exact: true,
      }),
    );
    expect(
      await screen.findByText(
        i18n.t(
          path === "/channels" ? "channel.noChannels" : "channel.noInstances",
        ),
      ),
    ).toBeVisible();
    expect(document.activeElement).not.toBe(document.body);
  },
);
test("unavailable status is not disabled and status retry does not reload the instance list", async () => {
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType).mockResolvedValue([instance]);
  vi.mocked(channelApi.getStatus)
    .mockRejectedValueOnce(new Error("Status unavailable"))
    .mockResolvedValue({
      channel_type: "slack",
      enabled: true,
      connected: true,
    });
  mount();
  await screen.findByRole("alert");
  expect(screen.queryByText(i18n.t("channel.disabled"))).toBeNull();
  expect(screen.getByText(i18n.t("channel.statusUnavailable"))).toBeVisible();
  await userEvent.setup().click(
    screen.getByRole("button", {
      name: i18n.t("common.refresh"),
      exact: true,
    }),
  );
  expect(await screen.findByText(i18n.t("channel.connected"))).toBeVisible();
  expect(channelApi.listByType).toHaveBeenCalledTimes(1);
  expect(document.activeElement).not.toBe(document.body);
});
test("disabled configuration retains its disabled status despite stale connection status", async () => {
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType).mockResolvedValue([
    { ...instance, enabled: false },
  ]);
  vi.mocked(channelApi.getStatus).mockResolvedValue({
    channel_type: "slack",
    enabled: true,
    connected: true,
  });
  mount();
  expect(await screen.findByText(i18n.t("channel.disabled"))).toBeVisible();
  expect(screen.queryByText(i18n.t("channel.connected"))).toBeNull();
});

test("status retry stays disabled until the pending request completes", async () => {
  let finish!: (value: {
    channel_type: "slack";
    enabled: boolean;
    connected: boolean;
  }) => void;
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType).mockResolvedValue([instance]);
  vi.mocked(channelApi.getStatus)
    .mockRejectedValueOnce(new Error("Unavailable"))
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
  mount();
  await screen.findByRole("alert");
  const retry = screen.getByRole("button", {
    name: i18n.t("common.refresh"),
    exact: true,
  });
  await userEvent.setup().click(retry);
  expect(retry).toBeDisabled();
  await act(async () =>
    finish({ channel_type: "slack", enabled: true, connected: true }),
  );
  expect(await screen.findByText(i18n.t("channel.connected"))).toBeVisible();
  expect(channelApi.getStatus).toHaveBeenCalledTimes(2);
});

test("catalog summary does not describe disabled instances as disconnected", async () => {
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType).mockResolvedValue([
    { ...instance, enabled: false },
  ]);
  vi.mocked(channelApi.getStatus).mockResolvedValue({
    channel_type: "slack",
    enabled: false,
    connected: false,
  });
  mount("/channels");
  expect(await screen.findByText(i18n.t("channel.disabled"))).toBeVisible();
  expect(screen.queryByText(i18n.t("channel.disconnected"))).toBeNull();
});

test("entering a channel after the catalog loads refreshes changes without remounting", async () => {
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType)
    .mockResolvedValueOnce([instance])
    .mockResolvedValue([{ ...instance, enabled: false }]);
  vi.mocked(channelApi.getStatus).mockResolvedValue({
    channel_type: "slack",
    enabled: true,
    connected: true,
  });
  mount("/channels");
  await screen.findByText(i18n.t("channel.connected"));
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Slack", exact: true }));
  expect(await screen.findByText(i18n.t("channel.disabled"))).toBeVisible();
  expect(channelApi.listByType).toHaveBeenCalledTimes(2);
});

test("closing the editor refreshes the list and keeps keyboard focus on a connected surface", async () => {
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType)
    .mockResolvedValueOnce([instance])
    .mockResolvedValue([]);
  vi.mocked(channelApi.getStatus).mockResolvedValue({
    channel_type: "slack",
    enabled: true,
    connected: true,
  });
  mount();
  await userEvent
    .setup()
    .click(
      await screen.findByRole("link", { name: new RegExp(instance.name) }),
    );
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Close editor", exact: true }));
  expect(await screen.findByText(i18n.t("channel.noInstances"))).toBeVisible();
  expect(channelApi.listByType).toHaveBeenCalledTimes(2);
  await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  expect(document.activeElement?.isConnected).toBe(true);
});

test("closing a mobile editor restores focus after the background stops being inert", async () => {
  const originalFocus = HTMLElement.prototype.focus;
  vi.spyOn(HTMLElement.prototype, "focus").mockImplementation(function (
    this: HTMLElement,
    options,
  ) {
    if (!this.closest("[inert]")) originalFocus.call(this, options);
  });
  vi.mocked(channelApi.getTypes).mockResolvedValue([metadata]);
  vi.mocked(channelApi.listByType).mockResolvedValue([]);
  render(
    <div id="simulated-background">
      <MemoryRouter initialEntries={["/channels/slack/fixture"]}>
        <Routes>
          <Route
            path="/channels/:channelType?/:instanceId?"
            element={<ChannelsPage />}
          />
        </Routes>
      </MemoryRouter>
    </div>,
  );
  await userEvent
    .setup()
    .click(
      await screen.findByRole("button", { name: "Close editor", exact: true }),
    );
  await screen.findByText(i18n.t("channel.noInstances"));
  await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  expect(document.activeElement?.isConnected).toBe(true);
  expect(document.activeElement?.closest("[inert]")).toBeNull();
});

test("channel catalog follows the UI language without refetching metadata", async () => {
  await i18n.changeLanguage("en");
  vi.mocked(channelApi.getTypes).mockResolvedValue([
    {
      ...metadata,
      channel_type: "weixin",
      display_name: "WeChat Bot",
      description:
        "Chat with your agent in WeChat via the official iLink bot API",
    },
  ]);
  vi.mocked(channelApi.listByType).mockResolvedValue([]);
  mount("/channels");
  await screen.findByRole("button", { name: "WeChat Bot" });
  try {
    await act(() => i18n.changeLanguage("zh"));
    expect(screen.getByRole("button", { name: "微信机器人" })).toBeVisible();
    expect(
      screen.getByText("通过官方 iLink 机器人接口，在微信中与智能体对话"),
    ).toBeVisible();
    expect(channelApi.getTypes).toHaveBeenCalledTimes(1);
  } finally {
    await act(() => i18n.changeLanguage("en"));
  }
});
