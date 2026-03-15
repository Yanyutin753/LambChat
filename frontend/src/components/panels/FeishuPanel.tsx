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
  Loader2,
  HelpCircle,
  ArrowLeft,
} from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  feishuApi,
  type FeishuConfigResponse,
  type FeishuConfigStatus,
} from "../../services/api/feishu";

export function FeishuPanel() {
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
  const [groupPolicy, setGroupPolicy] = useState<"open" | "mention">("mention");

  // Track if config exists
  const [hasExistingConfig, setHasExistingConfig] = useState(false);

  // Load config on mount
  useEffect(() => {
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const [configResponse, statusResponse] = await Promise.all([
        feishuApi.get(),
        feishuApi.getStatus(),
      ]);

      if (configResponse) {
        setConfig(configResponse);
        setHasExistingConfig(true);
        setEnabled(configResponse.enabled);
        setAppId(configResponse.app_id);
        setEncryptKey(configResponse.encrypt_key || "");
        setVerificationToken(configResponse.verification_token || "");
        setReactEmoji(configResponse.react_emoji || "THUMBSUP");
        setGroupPolicy(configResponse.group_policy || "mention");
      } else {
        setHasExistingConfig(false);
        // Reset form
        setEnabled(false);
        setAppId("");
        setAppSecret("");
        setEncryptKey("");
        setVerificationToken("");
        setReactEmoji("THUMBSUP");
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

  const handleSave = async () => {
    if (!appId.trim()) {
      toast.error(t("feishu.appIdRequired", "App ID is required"));
      return;
    }

    if (!hasExistingConfig && !appSecret.trim()) {
      toast.error(t("feishu.appSecretRequired", "App Secret is required"));
      return;
    }

    setIsSaving(true);
    try {
      if (hasExistingConfig) {
        // Update existing config
        const updateData: Record<string, unknown> = {
          app_id: appId,
          react_emoji: reactEmoji,
          group_policy: groupPolicy,
          enabled,
        };

        // Only include secret if user entered a new value
        if (appSecret.trim()) {
          updateData.app_secret = appSecret;
        }
        if (encryptKey.trim()) {
          updateData.encrypt_key = encryptKey;
        }
        if (verificationToken.trim()) {
          updateData.verification_token = verificationToken;
        }

        const updated = await feishuApi.update(updateData);
        setConfig(updated);
        setHasExistingConfig(true);
        // Clear secret field after save for security
        setAppSecret("");
      } else {
        // Create new config
        const created = await feishuApi.create({
          app_id: appId,
          app_secret: appSecret,
          encrypt_key: encryptKey || undefined,
          verification_token: verificationToken || undefined,
          react_emoji: reactEmoji,
          group_policy: groupPolicy,
          enabled,
        });
        setConfig(created);
        setHasExistingConfig(true);
        setAppSecret("");
      }

      toast.success(t("feishu.saveSuccess", "Feishu configuration saved"));

      // Reload status
      const newStatus = await feishuApi.getStatus();
      setStatus(newStatus);
    } catch (error) {
      console.error("Failed to save Feishu config:", error);
      toast.error(t("feishu.saveError", "Failed to save Feishu configuration"));
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
      await feishuApi.delete();
      setConfig(null);
      setHasExistingConfig(false);
      setEnabled(false);
      setAppId("");
      setAppSecret("");
      setEncryptKey("");
      setVerificationToken("");
      setReactEmoji("THUMBSUP");
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
      const result = await feishuApi.test();
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
      <div className="flex h-full items-center justify-center bg-stone-50 dark:bg-stone-950">
        <div className="flex flex-col items-center gap-3">
          <div className="relative">
            <div className="absolute inset-0 animate-ping rounded-full bg-stone-400/20" />
            <Loader2 className="relative h-10 w-10 animate-spin text-stone-600 dark:text-stone-400" />
          </div>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            {t("common.loading", "Loading...")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-stone-50 dark:bg-stone-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-stone-200 bg-white/80 backdrop-blur-sm px-4 py-5 dark:border-stone-800 dark:bg-stone-900/80 sm:px-6 lg:px-8 xl:py-6">
        <div className="mx-auto max-w-2xl xl:max-w-3xl 2xl:max-w-4xl">
          <div className="flex items-center gap-3 xl:gap-4">
            {/* Back button */}
            <button
              onClick={() => navigate("/channels")}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200 sm:-ml-3"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-900 shadow-lg dark:bg-stone-100 xl:h-12 xl:w-12">
              <MessageSquare className="h-5 w-5 text-stone-100 dark:text-stone-900 xl:h-6 xl:w-6" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold text-stone-900 dark:text-stone-100 sm:text-2xl xl:text-3xl">
                {t("feishu.title", "Feishu/Lark Channel")}
              </h1>
              <p className="truncate text-sm text-stone-500 dark:text-stone-400 xl:text-base">
                {t(
                  "feishu.description",
                  "Connect your Feishu bot to receive and send messages",
                )}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 xl:py-8 2xl:py-10">
        <div className="mx-auto max-w-2xl xl:max-w-3xl 2xl:max-w-4xl space-y-5 2xl:space-y-6">
          {/* Status Card */}
          {hasExistingConfig && status && (
            <div className="rounded-2xl border border-stone-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm dark:border-stone-800 dark:bg-stone-900/80 2xl:p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  {status.connected ? (
                    <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-green-100 to-emerald-100 dark:from-green-900/50 dark:to-emerald-900/50 2xl:h-12 2xl:w-12">
                      <Check className="h-5 w-5 text-green-600 dark:text-green-400 2xl:h-6 2xl:w-6" />
                    </div>
                  ) : (
                    <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-red-100 to-rose-100 dark:from-red-900/50 dark:to-rose-900/50 2xl:h-12 2xl:w-12">
                      <X className="h-5 w-5 text-red-600 dark:text-red-400 2xl:h-6 2xl:w-6" />
                    </div>
                  )}
                  <div>
                    <span
                      className={`text-sm font-semibold 2xl:text-base ${
                        status.connected
                          ? "text-green-600 dark:text-green-400"
                          : "text-red-600 dark:text-red-400"
                      }`}
                    >
                      {status.connected
                        ? t("feishu.connected", "Connected")
                        : t("feishu.disconnected", "Disconnected")}
                    </span>
                    <p className="text-xs text-stone-500 dark:text-stone-400">
                      {status.connected
                        ? t(
                            "feishu.connectionActive",
                            "Connection is active and working",
                          )
                        : t(
                            "feishu.connectionInactive",
                            "Check your configuration",
                          )}
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleTest}
                  disabled={isTesting || !enabled}
                  className="flex items-center justify-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-2 text-sm font-medium text-stone-600 transition-all hover:border-stone-300 hover:bg-stone-50 disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700 2xl:px-5 2xl:py-2.5"
                >
                  {isTesting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  {t("feishu.testConnection", "Test")}
                </button>
              </div>
              {status.error_message && (
                <div className="mt-4 flex items-start gap-3 rounded-xl bg-gradient-to-r from-red-50 to-rose-50 p-4 dark:from-red-900/20 dark:to-rose-900/20">
                  <AlertCircle className="h-5 w-5 flex-shrink-0 text-red-500 dark:text-red-400" />
                  <span className="text-sm text-red-700 dark:text-red-300">
                    {status.error_message}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Configuration Form */}
          <div className="rounded-2xl border border-stone-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm dark:border-stone-800 dark:bg-stone-900/80 2xl:p-6">
            <h3 className="mb-4 text-sm font-semibold text-stone-900 dark:text-stone-100 2xl:text-base">
              {t("feishu.configuration", "Configuration")}
            </h3>

            <div className="space-y-4 2xl:space-y-5">
              {/* Enable Toggle */}
              <div className="flex items-center justify-between rounded-xl bg-gradient-to-r from-stone-50 to-stone-100/50 px-4 py-3 dark:from-stone-800/50 dark:to-stone-800/30 2xl:px-5 2xl:py-4">
                <div>
                  <label className="text-sm font-medium text-stone-700 dark:text-stone-300 2xl:text-base">
                    {t("feishu.enabled", "Enable Feishu Bot")}
                  </label>
                  <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
                    {t(
                      "feishu.enabledDesc",
                      "Enable or disable this channel integration",
                    )}
                  </p>
                </div>
                <button
                  onClick={() => setEnabled(!enabled)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 2xl:h-7 2xl:w-12 ${
                    enabled
                      ? "bg-stone-900 shadow-sm dark:bg-stone-100"
                      : "bg-stone-200 dark:bg-stone-700"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 rounded-full shadow-sm transition-transform duration-200 2xl:h-5 2xl:w-5 ${
                      enabled
                        ? "translate-x-6 bg-stone-100 dark:translate-x-7 dark:bg-stone-900"
                        : "translate-x-1 bg-white dark:bg-stone-300"
                    }`}
                  />
                </button>
              </div>

              {/* App ID */}
              <div className="space-y-1.5 2xl:space-y-2">
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 2xl:text-base">
                  {t("feishu.appId", "App ID")}{" "}
                  <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={appId}
                  onChange={(e) => setAppId(e.target.value)}
                  placeholder="cli_xxxxxxxxxx"
                  className="w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500 2xl:py-3 2xl:text-base"
                />
              </div>

              {/* App Secret */}
              <div className="space-y-1.5 2xl:space-y-2">
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 2xl:text-base">
                  {t("feishu.appSecret", "App Secret")}{" "}
                  {hasExistingConfig ? (
                    <span className="text-xs text-stone-400 2xl:text-sm">
                      ({t("feishu.leaveEmpty", "leave empty to keep current")})
                    </span>
                  ) : (
                    <span className="text-red-500">*</span>
                  )}
                </label>
                <input
                  type="password"
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                  placeholder={hasExistingConfig ? "••••••••••••" : ""}
                  className="w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500 2xl:py-3 2xl:text-base"
                />
              </div>

              {/* Encrypt Key */}
              <div className="space-y-1.5 2xl:space-y-2">
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 2xl:text-base">
                  {t("feishu.encryptKey", "Encrypt Key")}
                  <span className="ml-1 text-xs text-stone-400 2xl:text-sm">
                    ({t("common.optional", "optional")})
                  </span>
                </label>
                <input
                  type="text"
                  value={encryptKey}
                  onChange={(e) => setEncryptKey(e.target.value)}
                  className="w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500 2xl:py-3 2xl:text-base"
                />
              </div>

              {/* Verification Token */}
              <div className="space-y-1.5 2xl:space-y-2">
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 2xl:text-base">
                  {t("feishu.verificationToken", "Verification Token")}
                  <span className="ml-1 text-xs text-stone-400 2xl:text-sm">
                    ({t("common.optional", "optional")})
                  </span>
                </label>
                <input
                  type="text"
                  value={verificationToken}
                  onChange={(e) => setVerificationToken(e.target.value)}
                  className="w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500 2xl:py-3 2xl:text-base"
                />
              </div>

              {/* React Emoji */}
              <div className="space-y-1.5 2xl:space-y-2">
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 2xl:text-base">
                  {t("feishu.reactEmoji", "Reaction Emoji")}
                </label>
                <select
                  value={reactEmoji}
                  onChange={(e) => setReactEmoji(e.target.value)}
                  className="w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 2xl:py-3 2xl:text-base"
                >
                  <option value="THUMBSUP">👍 Thumbs Up</option>
                  <option value="OK">👌 OK</option>
                  <option value="EYES">👀 Eyes</option>
                  <option value="DONE">✅ Done</option>
                  <option value="HEART">❤️ Heart</option>
                  <option value="FIRE">🔥 Fire</option>
                </select>
              </div>

              {/* Group Policy */}
              <div className="space-y-1.5 2xl:space-y-2">
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 2xl:text-base">
                  {t("feishu.groupPolicy", "Group Message Policy")}
                </label>
                <select
                  value={groupPolicy}
                  onChange={(e) =>
                    setGroupPolicy(e.target.value as "open" | "mention")
                  }
                  className="w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 2xl:py-3 2xl:text-base"
                >
                  <option value="mention">
                    {t(
                      "feishu.groupPolicyMention",
                      "Reply only when @mentioned",
                    )}
                  </option>
                  <option value="open">
                    {t("feishu.groupPolicyOpen", "Reply to all messages")}
                  </option>
                </select>
              </div>
            </div>
          </div>

          {/* Help Card */}
          <div className="rounded-2xl border border-stone-200 bg-gradient-to-br from-stone-50 to-stone-100/50 p-5 shadow-sm dark:border-stone-800 dark:from-stone-900/50 dark:to-stone-800/30 2xl:p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-stone-200 dark:bg-stone-700 2xl:h-10 2xl:w-10">
                <HelpCircle className="h-4 w-4 text-stone-600 dark:text-stone-300 2xl:h-5 2xl:w-5" />
              </div>
              <div className="min-w-0">
                <p className="font-medium text-stone-900 dark:text-stone-100 2xl:text-lg">
                  {t("feishu.setupGuide", "Setup Guide")}
                </p>
                <ol className="mt-2 list-decimal list-inside space-y-1.5 text-sm text-stone-600 dark:text-stone-300 2xl:mt-3 2xl:space-y-2 2xl:text-base">
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
          <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between 2xl:pt-3">
            <button
              onClick={handleDelete}
              disabled={!hasExistingConfig}
              className="flex items-center justify-center gap-2 rounded-xl border border-red-200 bg-white px-4 py-2.5 text-sm font-medium text-red-600 transition-all hover:border-red-300 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/50 dark:bg-stone-900 dark:text-red-400 dark:hover:bg-red-900/20 2xl:px-5 2xl:py-3 2xl:text-base"
            >
              <Trash2 className="h-4 w-4 2xl:h-5 2xl:w-5" />
              {t("common.delete")}
            </button>

            <button
              onClick={handleSave}
              disabled={isSaving || !appId.trim()}
              className="flex items-center justify-center gap-2 rounded-xl bg-stone-900 px-6 py-2.5 text-sm font-medium text-stone-100 shadow-lg transition-all hover:bg-stone-800 disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-200 2xl:px-8 2xl:py-3 2xl:text-base"
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin 2xl:h-5 2xl:w-5" />
              ) : (
                <Save className="h-4 w-4 2xl:h-5 2xl:w-5" />
              )}
              {t("common.save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
