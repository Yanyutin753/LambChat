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
import {
  ChannelPluginOptions,
  type ChannelPluginOptionValues,
} from "../ChannelPluginOptions";
import {
  filterPluginOptionsByVisibleWhen,
  hasEffectiveCorePersonaSuppressingOption,
} from "../../../../extensions/pluginOptions";
import {
  DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
  PREDEFINED_EMOJIS,
} from "./constants";
import type { FeishuConfigStatus } from "./types";
import type { ExtensionScopedOption } from "../../../../types";

interface FeishuPanelFormProps {
  t: TFunction;
  hasExistingConfig: boolean;
  status: FeishuConfigStatus | null;
  enabled: boolean;
  isTesting: boolean;
  canWrite: boolean;
  instanceName: string;
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
  channelPluginOptions: readonly ExtensionScopedOption[];
  channelPluginOptionValues: ChannelPluginOptionValues;
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
  setChannelPluginOption: (pluginId: string, key: string, value: unknown) => void;
  setPersonaPresetId: (value: string | null) => void;
  setCredentialMode: (value: "scan" | "manual") => void;
  handleStartRegistration: () => void;
  handleTest: () => void;
}

function FeishuToggle({
  checked,
  onChange,
  ariaLabel,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50 ${
        checked
          ? "bg-amber-500 shadow-sm shadow-amber-500/25"
          : "bg-stone-200 dark:bg-stone-700"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-[18px]" : "translate-x-[3px]"
        }`}
      />
    </button>
  );
}

export function FeishuPanelForm({
  t,
  hasExistingConfig,
  status,
  enabled,
  isTesting,
  canWrite,
  instanceName,
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
  channelPluginOptions,
  channelPluginOptionValues,
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
  setChannelPluginOption,
  setPersonaPresetId,
  setCredentialMode,
  handleStartRegistration,
  handleTest,
}: FeishuPanelFormProps) {
  const effectiveChannelPluginOptions = filterPluginOptionsByVisibleWhen(
    channelPluginOptions,
    {
      agentId,
      route: "/channels/feishu",
      scope: "channel",
    },
  );
  const suppressesCorePersonaSelector = hasEffectiveCorePersonaSuppressingOption(
    effectiveChannelPluginOptions,
  );

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
              <div className="es-callout-desc">{status.error_message}</div>
            )}
          </div>
          <button
            onClick={handleTest}
            disabled={isTesting || !enabled}
            className="btn-secondary btn-sm ml-auto flex-shrink-0"
          >
            {isTesting ? (
              <span className="animate-spin inline-block">⟳</span>
            ) : (
              <RefreshCw size={14} />
            )}
            {t("feishu.testConnection", "Test")}
          </button>
        </div>
      )}

      {/* Instance Name */}
      {!hasExistingConfig && (
        <div className="es-field">
          <label className="es-label">
            {t("feishu.instanceName", "Instance Name")}
            <span className="es-required">*</span>
          </label>
          <input
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
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-[var(--theme-text)]">
              {t("feishu.enabled", "Enable Feishu Bot")}
            </div>
            <p className="es-hint mt-0.5">
              {t("feishu.enabledDesc", "Enable or disable this channel")}
            </p>
          </div>
          <button
            onClick={() => setEnabled(!enabled)}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50 ${
              enabled
                ? "bg-amber-500 shadow-sm shadow-amber-500/25"
                : "bg-stone-200 dark:bg-stone-700"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                enabled ? "translate-x-[18px]" : "translate-x-[3px]"
              }`}
            />
          </button>
        </div>
      </div>

      {/* App Credentials */}
      <div className="es-section">
        <div className="es-section-title">
          {t("feishu.credentials", "App Credentials")}
        </div>

        <div className="mb-4 grid grid-cols-2 rounded-lg border border-[var(--theme-border)] bg-[var(--glass-bg-subtle)] p-1">
          <button
            type="button"
            onClick={() => setCredentialMode("scan")}
            className={`rounded-md px-3 py-2 text-sm font-medium transition-all ${
              credentialMode === "scan"
                ? "bg-[var(--theme-bg-card)] text-[var(--theme-text)] shadow-sm border border-[var(--theme-border)]"
                : "text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] border border-transparent"
            }`}
          >
            {t("feishu.scanCreate", "Scan to Create")}
          </button>
          <button
            type="button"
            onClick={() => setCredentialMode("manual")}
            className={`rounded-md px-3 py-2 text-sm font-medium transition-all ${
              credentialMode === "manual"
                ? "bg-[var(--theme-bg-card)] text-[var(--theme-text)] shadow-sm border border-[var(--theme-border)]"
                : "text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] border border-transparent"
            }`}
          >
            {t("feishu.manualFill", "Manual")}
          </button>
        </div>

        {credentialMode === "scan" && (
          <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-6 text-center">
            <p className="mx-auto max-w-[28rem] text-sm text-[var(--theme-text-secondary)]">
              {t(
                "feishu.scanCreateDesc",
                "Use the Feishu app to scan and create a bot. The current App ID and App Secret will be overwritten.",
              )}
            </p>

            <button
              type="button"
              onClick={handleStartRegistration}
              disabled={isRegistering || !canWrite}
              className="btn-primary mx-auto mt-4"
            >
              <QrCode size={16} />
              {isRegistering
                ? t("feishu.registering", "Waiting for scan")
                : t("feishu.oneClickRegister", "Create Feishu App")}
            </button>

            {(registrationQrDataUrl || isRegistering) && (
              <div className="mt-5 flex flex-col items-center">
                <div className="flex size-[224px] items-center justify-center rounded-xl border border-[var(--theme-border)] bg-white p-3 shadow-sm">
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
                <div className="mt-3 text-sm font-medium text-[var(--theme-primary)]">
                  {registrationStatus === "qr_ready"
                    ? t("feishu.waitingForScan", "Waiting for scan")
                    : registrationStatus ||
                      t("feishu.waitingForQr", "Preparing QR")}
                </div>
                <div className="mt-2 text-xs text-[var(--theme-text-secondary)]">
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
                    className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--theme-primary)]"
                  >
                    <ExternalLink size={12} />
                    {t("feishu.openRegistration", "Open in browser")}
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        {credentialMode === "manual" && (
          <>
            <div className="es-field">
              <label className="es-label">
                {t("feishu.appId", "App ID")}
                <span className="es-required">*</span>
              </label>
              <input
                type="text"
                value={appId}
                onChange={(e) => setAppId(e.target.value)}
                placeholder={t("feishu.appIdPlaceholder", "cli_xxxxxxxxxx")}
                className="glass-input es-input"
              />
            </div>
            <div className="es-field">
              <label className="es-label">
                {t("feishu.appSecret", "App Secret")}
                {hasExistingConfig ? (
                  <span className="es-hint ml-1">{t("feishu.leaveEmpty")}</span>
                ) : (
                  <span className="es-required">*</span>
                )}
              </label>
              <input
                type="password"
                value={appSecret}
                onChange={(e) => setAppSecret(e.target.value)}
                placeholder={
                  hasExistingConfig
                    ? t("feishu.passwordMask", "••••••••••••")
                    : ""
                }
                className="glass-input es-input"
              />
            </div>
          </>
        )}

        {credentialMode === "scan" && appId && (
          <div className="mt-4 rounded-lg border border-[var(--theme-border)] bg-[var(--glass-bg-subtle)] px-3 py-2">
            <div className="text-xs font-medium text-[var(--theme-text-secondary)]">
              {t("feishu.currentCredential", "Current credential")}
            </div>
            <div className="mt-1 truncate text-sm text-[var(--theme-text)]">
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
            ({t("feishu.optional")})
          </span>
        </div>
        <div className="es-field">
          <label className="es-label">
            {t("feishu.encryptKey", "Encrypt Key")}
          </label>
          <input
            type="text"
            value={encryptKey}
            onChange={(e) => setEncryptKey(e.target.value)}
            className="glass-input es-input"
          />
        </div>
        <div className="es-field">
          <label className="es-label">
            {t("feishu.verificationToken", "Verification Token")}
          </label>
          <input
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
          <div className="flex items-center justify-between">
            <label className="es-label">
              {t("feishu.reactEmoji", "Reaction Emoji")}
            </label>
            <button
              type="button"
              onClick={() => setUseCustomEmoji(!useCustomEmoji)}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                useCustomEmoji
                  ? "bg-[var(--theme-primary)] text-white dark:text-[var(--theme-bg-card)]"
                  : "bg-[var(--glass-bg-subtle)] text-theme-text-secondary hover:bg-theme-primary-light"
              }`}
            >
              <Sparkles size={12} />
              {useCustomEmoji
                ? t("feishu.preset", "Preset")
                : t("feishu.custom", "Custom")}
            </button>
          </div>

          {useCustomEmoji ? (
            <>
              <input
                type="text"
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
              <div className="grid grid-cols-6 gap-1 sm:grid-cols-8">
                {PREDEFINED_EMOJIS.map((emoji) => {
                  const isSelected = reactEmoji === emoji.value;
                  return (
                    <button
                      key={emoji.value}
                      type="button"
                      onClick={() => setReactEmoji(emoji.value)}
                      title={t(emoji.labelKey)}
                      className={`flex h-9 w-full items-center justify-center rounded-lg text-lg transition-all duration-150 ${
                        isSelected
                          ? "bg-[var(--theme-primary)]/15 ring-1 ring-[var(--theme-primary)]/40"
                          : "hover:bg-[var(--theme-bg-card)]"
                      }`}
                    >
                      {emoji.emoji}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Streaming */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3">
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
            <FeishuToggle
              checked={streamReply}
              onChange={setStreamReply}
              ariaLabel={t("feishu.streamReply", "Streaming Cards")}
            />
          </div>
        </div>

        {/* Audio */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3">
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
            <FeishuToggle
              checked={autoTranscribeAudio}
              onChange={setAutoTranscribeAudio}
              ariaLabel={t("feishu.autoTranscribeAudio", "Audio Transcription")}
            />
          </div>
          {autoTranscribeAudio && (
            <textarea
              value={audioTranscribePrompt}
              onChange={(e) => setAudioTranscribePrompt(e.target.value)}
              rows={3}
              className="glass-input es-input mt-3 min-h-[5rem] resize-y"
              placeholder={DEFAULT_AUDIO_TRANSCRIBE_PROMPT}
            />
          )}
        </div>

        {/* Group Policy */}
        <div className="es-field">
          <label className="es-label">
            {t("feishu.groupPolicy", "Group Message Policy")}
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setGroupPolicy("mention")}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-all ${
                groupPolicy === "mention"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)] shadow-sm shadow-[var(--theme-primary)]/10"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)] hover:border-[var(--theme-text-secondary)]"
              }`}
            >
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-md text-sm font-medium transition-colors ${
                  groupPolicy === "mention"
                    ? "bg-[var(--theme-primary)] text-white dark:text-[var(--theme-bg-card)]"
                    : "bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)]"
                }`}
              >
                @
              </div>
              <div className="min-w-0">
                <span className="block text-xs font-medium text-[var(--theme-text)]">
                  {t("feishu.groupPolicyMention", "Mention Only")}
                </span>
                <span className="text-[10px] text-[var(--theme-text-secondary)]">
                  {t("feishu.groupPolicyMentionDesc", "Reply when @mentioned")}
                </span>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setGroupPolicy("open")}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-all ${
                groupPolicy === "open"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)] shadow-sm shadow-[var(--theme-primary)]/10"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)] hover:border-[var(--theme-text-secondary)]"
              }`}
            >
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-md text-sm transition-colors ${
                  groupPolicy === "open"
                    ? "bg-[var(--theme-primary)]"
                    : "bg-[var(--glass-bg-subtle)]"
                }`}
              >
                💬
              </div>
              <div className="min-w-0">
                <span className="block text-xs font-medium text-[var(--theme-text)]">
                  {t("feishu.groupPolicyOpen", "All Messages")}
                </span>
                <span className="text-[10px] text-[var(--theme-text-secondary)]">
                  {t("feishu.groupPolicyOpenDesc", "Reply to all messages")}
                </span>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Agent & Model */}
      <div className="es-section">
        <ChannelAgentSelect value={agentId} onChange={onAgentIdChange} />
      </div>
      <div className="es-section">
        <ChannelModelSelect value={modelId} onChange={setModelId} />
      </div>
      <div className="es-section">
        <ChannelPluginOptions
          options={effectiveChannelPluginOptions}
          values={channelPluginOptionValues}
          disabled={!canWrite}
          onChange={setChannelPluginOption}
        />
        {!suppressesCorePersonaSelector && (
          <ChannelPersonaSelect
            value={personaPresetId}
            onChange={setPersonaPresetId}
          />
        )}
      </div>

      {/* Setup Guide */}
      <div className="es-callout">
        <div className="es-callout-body">
          <div className="es-callout-title">
            {t("feishu.setupGuide", "Setup Guide")}
          </div>
          <ol className="mt-1 list-decimal list-outside ml-4 space-y-0.5 text-[0.8rem] text-[var(--theme-text-secondary)]">
            <li>
              {t("feishu.step1", "Go to Feishu Open Platform (open.feishu.cn)")}
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
