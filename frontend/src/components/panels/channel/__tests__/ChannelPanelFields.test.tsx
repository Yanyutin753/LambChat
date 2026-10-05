/** @vitest-environment jsdom */
import {
  cleanup,
  render,
  screen,
  fireEvent,
  act,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { ChannelPanel } from "../../ChannelPanel";
import { channelApi } from "../../../../services/api/channel";
import type {
  ChannelMetadata,
  ChannelConfigResponse,
} from "../../../../types/channel";

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../ChannelAgentSelect", () => ({ ChannelAgentSelect: () => null }));
vi.mock("../../../../services/api/channel", () => ({
  channelApi: {
    create: vi.fn().mockRejectedValue(new Error("Save unavailable")),
    get: vi.fn(),
    getStatus: vi.fn(),
    update: vi.fn(),
  },
}));
afterEach(cleanup);
test("updating an existing channel omits an unchanged empty sensitive field", async () => {
  const config: ChannelConfigResponse = {
    instance_id: "fixture",
    channel_type: "slack",
    name: "Local fixture",
    user_id: "fixture",
    enabled: true,
    capabilities: [],
    config: { workspace: "Example", token: "" },
  };
  vi.mocked(channelApi.get).mockResolvedValue(config);
  vi.mocked(channelApi.getStatus).mockResolvedValue({
    channel_type: "slack",
    enabled: true,
    connected: true,
  });
  vi.mocked(channelApi.update).mockResolvedValue(config);
  render(
    <MemoryRouter>
      <ChannelPanel
        channelType="slack"
        instanceId="fixture"
        metadata={metadata}
      />
    </MemoryRouter>,
  );
  await screen.findByLabelText("Workspace", { exact: false });
  expect(
    screen.getByLabelText("Bot token", { exact: true }),
  ).toHaveAccessibleDescription(i18n.t("channel.leaveEmpty"));
  expect(screen.getByRole("switch", { name: "Streaming" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  expect(channelApi.update).toHaveBeenCalledWith(
    "slack",
    "fixture",
    expect.objectContaining({
      config: expect.objectContaining({ workspace: "Example" }),
    }),
  );
  expect(
    vi.mocked(channelApi.update).mock.calls[0][2].config,
  ).not.toHaveProperty("token");
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
  config_fields: [
    { name: "workspace", type: "text", title: "Workspace", required: true },
    { name: "token", type: "password", title: "Bot token", sensitive: true },
    {
      name: "mode",
      type: "select",
      title: "Reply mode",
      options: [{ value: "thread", label: "Thread" }],
    },
    { name: "stream", type: "toggle", title: "Streaming", default: true },
  ],
};
test("dynamic channel fields and switches expose names and preserve drafts after a rejected save", async () => {
  render(
    <MemoryRouter>
      <ChannelPanel channelType="slack" instanceId="new" metadata={metadata} />
    </MemoryRouter>,
  );
  const name = await screen.findByLabelText(i18n.t("channel.instanceName"), {
    exact: false,
  });
  fireEvent.change(name, { target: { value: "Local draft" } });
  const workspace = screen.getByLabelText("Workspace", { exact: false });
  fireEvent.change(workspace, { target: { value: "Example workspace" } });
  expect(screen.getByLabelText("Bot token")).toHaveAttribute(
    "type",
    "password",
  );
  expect(
    screen.getByRole("button", { name: "Reply mode" }),
  ).toBeInTheDocument();
  const stream = screen.getByRole("switch", { name: "Streaming" });
  expect(stream).toHaveAttribute("aria-checked", "true");
  fireEvent.click(stream);
  expect(stream).toHaveAttribute("aria-checked", "false");
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Save unavailable",
  );
  expect(workspace).toHaveValue("Example workspace");
  expect(channelApi.create).toHaveBeenCalledWith(
    expect.objectContaining({
      config: expect.objectContaining({
        workspace: "Example workspace",
        stream: false,
      }),
    }),
  );
});

test("switching language translates config and validation while preserving secret drafts", async () => {
  await i18n.changeLanguage("en");
  render(
    <MemoryRouter>
      <ChannelPanel
        channelType="dingtalk"
        instanceId="new"
        metadata={{
          ...metadata,
          channel_type: "dingtalk",
          display_name: "DingTalk",
          setup_guide: [
            "Open the target DingTalk group chat settings and choose Robots",
          ],
          config_fields: [
            {
              name: "webhook_url",
              title: "Webhook URL",
              type: "text",
              required: true,
            },
            {
              name: "secret",
              title: "Signing Secret",
              type: "password",
              sensitive: true,
            },
          ],
        }}
      />
    </MemoryRouter>,
  );
  fireEvent.change(await screen.findByLabelText("Signing Secret"), {
    target: { value: "SEC-draft" },
  });
  try {
    await act(() => i18n.changeLanguage("zh"));
    expect(screen.getByLabelText("加签密钥")).toHaveValue("SEC-draft");
    expect(
      screen.getByText("打开目标钉钉群设置，选择「机器人」"),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.save") }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Webhook 地址");
    expect(screen.getByRole("alert").textContent).not.toContain("{{");
  } finally {
    await act(() => i18n.changeLanguage("en"));
  }
});
