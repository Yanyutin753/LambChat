/**
 * Generic Channel Configuration Panel
 *
 * Dynamically renders channel configuration based on metadata from the backend.
 * Supports multiple channel types (Feishu, WeChat, DingTalk, etc.)
 */
import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { BackIcon } from "../common/BackIcon";
import {
  Save,
  Trash2,
  RefreshCw,
  Check,
  X,
  AlertCircle,
  MessageCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { EditorSidebar } from "../common/EditorSidebar";
import { Button, Input, PanelFooterActions, Select } from "../common";
import { ChannelAgentSelect } from "./channel/ChannelAgentSelect";
import {
  ChannelPluginOptions,
  type ChannelPluginOptionValues,
} from "./channel/ChannelPluginOptions";
import { channelApi } from "../../services/api/channel";
import { useChannelPluginOptions } from "../../hooks/useChannelPluginOptions";
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
  onClose?: () => void;
}

export function ChannelPanel({
  channelType,
  instanceId,
  metadata,
  onClose,
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
  const [channelPluginOptionValues, setChannelPluginOptionValues] =
    useState<ChannelPluginOptionValues>({});
  const { options: channelPluginOptions } = useChannelPluginOptions(channelType, {
    includeInactive: true,
  });

  const setChannelPluginOption = (
    pluginId: string,
    key: string,
    value: unknown,
  ) => {
    setChannelPluginOptionValues((prev) => {
      const next = { ...prev };
      const pluginValues = { ...(next[pluginId] ?? {}) };
      if (value === null || value === undefined || value === "") {
        delete pluginValues[key];
      } else {
        pluginValues[key] = value;
      }
      if (Object.keys(pluginValues).length > 0) {
        next[pluginId] = pluginValues;
      } else {
        delete next[pluginId];
      }
      return next;
    });
  };

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
        setChannelPluginOptionValues(configResponse.plugin_options || {});
      } else {
        setHasExistingConfig(false);
        setEnabled(false);
        setAgentId(null);
        setChannelPluginOptionValues({});
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
          plugin_options: channelPluginOptionValues,
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
          plugin_options: channelPluginOptionValues,
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
      onClose?.();
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
              className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50 ${
                value
                  ? "bg-amber-500 shadow-sm shadow-amber-500/25"
                  : "bg-stone-200 dark:bg-stone-700"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  value ? "translate-x-[18px]" : "translate-x-[3px]"
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
            <Select
              value={String(value)}
              onChange={(v) => updateFormField(field.name, v)}
              options={(field.options ?? []).map((opt) => ({
                value: String(opt.value),
                label: opt.label,
              }))}
            />
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
            <Input
              type="password"
              value={String(value)}
              onChange={(e) => updateFormField(field.name, e.target.value)}
              placeholder={
                field.placeholder ||
                (hasExistingConfig ? t("common.masked") : "")
              }
              className="px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-500 dark:text-stone-100 dark:placeholder-stone-500"
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
            <Input
              type="text"
              value={String(value)}
              onChange={(e) => updateFormField(field.name, e.target.value)}
              placeholder={field.placeholder || ""}
              className="px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-500 dark:text-stone-100 dark:placeholder-stone-500"
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
    return <PanelLoadingState text={t("common.loading", "加载中...")} />;
  }

  // Form content shared between both modes
  const formContent = (
    <div className="space-y-4">
      {/* Status Card */}
      {hasExistingConfig && status && (
        <div className="glass-card rounded-xl p-4">
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
                    ? t("channel.connected", "Connected")
                    : t("channel.disconnected", "Disconnected")}
                </span>
              </div>
            </div>
            <Button
              onClick={handleTest}
              disabled={isTesting || !enabled}
              loading={isTesting}
              leftIcon={<RefreshCw size={14} />}
              size="sm"
            >
              {t("channel.testConnection", "Test")}
            </Button>
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
      <div className="glass-card rounded-xl p-4">
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
              <Input
                type="text"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
                placeholder={t(
                  "channel.instanceNamePlaceholder",
                  "e.g., My Work Bot",
                )}
                className="px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-500 dark:text-stone-100 dark:placeholder-stone-500"
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
                {t("channel.enabledDesc", "Enable or disable this channel")}
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

          {/* Dynamic Fields */}
          {metadata.config_fields.map(renderField)}

          {/* Agent Selector */}
          <ChannelAgentSelect value={agentId} onChange={setAgentId} />

          {/* Plugin-declared channel options */}
          <ChannelPluginOptions
            options={channelPluginOptions}
            values={channelPluginOptionValues}
            disabled={!canWrite}
            onChange={setChannelPluginOption}
          />
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
    </div>
  );

  // Action buttons
  const actionButtons = (
    <PanelFooterActions align={canDelete ? "between" : "end"} className="pt-2">
      {canDelete && (
        <Button
          variant="danger"
          onClick={handleDeleteClick}
          disabled={!hasExistingConfig}
          leftIcon={<Trash2 size={16} />}
        >
          {t("common.delete")}
        </Button>
      )}
      {canWrite && (
        <Button
          variant="primary"
          onClick={handleSave}
          loading={isSaving}
          leftIcon={<Save size={16} />}
        >
          {t("common.save")}
        </Button>
      )}
    </PanelFooterActions>
  );

  const deleteDialog = (
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
  );

  // Sidebar mode: render inside EditorSidebar
  if (onClose) {
    return (
      <>
        <EditorSidebar
          open={true}
          onClose={onClose}
          title={
            hasExistingConfig
              ? instanceName || metadata.display_name
              : t("channel.newInstance", "New Instance")
          }
          subtitle={metadata.description}
          icon={getChannelIcon()}
          footer={actionButtons}
        >
          {formContent}
        </EditorSidebar>
        {deleteDialog}
      </>
    );
  }

  // Full-page mode (backward compatible)
  return (
    <>
      <div className="glass-shell flex h-full flex-col min-h-0">
        {/* Header */}
        <PanelHeader
          title={metadata.display_name}
          subtitle={t("channel.description")}
          icon={getChannelIcon()}
          actions={
            <Button
              onClick={() => navigate("/channels")}
              leftIcon={<BackIcon size={16} />}
            >
              <span className="hidden sm:inline">{t("common.back")}</span>
            </Button>
          }
        />
        <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
          {formContent}
        </div>
        <div className="border-t border-[var(--theme-border)] px-3 py-3 sm:px-4">
          {actionButtons}
        </div>
      </div>
      {deleteDialog}
    </>
  );
}
