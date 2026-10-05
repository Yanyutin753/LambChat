/**
 * Generic Channel Configuration Panel
 *
 * Dynamically renders channel configuration based on metadata from the backend.
 * Supports multiple channel types (Feishu, WeChat, DingTalk, etc.)
 */
import { useState, useEffect, useMemo, useId, useRef } from "react";
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
import { ToggleSwitch } from "./AgentPanel/shared";
import { ConfigPanelErrorCallout } from "./ConfigPanelErrorCallout";
import { EmptyState } from "../common/EmptyState";
import { WeixinQrLogin } from "./channel/weixin/WeixinQrLogin";
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
  onClose?: () => void;
}

export function ChannelPanel({
  channelType,
  instanceId,
  metadata,
  onClose,
}: ChannelPanelProps) {
  const { t } = useTranslation();
  const formId = useId();
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);
  const loadGeneration = useRef(0);
  const pageRef = useRef<HTMLDivElement>(null);
  const [statusRefreshError, setStatusRefreshError] = useState(false);
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false);
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
    const generation = ++loadGeneration.current;
    setIsLoading(true);
    setLoadError(false);
    setSaveError(null);
    setStatusRefreshError(false);
    setIsRefreshingStatus(false);
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
      if (generation !== loadGeneration.current) return;

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
      if (generation === loadGeneration.current) setLoadError(true);
    } finally {
      if (generation === loadGeneration.current) setIsLoading(false);
    }
  };

  // Load config on mount
  useEffect(() => {
    const generationRef = loadGeneration;
    loadConfig();
    return () => {
      generationRef.current++;
    };
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
        const message = t(
          "channel.fieldRequired",
          `${field.title} is required`,
        );
        setSaveError(message);
        return false;
      }
    }
    return true;
  };

  const handleSave = async () => {
    setSaveError(null);
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
          const message = t(
            "channel.nameRequired",
            "Instance name is required",
          );
          setSaveError(message);
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

      await refreshStatus();
    } catch (error) {
      console.error(`Failed to save ${channelType} config:`, error);
      const errorMessage =
        error instanceof Error
          ? error.message
          : t("channel.saveError", "Failed to save configuration");
      setSaveError(errorMessage);
    } finally {
      setIsSaving(false);
    }
  };

  const refreshStatus = async () => {
    const generation = loadGeneration.current;
    setIsRefreshingStatus(true);
    try {
      const nextStatus = await channelApi.getStatus(channelType, instanceId);
      if (generation !== loadGeneration.current) return;
      setStatus(nextStatus);
      setStatusRefreshError(false);
    } catch {
      if (generation === loadGeneration.current) setStatusRefreshError(true);
    } finally {
      if (generation === loadGeneration.current) setIsRefreshingStatus(false);
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
    setSaveError(null);
    try {
      const result = await channelApi.test(channelType, instanceId);
      if (result.success) {
        toast.success(
          result.message || t("channel.testSuccess", "Connection successful"),
        );
      } else {
        setSaveError(
          result.message || t("channel.testFailed", "Connection failed"),
        );
      }
    } catch (error) {
      console.error(`Failed to test ${channelType} connection:`, error);
      setSaveError(t("channel.testError", "Failed to test connection"));
    } finally {
      setIsTesting(false);
    }
  };

  const updateFormField = (name: string, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [name]: value }));
  };

  const renderField = (field: ConfigField) => {
    const value = formValues[field.name] ?? field.default ?? "";

    switch (field.type) {
      case "toggle":
        return (
          <div
            key={field.name}
            className="flex items-center justify-between gap-3 rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-2.5"
          >
            <div>
              <span className="text-14 font-medium font-serif text-stone-700 dark:text-stone-200">
                {field.title}
              </span>
              {field.description && (
                <p className="text-12 text-stone-500 dark:text-stone-400">
                  {field.description}
                </p>
              )}
            </div>
            <ToggleSwitch
              enabled={Boolean(value)}
              onToggle={() => updateFormField(field.name, !value)}
              ariaLabel={field.title}
            />
          </div>
        );

      case "select":
        return (
          <div key={field.name}>
            <label className="mb-1 block text-14 font-medium font-serif text-stone-700 dark:text-stone-200">
              {field.title}
            </label>
            <Select
              ariaLabel={field.title}
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
            <label
              htmlFor={`${formId}-${field.name}`}
              className="mb-1 block text-14 font-medium font-serif text-stone-700 dark:text-stone-200"
            >
              {field.title}{" "}
              {field.required && !hasExistingConfig && (
                <span className="text-red-500">*</span>
              )}
            </label>
            <Input
              id={`${formId}-${field.name}`}
              type="password"
              aria-describedby={
                hasExistingConfig && field.sensitive
                  ? `${formId}-${field.name}-hint`
                  : undefined
              }
              value={String(value)}
              onChange={(e) => updateFormField(field.name, e.target.value)}
              placeholder={
                field.placeholder ||
                (hasExistingConfig ? t("common.masked") : "")
              }
              className="px-3 py-2 text-14 text-stone-900 placeholder-stone-400 focus:border-stone-500 dark:text-stone-100 dark:placeholder-stone-500"
            />
            {hasExistingConfig && field.sensitive && (
              <p
                id={`${formId}-${field.name}-hint`}
                className="mt-1 text-12 text-theme-text-secondary"
              >
                {t("channel.leaveEmpty")}
              </p>
            )}
          </div>
        );

      default:
        return (
          <div key={field.name}>
            <label
              htmlFor={`${formId}-${field.name}`}
              className="mb-1 block text-14 font-medium font-serif text-stone-700 dark:text-stone-200"
            >
              {field.title}
              {field.required && (!hasExistingConfig || !field.sensitive) && (
                <span className="text-red-500"> *</span>
              )}
            </label>
            <Input
              id={`${formId}-${field.name}`}
              type="text"
              value={String(value)}
              onChange={(e) => updateFormField(field.name, e.target.value)}
              placeholder={field.placeholder || ""}
              className="px-3 py-2 text-14 text-stone-900 placeholder-stone-400 focus:border-stone-500 dark:text-stone-100 dark:placeholder-stone-500"
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

  // Form content shared between both modes
  const formContent = isLoading ? (
    <PanelLoadingState text={t("common.loading")} />
  ) : loadError ? (
    <div role="alert" className="flex min-h-full items-center justify-center">
      <EmptyState
        illustration="panel-channels"
        title={t("channel.loadError")}
        action={
          <Button
            onClick={(event) => {
              (
                event.currentTarget.closest<HTMLElement>(
                  "[data-right-panel-root]",
                ) ?? pageRef.current
              )?.focus();
              void loadConfig();
            }}
          >
            {t("common.retry")}
          </Button>
        }
      />
    </div>
  ) : (
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
                  className={`text-14 font-semibold ${
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
              <span className="min-w-0 [overflow-wrap:anywhere] text-14 text-red-700 dark:text-red-300">
                {status.error_message}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Configuration Card */}
      <div className="glass-card rounded-xl p-4">
        <h3 className="mb-4 text-14 font-semibold font-serif text-stone-900 dark:text-stone-100">
          {t("channel.configuration", "Configuration")}
        </h3>

        <div className="space-y-4">
          {/* Instance Name - only show for new instances */}
          {isNewInstance && (
            <div>
              <label
                htmlFor={`${formId}-instanceName`}
                className="mb-1 block text-14 font-medium font-serif text-stone-700 dark:text-stone-200"
              >
                {t("channel.instanceName", "Instance Name")}{" "}
                <span className="text-red-500">*</span>
              </label>
              <Input
                id={`${formId}-instanceName`}
                type="text"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
                placeholder={t(
                  "channel.instanceNamePlaceholder",
                  "e.g., My Work Bot",
                )}
                className="px-3 py-2 text-14 text-stone-900 placeholder-stone-400 focus:border-stone-500 dark:text-stone-100 dark:placeholder-stone-500"
              />
            </div>
          )}

          {/* Instance Name Display - show for existing instances */}
          {!isNewInstance && hasExistingConfig && (
            <div className="rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-2.5">
              <span className="text-14 font-medium font-serif text-stone-700 dark:text-stone-200">
                {t("channel.instanceName", "Instance Name")}
              </span>
              <p className="text-14 text-stone-900 dark:text-stone-100">
                {instanceName}
              </p>
            </div>
          )}

          {/* Enable Toggle */}
          <div className="flex items-center justify-between gap-3 rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-2.5">
            <div>
              <span className="text-14 font-medium font-serif text-stone-700 dark:text-stone-200">
                {t("channel.enabled", "Enable Channel")}
              </span>
              <p className="text-12 text-stone-500 dark:text-stone-400">
                {t("channel.enabledDesc", "Enable or disable this channel")}
              </p>
            </div>
            <ToggleSwitch
              enabled={enabled}
              onToggle={() => setEnabled(!enabled)}
              ariaLabel={t("channel.enabled")}
            />
          </div>

          {/* WeChat iLink: QR login fills bot_token */}
          {channelType === "weixin" && (
            <WeixinQrLogin
              onToken={(token) =>
                setFormValues((prev) => ({ ...prev, bot_token: token }))
              }
            />
          )}

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
              <p className="text-14 font-semibold text-stone-900 dark:text-stone-100">
                {t("channel.setupGuide", "Setup Guide")}
              </p>
              <ol className="mt-2 list-decimal list-outside ml-4 space-y-1 text-14 text-stone-600 dark:text-stone-300">
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
  const actionButtons = !isLoading && !loadError && (
    <>
      {statusRefreshError && (
        <div className="flex items-start gap-2">
          <ConfigPanelErrorCallout
            message={t("common.loadFailed")}
            className="min-w-0 flex-1"
          />
          <Button
            onClick={(event) => {
              (
                event.currentTarget.closest<HTMLElement>(
                  "[data-right-panel-root]",
                ) ?? pageRef.current
              )?.focus();
              void refreshStatus();
            }}
            loading={isRefreshingStatus}
          >
            {t("common.retry")}
          </Button>
        </div>
      )}
      {saveError && (
        <ConfigPanelErrorCallout
          message={saveError}
          tabIndex={0}
          className="max-h-32 overflow-y-auto"
        />
      )}
      <PanelFooterActions
        align={canDelete ? "between" : "end"}
        className="pt-2"
      >
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
    </>
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
            isNewInstance
              ? t("channel.newInstance", "New Instance")
              : instanceName || metadata.display_name
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
      <div
        ref={pageRef}
        tabIndex={-1}
        className="glass-shell flex h-full flex-col min-h-0"
      >
        {/* Header */}
        <PanelHeader
          title={metadata.display_name}
          subtitle={t("channel.description")}
          illustration="panel-channels"
          actions={
            <Button
              onClick={() => navigate("/channels")}
              leftIcon={<BackIcon size={16} />}
            >
              <span className="hidden sm:inline">{t("common.back")}</span>
            </Button>
          }
        />
        <div className="panel-body flex-1 overflow-y-auto">{formContent}</div>
        <div className="border-t border-[var(--theme-border)] px-3 py-3 sm:px-4">
          {actionButtons}
        </div>
      </div>
      {deleteDialog}
    </>
  );
}
