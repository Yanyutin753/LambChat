/** @vitest-environment jsdom */
import type { ComponentProps } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { FeishuPanelForm } from "../FeishuPanelForm";
import { PREDEFINED_EMOJIS } from "../constants";

vi.mock("../../ChannelAgentSelect", () => ({ ChannelAgentSelect: () => null }));
vi.mock("../../ChannelModelSelect", () => ({ ChannelModelSelect: () => <button type="button">Model choice</button> }));
vi.mock("../../ChannelPersonaSelect", () => ({
  ChannelPersonaSelect: () => null,
}));
vi.mock("../../ChannelTeamSelect", () => ({ ChannelTeamSelect: () => null }));
afterEach(cleanup);
test.each(["success", "error", "expired", "cancelled"])(
  "a retained QR image announces the registration terminal state %s",
  (registrationStatus) => {
    render(
      <FeishuPanelForm
        {...props()}
        credentialMode="scan"
        registrationStatus={registrationStatus}
        registrationQrDataUrl="data:image/png;base64,AA=="
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      i18n.t(
        registrationStatus === "success"
          ? "feishu.registrationSuccess"
          : "feishu.registrationFailed",
      ),
    );
  },
);
test("QR preparation announces a localized status and prevents a second registration", () => {
  const p = props();
  render(
    <FeishuPanelForm
      {...p}
      credentialMode="scan"
      isRegistering
      registrationStatus="pending"
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    i18n.t("feishu.waitingForQr"),
  );
  const waiting = screen.getByRole("button", {
    name: i18n.t("feishu.registering"),
  });
  expect(waiting).toBeDisabled();
  fireEvent.click(waiting);
  expect(p.handleStartRegistration).not.toHaveBeenCalled();
});
test("every reaction and the transcription prompt have labels in all five locales", () => {
  for (const lng of ["zh", "en", "ja", "ko", "ru"]) {
    for (const key of [
      "feishu.audioTranscribePrompt",
      ...PREDEFINED_EMOJIS.map((emoji) => emoji.labelKey),
    ]) {
      expect(i18n.exists(key, { lng }), `${lng}: ${key}`).toBe(true);
    }
  }
});

function props(): ComponentProps<typeof FeishuPanelForm> {
  return {
    t: i18n.t.bind(i18n),
    hasExistingConfig: false,
    status: null,
    enabled: false,
    isTesting: false,
    canWrite: true,
    platform: "feishu",
    setPlatform: vi.fn(),
    instanceName: "",
    appId: "",
    appSecret: "",
    encryptKey: "",
    verificationToken: "",
    reactEmoji: PREDEFINED_EMOJIS[0].value,
    customEmoji: "",
    useCustomEmoji: false,
    groupPolicy: "mention",
    streamReply: true,
    autoTranscribeAudio: true,
    audioTranscribePrompt: "",
    agentId: null,
    modelId: null,
    teamId: null,
    personaPresetId: null,
    credentialMode: "manual",
    registrationStatus: "",
    registrationQrUrl: null,
    registrationQrDataUrl: null,
    isRegistering: false,
    setInstanceName: vi.fn(),
    setEnabled: vi.fn(),
    setAppId: vi.fn(),
    setAppSecret: vi.fn(),
    setEncryptKey: vi.fn(),
    setVerificationToken: vi.fn(),
    setReactEmoji: vi.fn(),
    setCustomEmoji: vi.fn(),
    setUseCustomEmoji: vi.fn(),
    setGroupPolicy: vi.fn(),
    setStreamReply: vi.fn(),
    setAutoTranscribeAudio: vi.fn(),
    setAudioTranscribePrompt: vi.fn(),
    onAgentIdChange: vi.fn(),
    setModelId: vi.fn(),
    setTeamId: vi.fn(),
    setPersonaPresetId: vi.fn(),
    setCredentialMode: vi.fn(),
    handleStartRegistration: vi.fn(),
    handleTest: vi.fn(),
  };
}

test("Lark presents manual credentials and the international setup guide without Feishu registration", () => {
  render(<FeishuPanelForm {...props()} platform="lark" credentialMode="scan" />);
  expect(screen.getByLabelText(i18n.t("feishu.appId"), { exact: false })).toBeVisible();
  expect(screen.getByText(i18n.t("feishu.larkManualHint"))).toBeVisible();
  expect(screen.getByText(i18n.t("feishu.larkStep1"))).toBeVisible();
  expect(screen.queryByRole("button", { name: i18n.t("feishu.oneClickRegister") })).toBeNull();
  expect(screen.queryByRole("button", { name: i18n.t("feishu.scanCreate") })).toBeNull();
});

test("Feishu fields have associated labels and enabled switches expose their states", () => {
  const p = props();
  render(<FeishuPanelForm {...p} />);
  for (const key of [
    "instanceName",
    "appId",
    "appSecret",
    "encryptKey",
    "verificationToken",
  ]) {
    expect(
      screen.getByLabelText(i18n.t(`feishu.${key}`), { exact: false }),
    ).toBeInTheDocument();
  }
  expect(
    screen.getByLabelText(i18n.t("feishu.audioTranscribePrompt")),
  ).toBeInTheDocument();
  const enabled = screen.getByRole("switch", {
    name: i18n.t("feishu.enabled"),
  });
  expect(enabled).toHaveAttribute("aria-checked", "false");
  fireEvent.click(enabled);
  expect(p.setEnabled).toHaveBeenCalledWith(true);
  expect(
    screen.getByRole("switch", { name: i18n.t("feishu.streamReply") }),
  ).toHaveAttribute("aria-checked", "true");
});

test("credential mode, reaction and group policy expose selection without changing credentials", () => {
  const p = props();
  render(<FeishuPanelForm {...p} />);
  expect(
    screen.getByRole("button", { name: i18n.t("feishu.manualFill") }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(
    screen.getByRole("button", { name: i18n.t(PREDEFINED_EMOJIS[0].labelKey) }),
  ).toHaveAttribute("aria-pressed", "true");
  const open = screen.getByRole("button", {
    name: i18n.t("feishu.groupPolicyOpen"),
    exact: false,
  });
  expect(open).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(open);
  expect(p.setGroupPolicy).toHaveBeenCalledWith("open");
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("feishu.scanCreate") }),
  );
  expect(p.setCredentialMode).toHaveBeenCalledWith("scan");
  expect(p.setAppSecret).not.toHaveBeenCalled();
  expect(p.handleStartRegistration).not.toHaveBeenCalled();
});

test.each([{ isSaving: true, canWrite: true }, { isSaving: false, canWrite: false }])("run selectors are disabled when saving or read-only: %j", (state) => {
  render(<FeishuPanelForm {...props()} {...state} />);
  expect(screen.getByRole("button", { name: "Model choice" })).toBeDisabled();
});
