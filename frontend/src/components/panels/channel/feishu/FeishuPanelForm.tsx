import { useId, type ReactNode } from "react";
import { Button } from "../../../common";
import { ToggleSwitch } from "../../AgentPanel/shared";
import {
  Check,
  Unplug,
  RefreshCw,
  Sparkles,
  QrCode,
  ExternalLink,
} from "lucide-react";
import type { TFunction } from "i18next";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ImageWithSkeleton } from "../../../chat/ChatMessage/ImageWithSkeleton";
import { ChannelAgentSelect } from "../ChannelAgentSelect";
import { ChannelModelSelect } from "../ChannelModelSelect";
import { ChannelPersonaSelect } from "../ChannelPersonaSelect";
import { ChannelTeamSelect } from "../ChannelTeamSelect";
import {
  DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
  PREDEFINED_EMOJIS,
} from "./constants";
import type { FeishuConfigStatus } from "./types";

interface FeishuPanelFormProps {
  t: TFunction;
  runConfiguration?: ReactNode;
  hasExistingConfig: boolean;
  status: FeishuConfigStatus | null;
  enabled: boolean;
  isTesting: boolean;
  isSaving?: boolean;
  canWrite: boolean;
  instanceName: string;
  platform: "feishu" | "lark";
  setPlatform: (value: "feishu" | "lark") => void;
  secretRequired?: boolean;
  appId: string;
  appSecret: string;
  encryptKey: string;
  verificationToken: string;
  reactEmoji: string;
  customEmoji: string;
  useCustomEmoji: boolean;
  groupPolicy: "open" | "mention";
  streamReply: boolean;
  autoTranscribeAudio: boolean;
  audioTranscribePrompt: string;
  agentId: string | null;
  modelId: string | null;
  teamId: string | null;
  personaPresetId: string | null;
  credentialMode: "scan" | "manual";
  registrationStatus: string;
  registrationQrUrl: string | null;
  registrationQrDataUrl: string | null;
  isRegistering: boolean;
  setInstanceName: (value: string) => void;
  setEnabled: (value: boolean) => void;
  setAppId: (value: string) => void;
  setAppSecret: (value: string) => void;
  setEncryptKey: (value: string) => void;
  setVerificationToken: (value: string) => void;
  setReactEmoji: (value: string) => void;
  setCustomEmoji: (value: string) => void;
  setUseCustomEmoji: (value: boolean) => void;
  setGroupPolicy: (value: "open" | "mention") => void;
  setStreamReply: (value: boolean) => void;
  setAutoTranscribeAudio: (value: boolean) => void;
  setAudioTranscribePrompt: (value: string) => void;
  onAgentIdChange: (value: string | null) => void;
  setModelId: (value: string | null) => void;
  setTeamId: (value: string | null) => void;
  setPersonaPresetId: (value: string | null) => void;
  setCredentialMode: (value: "scan" | "manual") => void;
  handleStartRegistration: () => void;
  handleTest: () => void;
}

