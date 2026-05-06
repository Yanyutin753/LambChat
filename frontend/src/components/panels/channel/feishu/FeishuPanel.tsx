import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BackIcon } from "../../../common/BackIcon";
import {
  MessageSquare,
  Save,
  Trash2,
  RefreshCw,
  Check,
  X,
  Sparkles,
} from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../../hooks/useAuth";
import { Permission } from "../../../../types";
import { PanelHeader } from "../../../common/PanelHeader";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ChannelsPanelSkeleton } from "../../../skeletons";
import { ChannelAgentSelect } from "../ChannelAgentSelect";
import { ChannelModelSelect } from "../ChannelModelSelect";
import { EditorSidebar } from "../../../common/EditorSidebar";
import { channelApi } from "../../../../services/api/channel";
import type {
  ChannelConfigResponse,
  ChannelConfigStatus,
} from "../../../../types/channel";

type FeishuConfigResponse = ChannelConfigResponse["config"] & {
  app_id: string;
  encrypt_key: string;
  verification_token: string;
  react_emoji: string;
  group_policy: "open" | "mention";
};

type FeishuConfigStatus = ChannelConfigStatus;

interface FeishuPanelProps {
  instanceId: string;
  initialConfig?: ChannelConfigResponse | null;
  initialStatus?: ChannelConfigStatus | null;
  isLoading?: boolean;
  onClose?: () => void;
}

// Predefined emoji options
const PREDEFINED_EMOJIS = [
  { value: "THUMBSUP", emoji: "👍", labelKey: "feishu.emoji.thumbsUp" },
  { value: "OK", emoji: "👌", labelKey: "feishu.emoji.ok" },
  { value: "EYES", emoji: "👀", labelKey: "feishu.emoji.eyes" },
  { value: "DONE", emoji: "✅", labelKey: "feishu.emoji.done" },
  { value: "HEART", emoji: "❤️", labelKey: "feishu.emoji.heart" },
  { value: "FIRE", emoji: "🔥", labelKey: "feishu.emoji.fire" },
  { value: "ROCKET", emoji: "🚀", labelKey: "feishu.emoji.rocket" },
  { value: "CLAP", emoji: "👏", labelKey: "feishu.emoji.clap" },
  { value: "STAR", emoji: "⭐", labelKey: "feishu.emoji.star" },
  { value: "PARTY", emoji: "🎉", labelKey: "feishu.emoji.party" },
  { value: "THINKING", emoji: "🤔", labelKey: "feishu.emoji.thinking" },
  { value: "MUSCLE", emoji: "💪", labelKey: "feishu.emoji.muscle" },
];

