/** @vitest-environment jsdom */
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import toast from "react-hot-toast";
import userEvent from "@testing-library/user-event";
import i18n from "../../../../i18n";
import { ChannelPanel } from "../../ChannelPanel";
import { FeishuPanel } from "../feishu/FeishuPanel";
import { channelApi } from "../../../../services/api/channel";
import type { ChannelMetadata, ChannelType } from "../../../../types/channel";

vi.mock("../../../../services/api/project", () => ({ projectApi: { list: async () => [] } }));

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../ChannelAgentSelect", () => ({ ChannelAgentSelect: () => null }));
vi.mock("../ChannelModelSelect", () => ({ ChannelModelSelect: () => null }));
vi.mock("../ChannelPersonaSelect", () => ({
  ChannelPersonaSelect: () => null,
}));
vi.mock("../ChannelTeamSelect", () => ({ ChannelTeamSelect: () => null }));
vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("../../../../services/api/channel", () => ({
  channelApi: {
    get: vi.fn(),
    getStatus: vi.fn(),
    update: vi.fn(),
    test: vi.fn(),
    create: vi.fn(),
    startFeishuRegistration: vi.fn(),
    getFeishuRegistration: vi.fn(),
    cancelFeishuRegistration: vi.fn().mockResolvedValue({ cancelled: true }),
  },
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
});

const metadata: ChannelMetadata = {
  channel_type: "slack",
  display_name: "Slack",
  description: "",
  icon: "",
  capabilities: [],
  config_schema: {},
  requires_webhook: false,
  requires_websocket: false,
  setup_guide: [],
  config_fields: [{ name: "workspace", title: "Workspace", type: "text" }],
};
const config = (channelType: ChannelType) => ({
  instance_id: "fixture",
  channel_type: channelType,
  user_id: "fixture",
  name: "Existing channel",
  enabled: true,
  capabilities: [],
  config: { workspace: "Existing workspace", app_id: "cli_existing" },
});
function mount(type: "slack" | "feishu") {
  return render(
    <MemoryRouter>
      {type === "feishu" ? (
        <FeishuPanel instanceId="fixture" />
      ) : (
        <ChannelPanel
          channelType="slack"
          instanceId="fixture"
          metadata={metadata}
        />
      )}
    </MemoryRouter>,
  );
}
test.each(["slack", "feishu"] as const)(
  "%s retry keeps keyboard focus on a stable surface while loading",
  async (type) => {
    let finish!: (value: ReturnType<typeof config>) => void;
    vi.mocked(channelApi.get)
      .mockRejectedValueOnce(new Error("Unavailable"))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      );
    vi.mocked(channelApi.getStatus).mockResolvedValue({
      channel_type: type,
      enabled: true,
      connected: true,
    });
    mount(type);
    await screen.findByRole("alert");
    await userEvent.setup().click(
      screen.getByRole("button", {
        name: i18n.t("common.retry"),
        exact: true,
      }),
    );
    const focused = document.activeElement;
    expect(focused).not.toBe(document.body);
    expect(focused?.isConnected).toBe(true);
    await act(async () => finish(config(type)));
    expect(document.activeElement).toBe(focused);
  },
);
test.each(["slack", "feishu"] as const)(
  "%s ignores a previous instance status refresh failure",
  async (type) => {
    let fail!: (error: Error) => void;
    vi.mocked(channelApi.get).mockResolvedValue(config(type));
    vi.mocked(channelApi.getStatus)
      .mockResolvedValueOnce({
        channel_type: type,
        enabled: true,
        connected: true,
      })
      .mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            fail = reject;
          }),
      )
      .mockResolvedValue({
        channel_type: type,
        enabled: true,
        connected: false,
      });
    vi.mocked(channelApi.update).mockResolvedValue(config(type));
    const view = mount(type);
    fireEvent.click(
      await screen.findByRole("button", {
        name: i18n.t("common.save"),
        exact: true,
      }),
    );
    await waitFor(() => expect(channelApi.getStatus).toHaveBeenCalledTimes(2));
    view.rerender(
      <MemoryRouter>
        {type === "feishu" ? (
          <FeishuPanel instanceId="second" />
        ) : (
          <ChannelPanel
            channelType="slack"
            instanceId="second"
            metadata={metadata}
          />
        )}
      </MemoryRouter>,
    );
    await screen.findByText(
      i18n.t(
        type === "feishu" ? "feishu.disconnected" : "channel.disconnected",
      ),
    );
    await act(async () => fail(new Error("Old status unavailable")));
    expect(screen.queryByRole("alert")).toBeNull();
  },
);
test("a late rejected poll does not replace completed registration with failure", async () => {
  let fail!: (error: Error) => void;
  let finish!: (value: {
    session_id: string;
    status: string;
    app_id: string;
    app_secret: string;
  }) => void;
  vi.mocked(channelApi.startFeishuRegistration).mockResolvedValue({
    session_id: "local-fixture",
    status: "pending",
  });
  vi.mocked(channelApi.getFeishuRegistration)
    .mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          fail = reject;
        }),
    )
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
  vi.mocked(channelApi.cancelFeishuRegistration).mockResolvedValue({
    cancelled: true,
  });
  render(
    <MemoryRouter>
      <FeishuPanel instanceId="new" />
    </MemoryRouter>,
  );
  vi.useFakeTimers();
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", {
        name: i18n.t("feishu.oneClickRegister"),
        exact: true,
      }),
    );
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(4000);
  });
  await act(async () =>
    finish({
      session_id: "local-fixture",
      status: "success",
      app_id: "cli_fixture",
      app_secret: "test-only",
    }),
  );
  await act(async () => fail(new Error("Late poll failed")));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(toast.success).toHaveBeenCalledWith(
    i18n.t("feishu.registrationSuccess"),
  );
});
test("registration startup failure persists without a QR image and enables retry", async () => {
  vi.mocked(channelApi.startFeishuRegistration).mockRejectedValue(
    new Error("Registration unavailable"),
  );
  render(
    <MemoryRouter>
      <FeishuPanel instanceId="new" />
    </MemoryRouter>,
  );
  const register = await screen.findByRole("button", {
    name: i18n.t("feishu.oneClickRegister"),
    exact: true,
  });
  fireEvent.click(register);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("feishu.registrationFailed"),
  );
  expect(register).toBeEnabled();
  expect(screen.queryByRole("status")).toBeNull();
});
test("a registration polling failure persists and stops the waiting state", async () => {
  vi.mocked(channelApi.startFeishuRegistration).mockResolvedValue({
    session_id: "local-fixture",
    status: "pending",
  });
  vi.mocked(channelApi.getFeishuRegistration).mockRejectedValue(
    new Error("Polling unavailable"),
  );
  vi.mocked(channelApi.cancelFeishuRegistration).mockResolvedValue({
    cancelled: true,
  });
  render(
    <MemoryRouter>
      <FeishuPanel instanceId="new" />
    </MemoryRouter>,
  );
  vi.useFakeTimers();
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", {
        name: i18n.t("feishu.oneClickRegister"),
        exact: true,
      }),
    );
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(screen.getByRole("alert")).toHaveTextContent(
    i18n.t("feishu.registrationFailed"),
  );
  expect(screen.queryByRole("status")).toBeNull();
  expect(
    screen.getByRole("button", {
      name: i18n.t("feishu.oneClickRegister"),
      exact: true,
    }),
  ).toBeEnabled();
});
test.each(["slack", "feishu"] as const)(
  "%s ignores a previous instance load after switching instances",
  async (type) => {
    let finish!: (value: ReturnType<typeof config>) => void;
    vi.mocked(channelApi.get).mockImplementation((_, id) =>
      id === "fixture"
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : Promise.resolve({
            ...config(type),
            instance_id: "second",
            config: { workspace: "Second workspace", app_id: "cli_second" },
          }),
    );
    vi.mocked(channelApi.getStatus).mockResolvedValue({
      channel_type: type,
      enabled: true,
      connected: true,
    });
    const view = mount(type);
    view.rerender(
      <MemoryRouter>
        {type === "feishu" ? (
          <FeishuPanel instanceId="second" />
        ) : (
          <ChannelPanel
            channelType="slack"
            instanceId="second"
            metadata={metadata}
          />
        )}
      </MemoryRouter>,
    );
    const field = await screen.findByDisplayValue(
      type === "feishu" ? "cli_second" : "Second workspace",
    );
    await act(async () => finish(config(type)));
    expect(field).toHaveValue(
      type === "feishu" ? "cli_second" : "Second workspace",
    );
  },
);
test.each(["slack", "feishu"] as const)(
  "%s load failure blocks writes and restores the existing configuration on retry",
  async (type) => {
    vi.mocked(channelApi.get)
      .mockRejectedValueOnce(new Error("Unavailable"))
      .mockResolvedValueOnce(config(type));
    vi.mocked(channelApi.getStatus).mockResolvedValue({
      channel_type: type,
      enabled: true,
      connected: true,
    });
    mount(type);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      i18n.t(type === "feishu" ? "feishu.loadError" : "channel.loadError"),
    );
    expect(
      screen.queryByRole("button", {
        name: i18n.t("common.save"),
        exact: true,
      }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", {
        name: i18n.t("common.delete"),
        exact: true,
      }),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.retry"), exact: true }),
    );
    const field = await screen.findByLabelText(
      type === "feishu" ? i18n.t("feishu.appId") : "Workspace",
      { exact: false },
    );
    expect(field).toHaveValue(
      type === "feishu" ? "cli_existing" : "Existing workspace",
    );
    expect(channelApi.create).not.toHaveBeenCalled();
  },
);
test.each(["slack", "feishu"] as const)(
  "%s testing failure remains visible and permits another attempt",
  async (type) => {
    vi.mocked(channelApi.get).mockResolvedValue(config(type));
    vi.mocked(channelApi.getStatus).mockResolvedValue({
      channel_type: type,
      enabled: true,
      connected: true,
    });
    vi.mocked(channelApi.test)
      .mockResolvedValueOnce({ success: false, message: "Connection rejected" })
      .mockResolvedValueOnce({ success: true, message: "Connected" });
    mount(type);
    const testButton = await screen.findByRole("button", {
      name: i18n.t(
        type === "feishu" ? "feishu.testConnection" : "channel.testConnection",
      ),
      exact: true,
    });
    fireEvent.click(testButton);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Connection rejected",
    );
    expect(testButton).toBeEnabled();
    fireEvent.click(testButton);
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(toast.success).toHaveBeenCalledWith("Connected");
  },
);
test.each(["slack", "feishu"] as const)(
  "%s status refresh failure does not report a successful save as failed",
  async (type) => {
    vi.mocked(channelApi.get).mockResolvedValue(config(type));
    vi.mocked(channelApi.getStatus)
      .mockResolvedValueOnce({
        channel_type: type,
        enabled: true,
        connected: true,
      })
      .mockRejectedValueOnce(new Error("Status unavailable"))
      .mockResolvedValueOnce({
        channel_type: type,
        enabled: true,
        connected: true,
      });
    vi.mocked(channelApi.update).mockResolvedValue(config(type));
    mount(type);
    const save = await screen.findByRole("button", {
      name: i18n.t("common.save"),
      exact: true,
    });
    fireEvent.click(save);
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      i18n.t("common.loadFailed"),
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "Status unavailable",
    );
    expect(channelApi.update).toHaveBeenCalledTimes(1);
    await userEvent
      .setup()
      .click(
        screen.getByRole("button", {
          name: i18n.t("common.retry"),
          exact: true,
        }),
      );
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement?.isConnected).toBe(true);
    expect(channelApi.update).toHaveBeenCalledTimes(1);
  },
);
