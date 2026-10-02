/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { FeishuPanel } from "../FeishuPanel";
import { channelApi } from "../../../../../services/api/channel";
import type { ChannelConfigResponse } from "../../../../../types/channel";

vi.mock("../../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../ChannelAgentSelect", () => ({ ChannelAgentSelect: () => null }));
vi.mock("../../ChannelModelSelect", () => ({ ChannelModelSelect: () => null }));
vi.mock("../../ChannelPersonaSelect", () => ({
  ChannelPersonaSelect: () => null,
}));
vi.mock("../../ChannelTeamSelect", () => ({ ChannelTeamSelect: () => null }));
vi.mock("../../../../../services/api/channel", () => ({
  channelApi: { update: vi.fn(), getStatus: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test("Feishu keeps a rejected draft and permits retry without replacing an empty existing secret", async () => {
  const user = userEvent.setup();
  const config: ChannelConfigResponse = {
    instance_id: "fixture",
    channel_type: "feishu",
    name: "Local fixture",
    user_id: "fixture",
    enabled: true,
    capabilities: [],
    config: { app_id: "cli_fixture" },
  };
  vi.mocked(channelApi.update)
    .mockRejectedValueOnce(new Error("Save unavailable"))
    .mockResolvedValueOnce(config);
  vi.mocked(channelApi.getStatus).mockResolvedValue({
    channel_type: "feishu",
    enabled: true,
    connected: true,
  });
  render(
    <MemoryRouter>
      <FeishuPanel instanceId="fixture" initialConfig={config} />
    </MemoryRouter>,
  );
  const appId = await screen.findByLabelText(i18n.t("feishu.appId"), {
    exact: false,
  });
  expect(
    screen.getByLabelText(i18n.t("feishu.appSecret"), { exact: true }),
  ).toHaveAccessibleDescription(i18n.t("feishu.leaveEmpty"));
  await user.clear(appId);
  await user.type(appId, "cli_local_draft");
  await user.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Save unavailable",
  );
  expect(appId).toHaveValue("cli_local_draft");
  expect(
    vi.mocked(channelApi.update).mock.calls[0][2].config,
  ).not.toHaveProperty("app_secret");
  await user.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(channelApi.update).toHaveBeenCalledTimes(2);
});
