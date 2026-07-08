import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import QRCode from "qrcode";
import { BackIcon } from "../../../common/BackIcon";
import { BotMessageSquare, Save, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../../hooks/useAuth";
import { Permission } from "../../../../types";
import { PanelHeader } from "../../../common/PanelHeader";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ChannelConfigSkeleton } from "../../../skeletons";
import { EditorSidebar } from "../../../common/EditorSidebar";
import { channelApi } from "../../../../services/api/channel";
import {
  importLegacyPayloadPluginOptions,
  filterPluginOptionsByVisibleWhen,
  hasEffectiveCorePersonaSuppressingOption,
  pluginOptionsFromMetadata,
  retainPluginOptionsForDeclarations,
  withPluginOption,
} from "../../../../extensions/pluginOptions";
import { useChannelPluginOptions } from "../../../../hooks/useChannelPluginOptions";
import {
  DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
  PREDEFINED_EMOJIS,
} from "./constants";
import { FeishuPanelForm } from "./FeishuPanelForm";
import type {
  FeishuConfigResponse,
  FeishuConfigStatus,
  FeishuPanelProps,
} from "./types";
import type { ChannelPluginOptionValues } from "../ChannelPluginOptions";
import type { ExtensionScopedOption } from "../../../../types";

function pluginOptionsForChannelConfig(
  config: Record<string, unknown>,
  declarations: readonly ExtensionScopedOption[],
): ChannelPluginOptionValues {
  const imported = importLegacyPayloadPluginOptions(
    config,
    declarations,
    pluginOptionsFromMetadata(config),
  );
  return retainPluginOptionsForDeclarations(imported, declarations);
}

function channelOptionsForAgent(
  declarations: readonly ExtensionScopedOption[],
  agentId: string | null,
): readonly ExtensionScopedOption[] {
  return filterPluginOptionsByVisibleWhen(declarations, {
    agentId,
    route: "/channels/feishu",
    scope: "channel",
  });
}

