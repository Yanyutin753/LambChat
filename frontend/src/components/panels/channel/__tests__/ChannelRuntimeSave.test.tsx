/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { ChannelPanel } from "../../ChannelPanel";
import { FeishuPanel } from "../feishu/FeishuPanel";
import { channelApi } from "../../../../services/api/channel";
import type { ChannelConfigResponse, ChannelMetadata } from "../../../../types/channel";

vi.mock("../../../../hooks/useAuth", () => ({ useAuth: () => ({ hasPermission: () => true }) }));
vi.mock("../../../../hooks/useSandboxStatus", () => ({ useSandboxStatus: () => ({ machines: [], statusError: null }) }));
vi.mock("../../../../services/api/project", () => ({ projectApi: { list: async () => [] } }));
vi.mock("../ChannelAgentSelect", () => ({ ChannelAgentSelect: () => null }));
vi.mock("../ChannelModelSelect", () => ({ ChannelModelSelect: () => null }));
vi.mock("../ChannelPersonaSelect", () => ({ ChannelPersonaSelect: () => null }));
vi.mock("../ChannelTeamSelect", () => ({ ChannelTeamSelect: () => null }));
vi.mock("../../../../services/api/channel", () => ({ channelApi: { get: vi.fn(), getStatus: vi.fn(), update: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const metadata: ChannelMetadata = {
  channel_type: "telegram", display_name: "Telegram", description: "", icon: "", capabilities: ["long_polling", "direct_message"],
  config_schema: {}, requires_webhook: false, requires_websocket: false, setup_guide: [], config_fields: [],
};

for (const channelType of ["telegram", "feishu"] as const) {
  test(`${channelType} loads run settings, saves environment edits and remasks new secrets`, async () => {
    const config: ChannelConfigResponse = { instance_id: "one", channel_type: channelType, name: "Bot", user_id: "owner", enabled: true,
      capabilities: ["direct_message"], config: { app_id: "app" }, agent_id: "agent", model_id: "model", project_id: "project", persona_preset_id: "persona",
      runtime_config: { sandbox: "cloud", enable_thinking: "high", response_language: "ja", env_vars: { TOKEN: "***", REMOVE: "***" } },
    };
    vi.mocked(channelApi.get).mockResolvedValue(config);
    vi.mocked(channelApi.getStatus).mockResolvedValue({ channel_type: channelType, enabled: true, connected: true });
    vi.mocked(channelApi.update).mockResolvedValue({ ...config, runtime_config: { ...config.runtime_config, env_vars: { TOKEN: "***", NEW: "***" } } });
    render(<MemoryRouter>{channelType === "feishu" ? <FeishuPanel instanceId="one" initialConfig={config} />
      : <ChannelPanel channelType="telegram" instanceId="one" metadata={metadata} />}</MemoryRouter>);
    const env = await screen.findByLabelText(i18n.t("channel.runtime.env"));
    expect(env).toHaveValue("TOKEN=***\nREMOVE=***");
    expect(screen.getByLabelText(i18n.t("channel.runtime.thinking"))).toHaveValue("high");
    fireEvent.change(env, { target: { value: "TOKEN=***\nNEW= x=y " } });
    fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
    await waitFor(() => expect(channelApi.update).toHaveBeenCalled());
    const body = vi.mocked(channelApi.update).mock.calls[0][2];
    expect(body).toMatchObject({ project_id: "project", model_id: "model", persona_preset_id: "persona",
      runtime_config: { sandbox: "cloud", enable_thinking: "high", response_language: "ja", env_vars: { TOKEN: "***", NEW: " x=y " } },
    });
    expect(body.runtime_config?.env_vars).not.toHaveProperty("REMOVE");
    await waitFor(() => expect(env).toHaveValue("TOKEN=***\nNEW=***"));
  });
}

test("notification-only channels do not expose or write run configuration", async () => {
  vi.mocked(channelApi.get).mockResolvedValue({ instance_id: "one", channel_type: "bark", name: "Push", user_id: "owner", enabled: true, config: {}, capabilities: ["send_message"] });
  vi.mocked(channelApi.getStatus).mockResolvedValue({ channel_type: "bark", enabled: true, connected: true });
  vi.mocked(channelApi.update).mockResolvedValue({ instance_id: "one", channel_type: "bark", name: "Push", user_id: "owner", enabled: true, config: {}, capabilities: ["send_message"] });
  render(<MemoryRouter><ChannelPanel channelType="bark" instanceId="one" metadata={{ ...metadata, channel_type: "bark", capabilities: ["send_message"] }} /></MemoryRouter>);
  await screen.findByText("Push");
  expect(screen.queryByLabelText(i18n.t("channel.runtime.env"))).toBeNull();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") })); });
  expect(vi.mocked(channelApi.update).mock.calls[0][2]).not.toHaveProperty("runtime_config");
});

for (const channelType of ["telegram", "feishu"] as const) {
  test(`${channelType} rejects invalid environment drafts and explicitly clears project and all run overrides`, async () => {
    const config: ChannelConfigResponse = { instance_id: "one", channel_type: channelType, name: "Bot", user_id: "owner", enabled: true,
      capabilities: ["direct_message"], config: { app_id: "app" }, project_id: "project",
      runtime_config: { sandbox: "cloud", enable_thinking: "high", enable_code_interpreter: true, env_vars: { TOKEN: "***" } },
    };
    vi.mocked(channelApi.get).mockResolvedValue(config);
    vi.mocked(channelApi.getStatus).mockResolvedValue({ channel_type: channelType, enabled: true, connected: true });
    vi.mocked(channelApi.update).mockResolvedValue({ ...config, project_id: null, runtime_config: { env_vars: {} } });
    render(<MemoryRouter>{channelType === "feishu" ? <FeishuPanel instanceId="one" initialConfig={config} />
      : <ChannelPanel channelType="telegram" instanceId="one" metadata={metadata} />}</MemoryRouter>);
    const env = await screen.findByLabelText(i18n.t("channel.runtime.env"));
    fireEvent.change(env, { target: { value: "INVALID KEY=secret" } });
    fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("channel.runtime.envInvalid"));
    expect(channelApi.update).not.toHaveBeenCalled();
    expect(env).toHaveValue("INVALID KEY=secret");
    fireEvent.click(screen.getByRole("button", { name: i18n.t("channel.runtime.reset") }));
    const project = screen.getByLabelText(i18n.t("channel.runtime.project"));
    await waitFor(() => expect(project).not.toBeDisabled());
    fireEvent.change(project, { target: { value: "" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") })); });
    expect(vi.mocked(channelApi.update).mock.calls[0][2]).toMatchObject({ project_id: null, runtime_config: {
      sandbox: "default", sandbox_machine_id: "", enable_thinking: "", enable_code_interpreter: null, response_language: "", env_vars: {},
    } });
  });
}
