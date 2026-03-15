import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  MessageSquare,
  Save,
  Trash2,
  RefreshCw,
  Check,
  X,
  AlertCircle,
  ArrowLeft,
  Sparkles,
} from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { PanelHeader } from "../../../common/PanelHeader";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
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
}: FeishuPanelProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // State
  const [, setConfig] = useState<FeishuConfigResponse | null>(null);
  const [status, setStatus] = useState<FeishuConfigStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  // Form state
  const [enabled, setEnabled] = useState(false);
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [encryptKey, setEncryptKey] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [reactEmoji, setReactEmoji] = useState("THUMBSUP");
  const [customEmoji, setCustomEmoji] = useState("");
  const [useCustomEmoji, setUseCustomEmoji] = useState(false);
  const [groupPolicy, setGroupPolicy] = useState<"open" | "mention">("mention");

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
      setEnabled(initialConfig.enabled);
      setAppId(feishuConfig?.app_id || "");
      setEncryptKey(feishuConfig?.encrypt_key || "");
      setVerificationToken(feishuConfig?.verification_token || "");
      setGroupPolicy(feishuConfig?.group_policy || "mention");

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
      setEnabled(false);
      setAppId("");
      setAppSecret("");
      setEncryptKey("");
      setVerificationToken("");
      setReactEmoji("THUMBSUP");
      setCustomEmoji("");
      setUseCustomEmoji(false);
      setGroupPolicy("mention");
    }

    if (initialStatus) {
      setStatus(initialStatus as FeishuConfigStatus);
    }
    setIsLoading(false);
  };

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const [configResponse, statusResponse] = await Promise.all([
        channelApi.get("feishu", instanceId!),
        channelApi.getStatus("feishu", instanceId!),
      ]);

      if (configResponse) {
        const feishuConfig = configResponse.config as FeishuConfigResponse;
        setConfig(feishuConfig);
        setHasExistingConfig(true);
        setEnabled(configResponse.enabled);
        setAppId(feishuConfig.app_id || "");
        setEncryptKey(feishuConfig.encrypt_key || "");
        setVerificationToken(feishuConfig.verification_token || "");
        setGroupPolicy(feishuConfig.group_policy || "mention");

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
        setEnabled(false);
        setAppId("");
        setAppSecret("");
        setEncryptKey("");
        setVerificationToken("");
        setReactEmoji("THUMBSUP");
        setCustomEmoji("");
        setUseCustomEmoji(false);
        setGroupPolicy("mention");
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
        });
        const feishuConfig = updated.config as FeishuConfigResponse;
        setConfig(feishuConfig);
        setHasExistingConfig(true);
        setAppSecret("");
      } else {
        const created = await channelApi.create({
          channel_type: "feishu",
          name: instanceId, // Use instanceId as name for now
          config: {
            app_id: appId,
            app_secret: appSecret,
            encrypt_key: encryptKey || undefined,
            verification_token: verificationToken || undefined,
            react_emoji: emojiValue,
            group_policy: groupPolicy,
          },
        });
        const feishuConfig = created.config as FeishuConfigResponse;
        setConfig(feishuConfig);
        setHasExistingConfig(true);
        setAppSecret("");
      }

      toast.success(t("feishu.saveSuccess", "Feishu configuration saved"));

      const newStatus = await channelApi.getStatus("feishu", instanceId);
      setStatus(newStatus);
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
    return (
      <div className="flex h-full items-center justify-center text-gray-500 dark:text-gray-400">
        <LoadingSpinner size="sm" />
        <span className="ml-2">{t("common.loading")}</span>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* Header */}
      <PanelHeader
        title={t("feishu.title", "Feishu/Lark Channel")}
        subtitle={t(
          "feishu.description",
          "Connect your Feishu bot to receive and send messages",
        )}
        icon={
          <MessageSquare
            size={18}
            className="text-blue-600 dark:text-blue-400"
          />
        }
        actions={
          <button
            onClick={() => navigate("/channels")}
            className="btn-secondary"
          >
            <ArrowLeft size={16} />
            <span className="hidden sm:inline">{t("common.back")}</span>
          </button>
        }
      />

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4">
        <div className="mx-auto max-w-2xl space-y-4">
          {/* Status Card */}
          {hasExistingConfig && status && (
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {status.connected ? (
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/50">
                      <Check
                        size={16}
                        className="text-green-600 dark:text-green-400"
                      />
                    </div>
                  ) : (
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/50">
                      <X size={16} className="text-red-600 dark:text-red-400" />
                    </div>
                  )}
                  <div>
                    <span
                      className={`text-sm font-semibold ${
                        status.connected
                          ? "text-green-600 dark:text-green-400"
                          : "text-red-600 dark:text-red-400"
                      }`}
                    >
                      {status.connected
                        ? t("feishu.connected", "Connected")
                        : t("feishu.disconnected", "Disconnected")}
                    </span>
                  </div>
                </div>
                <button
                  onClick={handleTest}
                  disabled={isTesting || !enabled}
                  className="btn-secondary btn-sm"
                >
                  {isTesting ? (
                    <span className="animate-spin">⟳</span>
                  ) : (
                    <RefreshCw size={14} />
                  )}
                  {t("feishu.testConnection", "Test")}
                </button>
              </div>
              {status.error_message && (
                <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 dark:bg-red-900/20">
                  <AlertCircle
                    size={16}
                    className="flex-shrink-0 text-red-500 dark:text-red-400"
                  />
                  <span className="text-sm text-red-700 dark:text-red-300">
                    {status.error_message}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Configuration Form */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
            <h3 className="mb-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t("feishu.configuration", "Configuration")}
            </h3>

            <div className="space-y-4">
              {/* Enable Toggle */}
              <div className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2.5 dark:bg-stone-800">
                <div>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                    {t("feishu.enabled", "Enable Feishu Bot")}
                  </span>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t("feishu.enabledDesc", "Enable or disable this channel")}
                  </p>
                </div>
                <button
                  onClick={() => setEnabled(!enabled)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    enabled ? "bg-stone-900" : "bg-gray-200 dark:bg-stone-600"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${
                      enabled ? "translate-x-4" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>

              {/* App Credentials */}
              <div className="space-y-3">
                <h4 className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {t("feishu.credentials", "App Credentials")}
                </h4>

                {/* App ID */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200">
                    {t("feishu.appId", "App ID")}{" "}
                    <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={appId}
                    onChange={(e) => setAppId(e.target.value)}
                    placeholder={t("feishu.appIdPlaceholder", "cli_xxxxxxxxxx")}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-stone-500 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-gray-100 dark:placeholder-gray-500"
                  />
                </div>

                {/* App Secret */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200">
                    {t("feishu.appSecret", "App Secret")}{" "}
                    {hasExistingConfig ? (
                      <span className="text-xs text-gray-400">
                        {t("feishu.leaveEmpty")}
                      </span>
                    ) : (
                      <span className="text-red-500">*</span>
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
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-stone-500 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-gray-100 dark:placeholder-gray-500"
                  />
                </div>
              </div>

              {/* Security Settings */}
              <div className="space-y-3">
                <h4 className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {t("feishu.security", "Security Settings")}
                  <span className="ml-1 normal-case tracking-normal text-gray-400">
                    {t("feishu.optional")}
                  </span>
                </h4>

                {/* Encrypt Key */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200">
                    {t("feishu.encryptKey", "Encrypt Key")}
                  </label>
                  <input
                    type="text"
                    value={encryptKey}
                    onChange={(e) => setEncryptKey(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-stone-500 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-gray-100 dark:placeholder-gray-500"
                  />
                </div>

                {/* Verification Token */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200">
                    {t("feishu.verificationToken", "Verification Token")}
                  </label>
                  <input
                    type="text"
                    value={verificationToken}
                    onChange={(e) => setVerificationToken(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-stone-500 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-gray-100 dark:placeholder-gray-500"
                  />
                </div>
              </div>

              {/* Behavior Settings */}
              <div className="space-y-3">
                <h4 className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {t("feishu.behavior", "Behavior Settings")}
                </h4>

                {/* React Emoji */}
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-200">
                      {t("feishu.reactEmoji", "Reaction Emoji")}
                    </label>
                    <button
                      type="button"
                      onClick={() => setUseCustomEmoji(!useCustomEmoji)}
                      className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                        useCustomEmoji
                          ? "bg-stone-900 text-gray-100 dark:bg-gray-100 dark:text-gray-900"
                          : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-stone-800 dark:text-gray-400 dark:hover:bg-stone-700"
                      }`}
                    >
                      <Sparkles size={12} />
                      {t("feishu.custom", "Custom")}
                    </button>
                  </div>

                  {useCustomEmoji ? (
                    <div>
                      <input
                        type="text"
                        value={customEmoji}
                        onChange={(e) => setCustomEmoji(e.target.value)}
                        placeholder={t(
                          "feishu.customEmojiPlaceholder",
                          "Enter emoji or text (e.g., 🎯 or DONE)",
                        )}
                        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-stone-500 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-gray-100 dark:placeholder-gray-500"
                      />
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {t(
                          "feishu.customEmojiHint",
                          "Enter an emoji character or a Feishu emoji type code",
                        )}
                      </p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6">
                      {PREDEFINED_EMOJIS.map((emoji) => (
                        <button
                          key={emoji.value}
                          type="button"
                          onClick={() => setReactEmoji(emoji.value)}
                          className={`flex flex-col items-center gap-0.5 rounded-lg border px-2 py-1.5 transition-all ${
                            reactEmoji === emoji.value
                              ? "border-stone-400 bg-gray-100 dark:border-stone-500 dark:bg-stone-800"
                              : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50 dark:border-stone-700 dark:bg-stone-900 dark:hover:border-stone-600"
                          }`}
                        >
                          <span className="text-base">{emoji.emoji}</span>
                          <span className="text-[10px] text-gray-500 dark:text-gray-400">
                            {t(emoji.labelKey)}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Group Policy */}
                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200">
                    {t("feishu.groupPolicy", "Group Message Policy")}
                  </label>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => setGroupPolicy("mention")}
                      className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-all ${
                        groupPolicy === "mention"
                          ? "border-stone-400 bg-gray-50 dark:border-stone-500 dark:bg-stone-800"
                          : "border-gray-200 bg-white hover:border-gray-300 dark:border-stone-700 dark:bg-stone-900 dark:hover:border-stone-600"
                      }`}
                    >
                      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gray-100 text-sm dark:bg-stone-700">
                        @
                      </div>
                      <div>
                        <span className="block text-sm font-medium text-gray-700 dark:text-gray-200">
                          {t("feishu.groupPolicyMention", "Mention Only")}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {t(
                            "feishu.groupPolicyMentionDesc",
                            "Reply when @mentioned",
                          )}
                        </span>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setGroupPolicy("open")}
                      className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-all ${
                        groupPolicy === "open"
                          ? "border-stone-400 bg-gray-50 dark:border-stone-500 dark:bg-stone-800"
                          : "border-gray-200 bg-white hover:border-gray-300 dark:border-stone-700 dark:bg-stone-900 dark:hover:border-stone-600"
                      }`}
                    >
                      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gray-100 text-sm dark:bg-stone-700">
                        💬
                      </div>
                      <div>
                        <span className="block text-sm font-medium text-gray-700 dark:text-gray-200">
                          {t("feishu.groupPolicyOpen", "All Messages")}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {t(
                            "feishu.groupPolicyOpenDesc",
                            "Reply to all messages",
                          )}
                        </span>
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Help Card */}
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-stone-700 dark:bg-stone-800/50">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {t("feishu.setupGuide", "Setup Guide")}
                </p>
                <ol className="mt-2 list-decimal list-outside ml-4 space-y-1 text-sm text-gray-600 dark:text-gray-300">
                  <li>
                    {t(
                      "feishu.step1",
                      "Go to Feishu Open Platform (open.feishu.cn)",
                    )}
                  </li>
                  <li>
                    {t(
                      "feishu.step2",
                      "Create a custom app and get App ID and App Secret",
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

          {/* Actions */}
          <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:items-center sm:justify-between">
            <button
              onClick={handleDelete}
              disabled={!hasExistingConfig}
              className="btn-secondary !text-red-600 hover:!bg-red-50 disabled:opacity-50 dark:hover:!bg-red-900/20"
            >
              <Trash2 size={16} />
              {t("common.delete")}
            </button>

            <button
              onClick={handleSave}
              disabled={isSaving || !appId.trim()}
              className="btn-primary"
            >
              {isSaving ? <LoadingSpinner size="sm" /> : <Save size={16} />}
              {t("common.save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