function corePersonaPresetForChannelConfig(
  config: { persona_preset_id?: string | null },
  declarations: readonly ExtensionScopedOption[],
  agentId: string | null,
): string | null {
  return hasEffectiveCorePersonaSuppressingOption(
    channelOptionsForAgent(declarations, agentId),
  )
    ? null
    : config.persona_preset_id || null;
}

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
  const [streamReply, setStreamReply] = useState(true);
  const [autoTranscribeAudio, setAutoTranscribeAudio] = useState(true);
  const [audioTranscribePrompt, setAudioTranscribePrompt] = useState(
    DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
  );
  const [agentId, setAgentId] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [channelPluginOptionValues, setChannelPluginOptionValues] =
    useState<ChannelPluginOptionValues>({});
  const [personaPresetId, setPersonaPresetId] = useState<string | null>(null);
  const { options: channelPluginOptions } = useChannelPluginOptions("feishu", {
    includeInactive: true,
  });
  const [registrationSessionId, setRegistrationSessionId] = useState<
    string | null
  >(null);
  const [registrationStatus, setRegistrationStatus] = useState("");
  const [registrationQrUrl, setRegistrationQrUrl] = useState<string | null>(
    null,
  );
  const [registrationQrDataUrl, setRegistrationQrDataUrl] = useState<
    string | null
  >(null);
  const [isRegistering, setIsRegistering] = useState(false);
  const [credentialMode, setCredentialMode] = useState<"scan" | "manual">(
    "scan",
  );

  // Track if config exists
  const [hasExistingConfig, setHasExistingConfig] = useState(false);
  const activeChannelPluginOptions = filterPluginOptionsByVisibleWhen(
    channelPluginOptions,
    {
      agentId,
      route: "/channels/feishu",
      scope: "channel",
    },
  );

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
      setStreamReply(feishuConfig?.stream_reply ?? true);
      setAutoTranscribeAudio(feishuConfig?.auto_transcribe_audio ?? true);
      setAudioTranscribePrompt(
        feishuConfig?.audio_transcribe_prompt ||
          DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
      );
      setCredentialMode("manual");
      const initialAgentId = initialConfig.agent_id || null;
      setAgentId(initialAgentId);
      setModelId(initialConfig.model_id || null);
      setChannelPluginOptionValues(
        pluginOptionsForChannelConfig({ ...initialConfig }, channelPluginOptions),
      );
      setPersonaPresetId(
        corePersonaPresetForChannelConfig(
          { ...initialConfig },
          channelPluginOptions,
          initialAgentId,
        ),
      );

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
      setStreamReply(true);
      setAutoTranscribeAudio(true);
      setAudioTranscribePrompt(DEFAULT_AUDIO_TRANSCRIBE_PROMPT);
      setCredentialMode("scan");
      setAgentId(null);
      setModelId(null);
      setChannelPluginOptionValues({});
      setPersonaPresetId(null);
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
        setStreamReply(true);
        setAutoTranscribeAudio(true);
        setAudioTranscribePrompt(DEFAULT_AUDIO_TRANSCRIBE_PROMPT);
        setCredentialMode("scan");
        setStatus(null);
        setAgentId(null);
        setModelId(null);
        setChannelPluginOptionValues({});
        setPersonaPresetId(null);
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
        setStreamReply(feishuConfig.stream_reply ?? true);
        setAutoTranscribeAudio(feishuConfig.auto_transcribe_audio ?? true);
        setAudioTranscribePrompt(
          feishuConfig.audio_transcribe_prompt ||
            DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
        );
        setCredentialMode("manual");
        const loadedAgentId = configResponse.agent_id || null;
        setAgentId(loadedAgentId);
        setModelId(configResponse.model_id || null);
        setChannelPluginOptionValues(
          pluginOptionsForChannelConfig({ ...configResponse }, channelPluginOptions),
        );
        setPersonaPresetId(
          corePersonaPresetForChannelConfig(
            { ...configResponse },
            channelPluginOptions,
            loadedAgentId,
          ),
        );

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
        setStreamReply(true);
        setAutoTranscribeAudio(true);
        setAudioTranscribePrompt(DEFAULT_AUDIO_TRANSCRIBE_PROMPT);
        setCredentialMode("scan");
        setAgentId(null);
        setModelId(null);
        setChannelPluginOptionValues({});
        setPersonaPresetId(null);
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

  const handleAgentIdChange = (value: string | null) => {
    setAgentId(value);
    const nextOptions = filterPluginOptionsByVisibleWhen(channelPluginOptions, {
      agentId: value,
      route: "/channels/feishu",
      scope: "channel",
    });
    setChannelPluginOptionValues((current) =>
      retainPluginOptionsForDeclarations(current, nextOptions),
    );
    if (
      nextOptions.some(
        (option) =>
          option.effective !== false && option.suppresses_core_persona_selector,
      )
    ) {
      setPersonaPresetId(null);
    }
  };

  const handleChannelPluginOptionChange = (
    pluginId: string,
    key: string,
    value: unknown,
  ) => {
    setChannelPluginOptionValues(
      (current) =>
        withPluginOption({ plugin_options: current }, pluginId, key, value)
          .plugin_options ?? {},
    );
  };

  useEffect(() => {
    if (!registrationSessionId) {
      return;
    }

    let completed = false;
    const interval = window.setInterval(async () => {
      try {
        const result = await channelApi.getFeishuRegistration(
          registrationSessionId,
        );
        setRegistrationStatus(result.status);
        setRegistrationQrUrl(result.qr_url || null);

        if (result.status === "success" && result.app_id && result.app_secret) {
          completed = true;
          setAppId(result.app_id);
          setAppSecret(result.app_secret);
          setIsRegistering(false);
          setRegistrationSessionId(null);
          toast.success(
            t("feishu.registrationSuccess", "Feishu app credentials received"),
          );
        } else if (["error", "expired", "cancelled"].includes(result.status)) {
          completed = true;
          setIsRegistering(false);
          setRegistrationSessionId(null);
          toast.error(
            result.error ||
              t("feishu.registrationFailed", "Feishu registration failed"),
          );
        }
      } catch (error) {
        console.error("Failed to poll Feishu registration:", error);
        setIsRegistering(false);
        setRegistrationSessionId(null);
      }
    }, 2000);

    return () => {
      window.clearInterval(interval);
      if (!completed) {
        void channelApi
          .cancelFeishuRegistration(registrationSessionId)
          .catch((error) => {
            console.error("Failed to cancel Feishu registration:", error);
          });
      }
    };
  }, [registrationSessionId, t]);

  useEffect(() => {
    if (!registrationQrUrl) {
      setRegistrationQrDataUrl(null);
      return;
    }

    let cancelled = false;
    QRCode.toDataURL(registrationQrUrl, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 220,
      color: {
        dark: "#111827",
        light: "#ffffff",
      },
    })
      .then((dataUrl) => {
        if (!cancelled) {
          setRegistrationQrDataUrl(dataUrl);
        }
      })
      .catch((error) => {
        console.error("Failed to render Feishu registration QR:", error);
        if (!cancelled) {
          setRegistrationQrDataUrl(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [registrationQrUrl]);

  const handleStartRegistration = async () => {
    setCredentialMode("scan");
    setIsRegistering(true);
    setRegistrationQrUrl(null);
    setRegistrationQrDataUrl(null);
    setRegistrationStatus("pending");
    try {
      const session = await channelApi.startFeishuRegistration();
      setRegistrationSessionId(session.session_id);
      setRegistrationStatus(session.status);
      setRegistrationQrUrl(session.qr_url || null);
    } catch (error) {
      console.error("Failed to start Feishu registration:", error);
      setIsRegistering(false);
      toast.error(t("feishu.registrationFailed", "Feishu registration failed"));
    }
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
      const effectiveChannelPluginOptions = activeChannelPluginOptions.filter(
        (option) => option.effective !== false,
      );
      const nextChannelPluginOptions = retainPluginOptionsForDeclarations(
        channelPluginOptionValues,
        activeChannelPluginOptions,
      );
      const suppressesCorePersonaSelector = effectiveChannelPluginOptions.some(
        (option) => option.suppresses_core_persona_selector,
      );
      const channelPersonaPresetId = suppressesCorePersonaSelector
        ? null
        : personaPresetId;

      if (hasExistingConfig) {
        const updateData: Record<string, unknown> = {
          app_id: appId,
          react_emoji: emojiValue,
          group_policy: groupPolicy,
          stream_reply: streamReply,
          auto_transcribe_audio: autoTranscribeAudio,
          audio_transcribe_prompt: audioTranscribePrompt,
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
          enabled,
          agent_id: agentId,
          model_id: modelId,
          plugin_options: nextChannelPluginOptions,
          persona_preset_id: channelPersonaPresetId,
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
            stream_reply: streamReply,
            auto_transcribe_audio: autoTranscribeAudio,
            audio_transcribe_prompt: audioTranscribePrompt,
          },
          agent_id: agentId,
          model_id: modelId,
          plugin_options: nextChannelPluginOptions,
          persona_preset_id: channelPersonaPresetId,
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
      setStreamReply(true);
      setAutoTranscribeAudio(true);
      setAudioTranscribePrompt(DEFAULT_AUDIO_TRANSCRIBE_PROMPT);
      setCredentialMode("scan");
      setAgentId(null);
      setModelId(null);
      setChannelPluginOptionValues({});
      setPersonaPresetId(null);
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
    return <ChannelConfigSkeleton />;
  }

  const formContent = (
    <FeishuPanelForm
      t={t}
      hasExistingConfig={hasExistingConfig}
      status={status}
      enabled={enabled}
      isTesting={isTesting}
      canWrite={canWrite}
      instanceName={instanceName}
      appId={appId}
      appSecret={appSecret}
      encryptKey={encryptKey}
      verificationToken={verificationToken}
      reactEmoji={reactEmoji}
      customEmoji={customEmoji}
      useCustomEmoji={useCustomEmoji}
      groupPolicy={groupPolicy}
      streamReply={streamReply}
      autoTranscribeAudio={autoTranscribeAudio}
      audioTranscribePrompt={audioTranscribePrompt}
      agentId={agentId}
      modelId={modelId}
      channelPluginOptions={channelPluginOptions}
      channelPluginOptionValues={channelPluginOptionValues}
      personaPresetId={personaPresetId}
      credentialMode={credentialMode}
      registrationStatus={registrationStatus}
      registrationQrUrl={registrationQrUrl}
      registrationQrDataUrl={registrationQrDataUrl}
      isRegistering={isRegistering}
      setInstanceName={setInstanceName}
      setEnabled={setEnabled}
      setAppId={setAppId}
      setAppSecret={setAppSecret}
      setEncryptKey={setEncryptKey}
      setVerificationToken={setVerificationToken}
      setReactEmoji={setReactEmoji}
      setCustomEmoji={setCustomEmoji}
      setUseCustomEmoji={setUseCustomEmoji}
      setGroupPolicy={setGroupPolicy}
      setStreamReply={setStreamReply}
      setAutoTranscribeAudio={setAutoTranscribeAudio}
      setAudioTranscribePrompt={setAudioTranscribePrompt}
      onAgentIdChange={handleAgentIdChange}
      setModelId={setModelId}
      setChannelPluginOption={handleChannelPluginOptionChange}
      setPersonaPresetId={setPersonaPresetId}
      setCredentialMode={setCredentialMode}
      handleStartRegistration={handleStartRegistration}
      handleTest={handleTest}
    />
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
          <BotMessageSquare
            size={20}
            className="text-[#3370ff] dark:text-[#7aa2ff]"
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
          <BotMessageSquare
            size={20}
            className="text-[#3370ff] dark:text-[#7aa2ff]"
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