export function FeishuPanel({
  instanceId,
  initialConfig,
  initialStatus,
  isLoading: externalIsLoading,
  onClose,
}: FeishuPanelProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const navigate = useNavigate();

  const canWrite = hasPermission(Permission.CHANNEL_WRITE);
  const canDelete = hasPermission(Permission.CHANNEL_DELETE);

  // State
  const [, setConfig] = useState<FeishuConfigResponse | null>(null);
  const [status, setStatus] = useState<FeishuConfigStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  // Form state
  const [instanceName, setInstanceName] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [encryptKey, setEncryptKey] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [reactEmoji, setReactEmoji] = useState("THUMBSUP");
  const [customEmoji, setCustomEmoji] = useState("");
  const [useCustomEmoji, setUseCustomEmoji] = useState(false);
  const [groupPolicy, setGroupPolicy] = useState<"open" | "mention">("mention");
  const [agentId, setAgentId] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);

  // Track if config exists
  const [hasExistingConfig, setHasExistingConfig] = useState(false);

  // Load config - use external data if provided, otherwise fetch from API
  useEffect(() => {
    if (externalIsLoading) {
      return;
    }

    // Use external data if available
    if (initialConfig || initialStatus) {
      initializeFromExternalData();
      return;
    }

    // Otherwise fetch from API
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalIsLoading, initialConfig, initialStatus]);

  const initializeFromExternalData = () => {
    if (initialConfig) {
      const feishuConfig = initialConfig.config as unknown as
        | FeishuConfigResponse
        | undefined;
      setConfig(feishuConfig ?? null);
      setHasExistingConfig(true);
      setInstanceName(initialConfig.name || "");
      setEnabled(initialConfig.enabled);
      setAppId(feishuConfig?.app_id || "");
      setEncryptKey(feishuConfig?.encrypt_key || "");
      setVerificationToken(feishuConfig?.verification_token || "");
      setGroupPolicy(feishuConfig?.group_policy || "mention");
      setAgentId(initialConfig.agent_id || null);
      setModelId(initialConfig.model_id || null);

      const emojiValue = (feishuConfig?.react_emoji as string) || "THUMBSUP";
      const isPredefined = PREDEFINED_EMOJIS.some(
        (e) => e.value === emojiValue,
      );
      if (isPredefined) {
        setReactEmoji(emojiValue);
        setUseCustomEmoji(false);
      } else {
        setCustomEmoji(emojiValue);
        setUseCustomEmoji(true);
        setReactEmoji("THUMBSUP");
      }
    } else {
      setHasExistingConfig(false);
      setInstanceName("");
      setEnabled(false);
      setAppId("");
      setAppSecret("");
      setEncryptKey("");
      setVerificationToken("");
      setReactEmoji("THUMBSUP");
      setCustomEmoji("");
      setUseCustomEmoji(false);
      setGroupPolicy("mention");
      setAgentId(null);
      setModelId(null);
    }

    if (initialStatus) {
      setStatus(initialStatus as FeishuConfigStatus);
    }
    setIsLoading(false);
  };

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      // For new instances, just set defaults without calling API
      if (instanceId === "new") {
        setHasExistingConfig(false);
        setEnabled(false);
        setInstanceName("");
        setAppId("");
        setAppSecret("");
        setEncryptKey("");
        setVerificationToken("");
        setReactEmoji("THUMBSUP");
        setCustomEmoji("");
        setUseCustomEmoji(false);
        setGroupPolicy("mention");
        setStatus(null);
        setIsLoading(false);
        return;
      }

      const [configResponse, statusResponse] = await Promise.all([
        channelApi.get("feishu", instanceId!),
        channelApi.getStatus("feishu", instanceId!),
      ]);

      if (configResponse) {
        const feishuConfig = configResponse.config as FeishuConfigResponse;
        setConfig(feishuConfig);
        setHasExistingConfig(true);
        setInstanceName(configResponse.name || "");
        setEnabled(configResponse.enabled);
        setAppId(feishuConfig.app_id || "");
        setEncryptKey(feishuConfig.encrypt_key || "");
        setVerificationToken(feishuConfig.verification_token || "");
        setGroupPolicy(feishuConfig.group_policy || "mention");
        setAgentId(configResponse.agent_id || null);
        setModelId(configResponse.model_id || null);

        // Check if the emoji is a predefined one or custom
        const emojiValue = feishuConfig?.react_emoji || "THUMBSUP";
        const isPredefined = PREDEFINED_EMOJIS.some(
          (e) => e.value === emojiValue,
        );
        if (isPredefined) {
          setReactEmoji(emojiValue);
          setUseCustomEmoji(false);
        } else {
          setCustomEmoji(emojiValue);
          setUseCustomEmoji(true);
          setReactEmoji("THUMBSUP");
        }
      } else {
        setHasExistingConfig(false);
        setInstanceName("");
        setEnabled(false);
        setAppId("");
        setAppSecret("");
        setEncryptKey("");
        setVerificationToken("");
        setReactEmoji("THUMBSUP");
        setCustomEmoji("");
        setUseCustomEmoji(false);
        setGroupPolicy("mention");
        setAgentId(null);
        setModelId(null);
      }

      setStatus(statusResponse);
    } catch (error) {
      console.error("Failed to load Feishu config:", error);
      toast.error(t("feishu.loadError", "Failed to load Feishu configuration"));
    } finally {
      setIsLoading(false);
    }
  };

  const getEmojiValue = () => {
    return useCustomEmoji ? customEmoji : reactEmoji;
  };

  const handleSave = async () => {
    // Validate instance name for new instances
    if (!hasExistingConfig && !instanceName.trim()) {
      toast.error(
        t("feishu.instanceNameRequired", "Instance name is required"),
      );
      return;
    }

    if (!appId.trim()) {
      toast.error(t("feishu.appIdRequired", "App ID is required"));
      return;
    }

    if (!hasExistingConfig && !appSecret.trim()) {
      toast.error(t("feishu.appSecretRequired", "App Secret is required"));
      return;
    }

    if (useCustomEmoji && !customEmoji.trim()) {
      toast.error(
        t(
          "feishu.customEmojiRequired",
          "Custom emoji is required when selected",
        ),
      );
      return;
    }

    setIsSaving(true);
    try {
      const emojiValue = getEmojiValue();

      if (hasExistingConfig) {
        const updateData: Record<string, unknown> = {
          app_id: appId,
          react_emoji: emojiValue,
          group_policy: groupPolicy,
          enabled,
        };

        if (appSecret.trim()) {
          updateData.app_secret = appSecret;
        }
        if (encryptKey.trim()) {
          updateData.encrypt_key = encryptKey;
        }
        if (verificationToken.trim()) {
          updateData.verification_token = verificationToken;
        }

        const updated = await channelApi.update("feishu", instanceId, {
          config: updateData,
          agent_id: agentId,
          model_id: modelId,
        });
        const feishuConfig = updated.config as FeishuConfigResponse;
        setConfig(feishuConfig);
        setHasExistingConfig(true);
        setAppSecret("");
      } else {
        const created = await channelApi.create({
          channel_type: "feishu",
          name: instanceName.trim(),
          config: {
            app_id: appId,
            app_secret: appSecret,
            encrypt_key: encryptKey || undefined,
            verification_token: verificationToken || undefined,
            react_emoji: emojiValue,
            group_policy: groupPolicy,
          },
          agent_id: agentId,
          model_id: modelId,
        });
        const feishuConfig = created.config as FeishuConfigResponse;
        setConfig(feishuConfig);
        setHasExistingConfig(true);
        setAppSecret("");
        // Navigate to the new instance URL
        navigate(`/channels/feishu/${created.instance_id}`, { replace: true });
      }

      toast.success(t("feishu.saveSuccess", "Feishu configuration saved"));

      // Only fetch status for existing instances
      if (hasExistingConfig) {
        const newStatus = await channelApi.getStatus("feishu", instanceId);
        setStatus(newStatus);
      }
    } catch (error) {
      console.error("Failed to save Feishu config:", error);
      const errorMessage =
        error instanceof Error
          ? error.message
          : t("feishu.saveError", "Failed to save Feishu configuration");
      toast.error(errorMessage);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (
      !window.confirm(
        t(
          "feishu.deleteConfirm",
          "Are you sure you want to delete your Feishu configuration? This action cannot be undone.",
        ),
      )
    ) {
      return;
    }

    try {
      await channelApi.delete("feishu", instanceId);
      setConfig(null);
      setHasExistingConfig(false);
      setEnabled(false);
      setAppId("");
      setAppSecret("");
      setEncryptKey("");
      setVerificationToken("");
      setReactEmoji("THUMBSUP");
      setCustomEmoji("");
      setUseCustomEmoji(false);
      setGroupPolicy("mention");
      setStatus(null);
      toast.success(t("feishu.deleteSuccess", "Feishu configuration deleted"));
      onClose?.();
    } catch (error) {
      console.error("Failed to delete Feishu config:", error);
      toast.error(
        t("feishu.deleteError", "Failed to delete Feishu configuration"),
      );
    }
  };

  const handleTest = async () => {
    setIsTesting(true);
    try {
      const result = await channelApi.test("feishu", instanceId);
      if (result.success) {
        toast.success(
          result.message || t("feishu.testSuccess", "Connection successful"),
        );
      } else {
        toast.error(
          result.message || t("feishu.testFailed", "Connection failed"),
        );
      }
    } catch (error) {
      console.error("Failed to test Feishu connection:", error);
      toast.error(t("feishu.testError", "Failed to test connection"));
    } finally {
      setIsTesting(false);
    }
  };

  if (isLoading) {
    return <ChannelsPanelSkeleton />;
  }

  // Form content shared between both modes
  const formContent = (
    <div className="es-form">
      {/* Status Callout */}
      {hasExistingConfig && status && (
        <div
          className={`es-callout ${
            status.connected ? "es-callout--success" : "es-callout--danger"
          }`}
        >
          <div className="es-callout-icon">
            {status.connected ? <Check size={14} /> : <X size={14} />}
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
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
              enabled ? "bg-[var(--theme-primary)]" : "bg-theme-primary-light"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${
                enabled ? "translate-x-4" : "translate-x-0.5"
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
              hasExistingConfig ? t("feishu.passwordMask", "••••••••••••") : ""
            }
            className="glass-input es-input"
          />
        </div>
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
                  ? "bg-[var(--theme-primary)] text-white"
                  : "bg-[var(--glass-bg-subtle)] text-theme-text-secondary hover:bg-theme-primary-light"
              }`}
            >
              <Sparkles size={12} />
              {t("feishu.custom", "Custom")}
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
            <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6">
              {PREDEFINED_EMOJIS.map((emoji) => (
                <button
                  key={emoji.value}
                  type="button"
                  onClick={() => setReactEmoji(emoji.value)}
                  className={`flex flex-col items-center gap-0.5 rounded-lg border px-2 py-1.5 transition-all ${
                    reactEmoji === emoji.value
                      ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)]"
                      : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)]"
                  }`}
                >
                  <span className="text-base">{emoji.emoji}</span>
                  <span className="text-[10px] text-[var(--theme-text-secondary)]">
                    {t(emoji.labelKey)}
                  </span>
                </button>
              ))}
            </div>
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
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-all ${
                groupPolicy === "mention"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)]"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)]"
              }`}
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--glass-bg-subtle)] text-sm font-medium">
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
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-all ${
                groupPolicy === "open"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)]"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)]"
              }`}
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--glass-bg-subtle)] text-sm">
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
        <ChannelAgentSelect value={agentId} onChange={setAgentId} />
      </div>
      <div className="es-section">
        <ChannelModelSelect value={modelId} onChange={setModelId} />
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

  // Action buttons
  const actionButtons = (
    <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:items-center sm:justify-between">
      {canDelete && (
        <button
          onClick={handleDelete}
          disabled={!hasExistingConfig}
          className="btn-danger"
        >
          <Trash2 size={16} />
          {t("common.delete")}
        </button>
      )}
      {canWrite && (
        <button
          onClick={handleSave}
          disabled={isSaving || !appId.trim()}
          className="btn-primary"
        >
          {isSaving ? (
            <LoadingSpinner size="sm" color="text-white" />
          ) : (
            <Save size={16} />
          )}
          {t("common.save")}
        </button>
      )}
    </div>
  );

  // Sidebar mode: render inside EditorSidebar
  if (onClose) {
    return (
      <EditorSidebar
        open={true}
        onClose={onClose}
        title={
          hasExistingConfig
            ? instanceName || t("feishu.title", "Feishu/Lark Channel")
            : t("feishu.newInstance", "New Feishu Instance")
        }
        subtitle={t("feishu.description")}
        icon={
          <MessageSquare
            size={20}
            className="text-blue-600 dark:text-blue-400"
          />
        }
        footer={actionButtons}
      >
        {formContent}
      </EditorSidebar>
    );
  }

  // Full-page mode (backward compatible)
  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      <PanelHeader
        title={t("feishu.title", "Feishu/Lark Channel")}
        subtitle={t("feishu.description")}
        icon={
          <MessageSquare
            size={20}
            className="text-blue-600 dark:text-blue-400"
          />
        }
        actions={
          <button
            onClick={() => navigate("/channels")}
            className="btn-secondary"
          >
            <BackIcon size={16} />
            <span className="hidden sm:inline">{t("common.back")}</span>
          </button>
        }
      />
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
        {formContent}
      </div>
      <div className="border-t border-[var(--theme-border)] px-3 py-3 sm:px-4">
        {actionButtons}
      </div>
    </div>
  );
}