export function FeishuPanelForm({
  t,
  runConfiguration,
  hasExistingConfig,
  status,
  enabled,
  isTesting,
  isSaving = false,
  canWrite,
  instanceName,
  platform,
  setPlatform,
  secretRequired = !hasExistingConfig,
  appId,
  appSecret,
  encryptKey,
  verificationToken,
  reactEmoji,
  customEmoji,
  useCustomEmoji,
  groupPolicy,
  streamReply,
  autoTranscribeAudio,
  audioTranscribePrompt,
  agentId,
  modelId,
  teamId,
  personaPresetId,
  credentialMode,
  registrationStatus,
  registrationQrUrl,
  registrationQrDataUrl,
  isRegistering,
  setInstanceName,
  setEnabled,
  setAppId,
  setAppSecret,
  setEncryptKey,
  setVerificationToken,
  setReactEmoji,
  setCustomEmoji,
  setUseCustomEmoji,
  setGroupPolicy,
  setStreamReply,
  setAutoTranscribeAudio,
  setAudioTranscribePrompt,
  onAgentIdChange,
  setModelId,
  setTeamId,
  setPersonaPresetId,
  setCredentialMode,
  handleStartRegistration,
  handleTest,
}: FeishuPanelFormProps) {
  const formId = useId();
  const activeCredentialMode = platform === "lark" ? "manual" : credentialMode;
  return (
    <div className="es-form">
      {/* Status Callout */}
      {hasExistingConfig && status && (
        <div
          className={`es-callout ${
            status.connected ? "es-callout--success" : "es-callout--danger"
          }`}
        >
          <div className="es-callout-icon">
            {status.connected ? <Check size={14} /> : <Unplug size={14} />}
          </div>
          <div className="es-callout-body">
            <div className="es-callout-title">
              <span
                className={`es-status-dot ${
                  status.connected ? "" : "opacity-40"
                }`}
              />
              {status.connected
                ? t("feishu.connected", "Connected")
                : t("feishu.disconnected", "Disconnected")}
            </div>
            {status.error_message && (
              <div className="es-callout-desc [overflow-wrap:anywhere]">
                {status.error_message}
              </div>
            )}
          </div>
          <Button
            onClick={handleTest}
            disabled={isTesting || !enabled}
            loading={isTesting}
            leftIcon={<RefreshCw size={14} />}
            size="sm"
            className="ml-auto shrink-0"
          >
            {t("feishu.testConnection")}
          </Button>
        </div>
      )}

      {/* Instance Name */}
      {!hasExistingConfig && (
        <div className="es-field">
          <label htmlFor={`${formId}-instanceName`} className="es-label">
            {t("feishu.instanceName", "Instance Name")}
            <span className="es-required">*</span>
          </label>
          <input
            id={`${formId}-instanceName`}
            type="text"
            value={instanceName}
            onChange={(e) => setInstanceName(e.target.value)}
            placeholder={t("feishu.instanceNamePlaceholder", "My Feishu Bot")}
            className="glass-input es-input"
          />
        </div>
      )}

      {/* Enable Toggle */}
      <div className="es-section">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-14 font-medium text-[var(--theme-text)]">
              {t("feishu.enabled", "Enable Feishu Bot")}
            </div>
            <p className="es-hint mt-0.5">
              {t("feishu.enabledDesc", "Enable or disable this channel")}
            </p>
          </div>
          <ToggleSwitch
            enabled={enabled}
            onToggle={() => setEnabled(!enabled)}
            ariaLabel={t("feishu.enabled")}
          />
        </div>
      </div>

      {/* App Credentials */}
      <div className="es-section">
        <div className="es-section-title">
          {t("feishu.credentials", "App Credentials")}
        </div>

        <div className="es-field">
          <label htmlFor={`${formId}-platform`} className="es-label">
            {t("feishu.platform")}
          </label>
          <select
            id={`${formId}-platform`}
            value={platform}
            disabled={!canWrite || isRegistering}
            onChange={(event) => setPlatform(event.target.value as "feishu" | "lark")}
            className="glass-input es-input"
          >
            <option value="feishu">{t("feishu.platformFeishu")}</option>
            <option value="lark">{t("feishu.platformLark")}</option>
          </select>
          {platform === "lark" && <p className="es-hint">{t("feishu.larkManualHint")}</p>}
        </div>

        {platform === "feishu" && <div className="mb-4 grid grid-cols-2 rounded-lg border border-[var(--theme-border)] bg-[var(--glass-bg-subtle)] p-1">
          {(["scan", "manual"] as const).map((mode) => (
            <Button
              key={mode}
              variant={activeCredentialMode === mode ? "secondary" : "ghost"}
              aria-pressed={activeCredentialMode === mode}
              className="feishu-mode-button"
              onClick={() => setCredentialMode(mode)}
            >
              {t(mode === "scan" ? "feishu.scanCreate" : "feishu.manualFill")}
            </Button>
          ))}
        </div>}

        {activeCredentialMode === "scan" && (
          <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-6 text-center">
            <p className="mx-auto max-w-[28rem] text-14 text-[var(--theme-text-secondary)]">
              {t(
                "feishu.scanCreateDesc",
                "Use the Feishu app to scan and create a bot. The current App ID and App Secret will be overwritten.",
              )}
            </p>

            <Button
              variant="primary"
              onClick={handleStartRegistration}
              disabled={isRegistering || !canWrite}
              loading={isRegistering}
              leftIcon={<QrCode size={16} />}
              className="feishu-mode-button mx-auto mt-4 max-w-full"
            >
              {isRegistering
                ? t("feishu.registering", "Waiting for scan")
                : t("feishu.oneClickRegister", "Create Feishu App")}
            </Button>

            {(registrationQrDataUrl || isRegistering) && (
              <div className="mt-5 flex flex-col items-center">
                <div className="flex w-[224px] max-w-full aspect-square items-center justify-center rounded-xl border border-[var(--theme-border)] bg-white p-3 shadow-sm">
                  {registrationQrDataUrl ? (
                    <ImageWithSkeleton
                      src={registrationQrDataUrl}
                      alt={t("feishu.scanWithFeishu", "Scan with Feishu")}
                      skipUrlResolve
                      inline
                      className="size-full"
                    />
                  ) : (
                    <LoadingSpinner size="md" />
                  )}
                </div>
                <div
                  role="status"
                  className="mt-3 text-14 font-medium text-[var(--theme-primary)]"
                >
                  {t(
                    `feishu.${
                      isRegistering
                        ? registrationQrDataUrl
                          ? "waitingForScan"
                          : "waitingForQr"
                        : registrationStatus === "success"
                          ? "registrationSuccess"
                          : "registrationFailed"
                    }`,
                  )}
                </div>
                <div className="mt-2 text-12 text-[var(--theme-text-secondary)]">
                  {t(
                    "feishu.qrExpiresHint",
                    "QR code is valid for 10 minutes and can be scanned once.",
                  )}
                </div>
                {registrationQrUrl && (
                  <a
                    href={registrationQrUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex min-h-11 items-center gap-1 text-12 text-[var(--theme-primary)] focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
                  >
                    <ExternalLink size={12} />
                    {t("feishu.openRegistration", "Open in browser")}
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        {activeCredentialMode === "manual" && (
          <>
            <div className="es-field">
              <label htmlFor={`${formId}-appId`} className="es-label">
                {t("feishu.appId", "App ID")}
                <span className="es-required">*</span>
              </label>
              <input
                id={`${formId}-appId`}
                type="text"
                value={appId}
                onChange={(e) => setAppId(e.target.value)}
                placeholder={t("feishu.appIdPlaceholder", "cli_xxxxxxxxxx")}
                className="glass-input es-input"
              />
            </div>
            <div className="es-field">
              <label htmlFor={`${formId}-appSecret`} className="es-label">
                {t("feishu.appSecret", "App Secret")}
                {secretRequired && <span className="es-required">*</span>}
              </label>
              <input
                id={`${formId}-appSecret`}
                type="password"
                aria-describedby={
                  !secretRequired ? `${formId}-secret-hint` : undefined
                }
                value={appSecret}
                onChange={(e) => setAppSecret(e.target.value)}
                placeholder={
                  !secretRequired
                    ? t("feishu.passwordMask", "••••••••••••")
                    : ""
                }
                className="glass-input es-input"
              />
              {!secretRequired && (
                <p id={`${formId}-secret-hint`} className="es-hint">
                  {t("feishu.leaveEmpty")}
                </p>
              )}
            </div>
          </>
        )}

        {activeCredentialMode === "scan" && appId && (
          <div className="mt-4 rounded-lg border border-[var(--theme-border)] bg-[var(--glass-bg-subtle)] px-3 py-2">
            <div className="text-12 font-medium text-[var(--theme-text-secondary)]">
              {t("feishu.currentCredential", "Current credential")}
            </div>
            <div className="mt-1 truncate text-14 text-[var(--theme-text)]">
              {appId}
            </div>
          </div>
        )}
      </div>

      {/* Security Settings */}
      <div className="es-section">
        <div className="es-section-title">
          {t("feishu.security", "Security Settings")}
          <span className="ml-1 normal-case tracking-normal opacity-60">
            {t("feishu.optional")}
          </span>
        </div>
        <div className="es-field">
          <label htmlFor={`${formId}-encryptKey`} className="es-label">
            {t("feishu.encryptKey", "Encrypt Key")}
          </label>
          <input
            id={`${formId}-encryptKey`}
            type="text"
            value={encryptKey}
            onChange={(e) => setEncryptKey(e.target.value)}
            className="glass-input es-input"
          />
        </div>
        <div className="es-field">
          <label htmlFor={`${formId}-verificationToken`} className="es-label">
            {t("feishu.verificationToken", "Verification Token")}
          </label>
          <input
            id={`${formId}-verificationToken`}
            type="text"
            value={verificationToken}
            onChange={(e) => setVerificationToken(e.target.value)}
            className="glass-input es-input"
          />
        </div>
      </div>

      {/* Behavior Settings */}
      <div className="es-section">
        <div className="es-section-title">
          {t("feishu.behavior", "Behavior Settings")}
        </div>

        {/* React Emoji */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3">
            <label
              htmlFor={useCustomEmoji ? `${formId}-customEmoji` : undefined}
              id={`${formId}-reaction-label`}
              className="es-label"
            >
              {t("feishu.reactEmoji", "Reaction Emoji")}
            </label>
            <Button
              size="sm"
              variant={useCustomEmoji ? "secondary" : "ghost"}
              aria-pressed={useCustomEmoji}
              onClick={() => setUseCustomEmoji(!useCustomEmoji)}
              leftIcon={<Sparkles size={12} />}
            >
              {useCustomEmoji ? t("feishu.preset") : t("feishu.custom")}
            </Button>
          </div>

          {useCustomEmoji ? (
            <>
              <input
                type="text"
                id={`${formId}-customEmoji`}
                value={customEmoji}
                onChange={(e) => setCustomEmoji(e.target.value)}
                placeholder={t(
                  "feishu.customEmojiPlaceholder",
                  "Enter emoji or text (e.g., 🎯 or DONE)",
                )}
                className="glass-input es-input"
              />
              <p className="es-hint">
                {t(
                  "feishu.customEmojiHint",
                  "Enter an emoji character or a Feishu emoji type code",
                )}
              </p>
            </>
          ) : (
            <div className="max-h-[260px] overflow-y-auto rounded-lg border border-[var(--theme-border)] bg-[var(--glass-bg-subtle)] p-2 scrollbar-thin">
              <div
                role="group"
                aria-labelledby={`${formId}-reaction-label`}
                className="feishu-emoji-grid"
              >
                {PREDEFINED_EMOJIS.map((emoji) => {
                  const isSelected = reactEmoji === emoji.value;
                  return (
                    <Button
                      key={emoji.value}
                      size="lg"
                      variant={isSelected ? "secondary" : "ghost"}
                      onClick={() => setReactEmoji(emoji.value)}
                      title={t(emoji.labelKey)}
                      aria-label={t(emoji.labelKey)}
                      aria-pressed={isSelected}
                      className="feishu-emoji-button"
                    >
                      {emoji.emoji}
                    </Button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Streaming */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3 font-serif">
            <div>
              <label className="es-label">
                {t("feishu.streamReply", "Streaming Cards")}
              </label>
              <p className="es-hint mt-0.5">
                {t(
                  "feishu.streamReplyDesc",
                  "Update the reply card while the agent is generating",
                )}
              </p>
            </div>
            <ToggleSwitch
              enabled={streamReply}
              onToggle={() => setStreamReply(!streamReply)}
              ariaLabel={t("feishu.streamReply", "Streaming Cards")}
            />
          </div>
        </div>

        {/* Audio */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3 font-serif">
            <div>
              <label className="es-label">
                {t("feishu.autoTranscribeAudio", "Audio Transcription")}
              </label>
              <p className="es-hint mt-0.5">
                {t(
                  "feishu.autoTranscribeAudioDesc",
                  "Attach voice messages and ask the agent to transcribe them",
                )}
              </p>
            </div>
            <ToggleSwitch
              enabled={autoTranscribeAudio}
              onToggle={() => setAutoTranscribeAudio(!autoTranscribeAudio)}
              ariaLabel={t("feishu.autoTranscribeAudio", "Audio Transcription")}
            />
          </div>
          {autoTranscribeAudio && (
            <div className="es-field mt-3">
              <label htmlFor={`${formId}-audioPrompt`} className="es-label">
                {t("feishu.audioTranscribePrompt")}
              </label>
              <textarea
                id={`${formId}-audioPrompt`}
                value={audioTranscribePrompt}
                onChange={(e) => setAudioTranscribePrompt(e.target.value)}
                rows={3}
                className="glass-input es-input min-h-[5rem] resize-y"
                placeholder={DEFAULT_AUDIO_TRANSCRIBE_PROMPT}
              />
            </div>
          )}
        </div>

        {/* Group Policy */}
        <div className="es-field">
          <label className="es-label">
            {t("feishu.groupPolicy", "Group Message Policy")}
          </label>
          <div
            role="group"
            aria-label={t("feishu.groupPolicy")}
            className="feishu-policy-grid"
          >
            <button
              type="button"
              aria-pressed={groupPolicy === "mention"}
              aria-label={t("feishu.groupPolicyMention")}
              onClick={() => setGroupPolicy("mention")}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
                groupPolicy === "mention"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)] shadow-sm shadow-[var(--theme-primary)]/10"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)] hover:border-[var(--theme-text-secondary)]"
              }`}
            >
              <div
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-14 font-medium transition-colors ${
                  groupPolicy === "mention"
                    ? "bg-[var(--theme-primary)] text-white dark:text-[var(--theme-bg-card)]"
                    : "bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)]"
                }`}
              >
                @
              </div>
              <div className="min-w-0">
                <span className="block text-12 font-medium text-[var(--theme-text)]">
                  {t("feishu.groupPolicyMention", "Mention Only")}
                </span>
                <span className="text-10 text-[var(--theme-text-secondary)]">
                  {t("feishu.groupPolicyMentionDesc", "Reply when @mentioned")}
                </span>
              </div>
            </button>
            <button
              type="button"
              aria-pressed={groupPolicy === "open"}
              aria-label={t("feishu.groupPolicyOpen")}
              onClick={() => setGroupPolicy("open")}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
                groupPolicy === "open"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)] shadow-sm shadow-[var(--theme-primary)]/10"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)] hover:border-[var(--theme-text-secondary)]"
              }`}
            >
              <div
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-14 transition-colors ${
                  groupPolicy === "open"
                    ? "bg-[var(--theme-primary)]"
                    : "bg-[var(--glass-bg-subtle)]"
                }`}
              >
                💬
              </div>
              <div className="min-w-0">
                <span className="block text-12 font-medium text-[var(--theme-text)]">
                  {t("feishu.groupPolicyOpen", "All Messages")}
                </span>
                <span className="text-10 text-[var(--theme-text-secondary)]">
                  {t("feishu.groupPolicyOpenDesc", "Reply to all messages")}
                </span>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Agent & Model */}
      <fieldset disabled={isSaving || !canWrite} className="min-w-0 space-y-4">
        <div className="es-section">
          <ChannelAgentSelect value={agentId} onChange={onAgentIdChange} />
        </div>
        <div className="es-section">
          <ChannelModelSelect value={modelId} onChange={setModelId} />
        </div>
        <div className="es-section">
          {agentId === "team" ? (
            <ChannelTeamSelect value={teamId} onChange={setTeamId} />
          ) : (
            <ChannelPersonaSelect
              value={personaPresetId}
              onChange={setPersonaPresetId}
            />
          )}
        </div>

        {runConfiguration}
      </fieldset>

      {/* Setup Guide */}
      <div className="es-callout">
        <div className="es-callout-body">
          <div className="es-callout-title">
            {t("feishu.setupGuide", "Setup Guide")}
          </div>
          <ol className="mt-1 list-decimal list-outside ml-4 space-y-0.5 text-[0.8rem] text-[var(--theme-text-secondary)]">
            <li>
              {t(platform === "lark" ? "feishu.larkStep1" : "feishu.step1")}
            </li>
            <li>
              {t(
                "feishu.step2",
                "Create a custom app and get App ID and App secret",
              )}
            </li>
            <li>
              {t(
                "feishu.step3",
                "Enable bot capability and subscribe to message events",
              )}
            </li>
            <li>
              {t(
                "feishu.step4",
                "Use WebSocket long connection (no public IP required)",
              )}
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
