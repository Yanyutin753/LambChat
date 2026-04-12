/**
 * Generic Channel Configuration Panel
 *
 * Dynamically renders channel configuration based on metadata from the backend.
 * Supports multiple channel types (Feishu, WeChat, DingTalk, etc.)
 */
import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Save,
  Trash2,
  RefreshCw,
  Check,
  X,
  AlertCircle,
  ArrowLeft,
  MessageCircle,
  ChevronDown,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ChannelAgentSelect } from "./channel/ChannelAgentSelect";
import { channelApi } from "../../services/api/channel";
import type {
  ChannelType,
  ChannelMetadata,
  ChannelConfigResponse,
  ChannelConfigStatus,
  ConfigField,
} from "../../types/channel";

interface ChannelPanelProps {
  channelType: ChannelType;
  instanceId: string;
  metadata: ChannelMetadata;
}

export function ChannelPanel({
  channelType,
  instanceId,
  metadata,
}: ChannelPanelProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const navigate = useNavigate();

  const canWrite = hasPermission(Permission.CHANNEL_WRITE);
  const canDelete = hasPermission(Permission.CHANNEL_DELETE);

  const isNewInstance = instanceId === "new";

  // State
  const [status, setStatus] = useState<ChannelConfigStatus | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_config, setConfig] = useState<ChannelConfigResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [instanceName, setInstanceName] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [hasExistingConfig, setHasExistingConfig] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [agentId, setAgentId] = useState<string | null>(null);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      if (isNewInstance) {
        // New instance - don't load anything
        setHasExistingConfig(false);
        setEnabled(false);
        const defaults: Record<string, unknown> = {};
        metadata.config_fields.forEach((field) => {
          if (field.default !== undefined) {
            defaults[field.name] = field.default;
          }
        });
        setFormValues(defaults);
        setIsLoading(false);
        return;
      }

      const [configResponse, statusResponse] = await Promise.all([
        channelApi.get(channelType, instanceId),
        channelApi.getStatus(channelType, instanceId),
      ]);

      if (configResponse) {
        setConfig(configResponse);
        setHasExistingConfig(true);
        setEnabled(configResponse.enabled);
        setInstanceName(configResponse.name);
        setFormValues(configResponse.config || {});
        setAgentId(configResponse.agent_id || null);
      } else {
        setHasExistingConfig(false);
        setEnabled(false);
        setAgentId(null);
        const defaults: Record<string, unknown> = {};
        metadata.config_fields.forEach((field) => {
          if (field.default !== undefined) {
            defaults[field.name] = field.default;
          }
        });
        setFormValues(defaults);
      }

      setStatus(statusResponse);
    } catch (error) {
      console.error(`Failed to load ${channelType} config:`, error);
      toast.error(
        t("channel.loadError", "Failed to load channel configuration"),
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Load config on mount
  useEffect(() => {
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelType, instanceId]);

  // Initialize form defaults from metadata
  useEffect(() => {
    const defaults: Record<string, unknown> = {};
    metadata.config_fields.forEach((field) => {
      if (field.default !== undefined) {
        defaults[field.name] = field.default;
      }
    });
    setFormValues((prev) => ({ ...defaults, ...prev }));
  }, [metadata]);

  const requiredFields = useMemo(() => {
    return metadata.config_fields.filter((f) => f.required);
  }, [metadata.config_fields]);

  const validateForm = (): boolean => {
    for (const field of requiredFields) {
      const value = formValues[field.name];
      if (value === undefined || value === "" || value === null) {
        if (hasExistingConfig && field.sensitive) continue;
        toast.error(t("channel.fieldRequired", `${field.title} is required`));
        return false;
      }
    }
    return true;
  };

  const handleSave = async () => {
    if (!validateForm()) return;

    setIsSaving(true);
    try {
      const configData: Record<string, unknown> = {};
      for (const field of metadata.config_fields) {
        const value = formValues[field.name];
        if (hasExistingConfig && field.sensitive && !value) {
          continue;
        }
        configData[field.name] = value;
      }

      if (hasExistingConfig) {
        const updated = await channelApi.update(channelType, instanceId, {
          config: configData,
          enabled,
          agent_id: agentId,
        });
        setConfig(updated);
        const cleared = { ...formValues };
        metadata.config_fields
          .filter((f) => f.sensitive)
          .forEach((f) => {
            cleared[f.name] = "";
          });
        setFormValues(cleared);
      } else {
        if (!instanceName.trim()) {
          toast.error(t("channel.nameRequired", "Instance name is required"));
          setIsSaving(false);
          return;
        }
        const created = await channelApi.create({
          channel_type: channelType,
          name: instanceName.trim(),
          config: configData,
          agent_id: agentId,
        });
        setConfig(created);
        setHasExistingConfig(true);
        // Navigate to the new instance - don't fetch status here, it will be fetched after navigation
        navigate(`/channels/${channelType}/${created.instance_id}`, {
          replace: true,
        });
        const cleared = { ...formValues };
        metadata.config_fields
          .filter((f) => f.sensitive)
          .forEach((f) => {
            cleared[f.name] = "";
          });
        setFormValues(cleared);
        // Return early to avoid calling getStatus with "new" instanceId
        setIsSaving(false);
        toast.success(t("channel.saveSuccess", "Configuration saved"));
        return;
      }

      toast.success(t("channel.saveSuccess", "Configuration saved"));

      const newStatus = await channelApi.getStatus(channelType, instanceId);
      setStatus(newStatus);
    } catch (error) {
      console.error(`Failed to save ${channelType} config:`, error);
      const errorMessage =
        error instanceof Error
          ? error.message
          : t("channel.saveError", "Failed to save configuration");
      toast.error(errorMessage);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      await channelApi.delete(channelType, instanceId);
      toast.success(t("channel.deleteSuccess", "Configuration deleted"));
      // Navigate back to instance list
      navigate(`/channels/${channelType}`);
    } catch (error) {
      console.error(`Failed to delete ${channelType} config:`, error);
      toast.error(t("channel.deleteError", "Failed to delete configuration"));
    }
  };

  const handleDeleteClick = () => {
    setShowDeleteConfirm(true);
  };

  const handleTest = async () => {
    setIsTesting(true);
    try {
      const result = await channelApi.test(channelType, instanceId);
      if (result.success) {
        toast.success(
          result.message || t("channel.testSuccess", "Connection successful"),
        );
      } else {
        toast.error(
          result.message || t("channel.testFailed", "Connection failed"),
        );
      }
    } catch (error) {
      console.error(`Failed to test ${channelType} connection:`, error);
      toast.error(t("channel.testError", "Failed to test connection"));
    } finally {
      setIsTesting(false);
    }
  };

  const updateFormField = (name: string, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [name]: value }));
  };

  const renderField = (field: ConfigField) => {
    const value = formValues[field.name] ?? "";

    switch (field.type) {
      case "toggle":
        return (
          <div
            key={field.name}
            className="flex items-center justify-between rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-2.5"
          >
            <div>
              <span className="text-sm font-medium text-stone-700 dark:text-stone-200">
                {field.title}
              </span>
              {field.description && (
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {field.description}
                </p>
              )}
            </div>
            <button
              onClick={() => updateFormField(field.name, !value)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                value ? "bg-stone-900" : "bg-stone-200 dark:bg-stone-600"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 rounded-full bg-[var(--theme-bg-card)] shadow-sm transition-transform ${
                  value ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
        );

      case "select":
        return (
          <div key={field.name}>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-200">
              {field.title}
            </label>
            <div className="relative">
              <select
                value={String(value)}
                onChange={(e) => updateFormField(field.name, e.target.value)}
                className="w-full appearance-none rounded-lg glass-input pl-3 pr-9 py-2 text-sm text-stone-900 focus:border-stone-500 focus:outline-none dark:text-stone-100"
              >
                {field.options?.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={16}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
              />
            </div>
          </div>
        );

      case "password":
        return (
          <div key={field.name}>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-200">
              {field.title}{" "}
              {field.required && !hasExistingConfig && (
                <span className="text-red-500">*</span>
              )}
              {hasExistingConfig && field.sensitive && (
                <span className="ml-1 text-xs text-stone-400">
                  ({t("channel.leaveEmpty")})
                </span>
              )}
            </label>
            <input
              type="password"
              value={String(value)}
              onChange={(e) => updateFormField(field.name, e.target.value)}
              placeholder={
                field.placeholder ||
                (hasExistingConfig ? t("common.masked") : "")
              }
              className="w-full rounded-lg glass-input px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-500 focus:outline-none dark:text-stone-100 dark:placeholder-stone-500"
            />
          </div>
        );

      default:
        return (
          <div key={field.name}>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-200">
              {field.title}
              {field.required && (!hasExistingConfig || !field.sensitive) && (
                <span className="text-red-500"> *</span>
              )}
            </label>
            <input
              type="text"
              value={String(value)}
              onChange={(e) => updateFormField(field.name, e.target.value)}
              placeholder={field.placeholder || ""}
              className="w-full rounded-lg glass-input px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-500 focus:outline-none dark:text-stone-100 dark:placeholder-stone-500"
            />
          </div>
        );
    }
  };

  // Get icon based on channel type
  const getChannelIcon = () => {
    switch (channelType) {
      case "wechat":
        return (
          <MessageCircle
            size={18}
            className="text-stone-600 dark:text-stone-400"
          />
        );
      default:
        return (
          <MessageCircle
            size={18}
            className="text-stone-600 dark:text-stone-400"
          />
        );
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
        <LoadingSpinner size="sm" />
        <span className="ml-2">{t("common.loading")}</span>
      </div>
    );
  }

  return (
    <>
      <div className="glass-shell flex h-full flex-col min-h-0">
        {/* Header */}
        <PanelHeader
          title={metadata.display_name}
          subtitle={t("channel.description")}
          icon={getChannelIcon()}
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
          <div className="space-y-4">
            {/* Status Card */}
            {hasExistingConfig && status && (
              <div className="glass-card rounded-xl p-4 ">
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
                        <X
                          size={16}
                          className="text-red-600 dark:text-red-400"
                        />
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
                          ? t("channel.connected", "Connected")
                          : t("channel.disconnected", "Disconnected")}
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
                    {t("channel.testConnection", "Test")}
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

            {/* Configuration Card */}
            <div className="glass-card rounded-xl p-4 ">
              <h3 className="mb-4 text-sm font-semibold text-stone-900 dark:text-stone-100">
                {t("channel.configuration", "Configuration")}
              </h3>

              <div className="space-y-4">
                {/* Instance Name - only show for new instances */}
                {isNewInstance && (
                  <div>
                    <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-200">
                      {t("channel.instanceName", "Instance Name")}{" "}
                      <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={instanceName}
                      onChange={(e) => setInstanceName(e.target.value)}
                      placeholder={t(
                        "channel.instanceNamePlaceholder",
                        "e.g., My Work Bot",
                      )}
                      className="w-full rounded-lg glass-input px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-500 focus:outline-none dark:text-stone-100 dark:placeholder-stone-500"
                    />
                  </div>
                )}

                {/* Instance Name Display - show for existing instances */}
                {!isNewInstance && hasExistingConfig && (
                  <div className="rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-2.5">
                    <span className="text-sm font-medium text-stone-700 dark:text-stone-200">
                      {t("channel.instanceName", "Instance Name")}
                    </span>
                    <p className="text-sm text-stone-900 dark:text-stone-100">
                      {instanceName}
                    </p>
                  </div>
                )}

                {/* Enable Toggle */}
                <div className="flex items-center justify-between rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-2.5">
                  <div>
                    <span className="text-sm font-medium text-stone-700 dark:text-stone-200">
                      {t("channel.enabled", "Enable Channel")}
                    </span>
                    <p className="text-xs text-stone-500 dark:text-stone-400">
                      {t(
                        "channel.enabledDesc",
                        "Enable or disable this channel",
                      )}
                    </p>
                  </div>
                  <button
                    onClick={() => setEnabled(!enabled)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                      enabled
                        ? "bg-stone-900"
                        : "bg-stone-200 dark:bg-stone-600"
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 rounded-full bg-[var(--theme-bg-card)] shadow-sm transition-transform ${
                        enabled ? "translate-x-4" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </div>

                {/* Dynamic Fields */}
                {metadata.config_fields.map(renderField)}

                {/* Agent Selector */}
                <ChannelAgentSelect value={agentId} onChange={setAgentId} />
              </div>
            </div>

            {/* Help Card */}
            {metadata.setup_guide.length > 0 && (
              <div className="glass-card-subtle rounded-xl p-4">
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-stone-900 dark:text-stone-100">
                      {t("channel.setupGuide", "Setup Guide")}
                    </p>
                    <ol className="mt-2 list-decimal list-outside ml-4 space-y-1 text-sm text-stone-600 dark:text-stone-300">
                      {metadata.setup_guide.map((step, index) => (
                        <li key={index} className="leading-relaxed">
                          {step}
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:items-center sm:justify-between">
              {canDelete && (
                <button
                  onClick={handleDeleteClick}
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
                  disabled={isSaving}
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
          </div>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        title={t("channel.deleteTitle", "Delete Channel Instance")}
        message={t(
          "channel.deleteConfirmMessage",
          `Are you sure you want to delete "${instanceName}"? This action cannot be undone.`,
        )}
        confirmText={t("common.delete", "Delete")}
        cancelText={t("common.cancel", "Cancel")}
        variant="danger"
        onConfirm={() => {
          setShowDeleteConfirm(false);
          handleDelete();
        }}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}
