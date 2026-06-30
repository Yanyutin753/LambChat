import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  CalendarClock,
  Pencil,
  Plus,
  Save,
  Timer,
  UserRound,
} from "lucide-react";
import {
  Button,
  Input,
  PanelFooterActions,
  Select,
  Textarea,
} from "../../common";
import { EditorSidebar } from "../../common/EditorSidebar";
import { ToggleSwitch } from "../AgentPanel/shared";
import type {
  ScheduledTask,
  ScheduledTaskCreate,
  TriggerType,
} from "../../../types/scheduledTask";
import type { AgentInfo } from "../../../types/agent";
import type { AvailableModel } from "../../../contexts/SettingsContext";
import type { PersonaPreset } from "../../../types/personaPreset";
import { personaPresetApi } from "../../../services/api/personaPreset";
import { useScheduledTaskPluginOptions } from "../../../hooks/useScheduledTaskPluginOptions";
import {
  hasEffectiveCorePersonaSuppressingOption,
  importLegacyPayloadPluginOptions,
  pluginOptionFromValues,
  pluginOptionsFromMetadata,
  retainPluginOptionsForDeclarations,
  withPluginOption,
} from "../../../extensions/pluginOptions";
import type { PluginOptionsMetadata } from "../../../extensions/pluginOptions";
import {
  buildScheduledTaskInputPayload,
  getAgentOptionsFromScheduledTaskPayload,
  getScheduledTaskPersonaPresetId,
} from "../scheduledTaskPayload";
import { getBrowserTimezone, toDateTimeLocalValue } from "./utils";
import {
  renderScheduledTaskOptionField,
} from "./scheduledTaskOptionRenderers";
import type { ExtensionScopedOption } from "../../../types";

function asInputValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : String(value);
}

function parseJsonValue(value: string): unknown {
  if (!value.trim()) return null;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function optionInputType(option: ExtensionScopedOption): "text" | "number" {
  return option.type === "number" ? "number" : "text";
}

/** Create/Edit form sidebar */
export function TaskFormModal({
  task,
  agents,
  availableModels,
  defaultAgentId,
  defaultModelId,
  defaultModelValue,
  onSave,
  onClose,
}: {
  task: ScheduledTask | null;
  agents: AgentInfo[];
  availableModels: AvailableModel[] | null;
  defaultAgentId?: string;
  defaultModelId?: string;
  defaultModelValue?: string;
  onSave: (data: ScheduledTaskCreate) => Promise<void>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const isEdit = !!task;
  const taskAgentOptions = getAgentOptionsFromScheduledTaskPayload(
    task?.input_payload,
  );
  const initialModelId =
    (typeof taskAgentOptions.model_id === "string"
      ? taskAgentOptions.model_id
      : "") ||
    defaultModelId ||
    "";
  const initialModelValue =
    (typeof taskAgentOptions.model === "string"
      ? taskAgentOptions.model
      : "") ||
    defaultModelValue ||
    "";

  const [name, setName] = useState(task?.name ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [agentId, setAgentId] = useState(
    task?.agent_id ?? defaultAgentId ?? "",
  );
  const [personaPresetId, setPersonaPresetId] = useState(
    getScheduledTaskPersonaPresetId(task?.input_payload),
  );
  const [scheduledTaskPluginOptionValues, setScheduledTaskPluginOptionValues] =
    useState<PluginOptionsMetadata>(() => pluginOptionsFromMetadata(task?.input_payload));
  const [personaPresets, setPersonaPresets] = useState<PersonaPreset[]>([]);
  const [modelId, setModelId] = useState(initialModelId);
  const [modelValue, setModelValue] = useState(initialModelValue);
  const [triggerType, setTriggerType] = useState<TriggerType>(
    task?.trigger_type ?? "interval",
  );
  const [timezone] = useState(task?.timezone || getBrowserTimezone());
  const [intervalSeconds, setIntervalSeconds] = useState(
    task?.trigger_type === "interval"
      ? String((task?.trigger_config as { seconds?: number })?.seconds ?? 300)
      : "300",
  );
  const [runDate, setRunDate] = useState(
    task?.trigger_type === "date"
      ? toDateTimeLocalValue(
          (task?.trigger_config as { run_date?: string })?.run_date,
        )
      : toDateTimeLocalValue(null),
  );
  const [cronHour, setCronHour] = useState(
    task?.trigger_type === "cron"
      ? String((task?.trigger_config as { hour?: string })?.hour ?? "0")
      : "0",
  );
  const [cronMinute, setCronMinute] = useState(
    task?.trigger_type === "cron"
      ? String((task?.trigger_config as { minute?: string })?.minute ?? "0")
      : "0",
  );
  const [cronSecond, setCronSecond] = useState(
    task?.trigger_type === "cron"
      ? String((task?.trigger_config as { second?: string })?.second ?? "0")
      : "0",
  );
  const [cronDay, setCronDay] = useState(
    task?.trigger_type === "cron"
      ? String((task?.trigger_config as { day?: string })?.day ?? "")
      : "",
  );
  const [cronMonth, setCronMonth] = useState(
    task?.trigger_type === "cron"
      ? String((task?.trigger_config as { month?: string })?.month ?? "")
      : "",
  );
  const [cronDayOfWeek, setCronDayOfWeek] = useState(
    task?.trigger_type === "cron"
      ? String(
          (task?.trigger_config as { day_of_week?: string })?.day_of_week ?? "",
        )
      : "",
  );
  const [inputPayload, setInputPayload] = useState(
    task ? JSON.stringify(task.input_payload ?? {}, null, 2) : "{}",
  );
  const [enabled, setEnabled] = useState(task?.enabled ?? true);
  const [runOnStart, setRunOnStart] = useState(task?.run_on_start ?? false);
  const [maxRetries, setMaxRetries] = useState(String(task?.max_retries ?? 0));
  const [timeoutSeconds, setTimeoutSeconds] = useState(
    String(task?.timeout_seconds ?? 600),
  );
  const [isSaving, setIsSaving] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const {
    options: scheduledTaskPluginOptions,
    isLoading: scheduledTaskPluginOptionsLoading,
  } = useScheduledTaskPluginOptions(agentId, {
    includeInactive: true,
  });
  const suppressPersonaSelector = hasEffectiveCorePersonaSuppressingOption(
    scheduledTaskPluginOptions,
  );

  const setScheduledTaskPluginOptionValue = (
    pluginId: string,
    key: string,
    value: unknown,
  ) => {
    setScheduledTaskPluginOptionValues((current) =>
      withPluginOption({ plugin_options: current }, pluginId, key, value)
        .plugin_options ?? {},
    );
  };

  useEffect(() => {
    let cancelled = false;
    personaPresetApi
      .list({ limit: 100 })
      .then((response) => {
        if (!cancelled) setPersonaPresets(response.presets);
      })
      .catch(() => {
        if (!cancelled) setPersonaPresets([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (scheduledTaskPluginOptionsLoading) return;
    setScheduledTaskPluginOptionValues((current) => {
      const imported = importLegacyPayloadPluginOptions(
        task?.input_payload,
        scheduledTaskPluginOptions,
        current,
      );
      const next = retainPluginOptionsForDeclarations(
        imported,
        scheduledTaskPluginOptions,
      );
      return JSON.stringify(next) === JSON.stringify(current) ? current : next;
    });
    if (suppressPersonaSelector) {
      setPersonaPresetId("");
    }
  }, [
    scheduledTaskPluginOptions,
    scheduledTaskPluginOptionsLoading,
    suppressPersonaSelector,
    task?.input_payload,
  ]);

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error(t("scheduledTask.nameRequired"));
      return;
    }
    if (!agentId) {
      toast.error(t("scheduledTask.agentRequired"));
      return;
    }

    // Validate JSON
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(inputPayload || "{}");
    } catch {
      setJsonError(t("scheduledTask.invalidJson"));
      return;
    }
    setJsonError(null);

    // Build trigger config
    let triggerConfig: Record<string, unknown>;
    if (triggerType === "interval") {
      triggerConfig = {
        seconds: Math.max(1, parseInt(intervalSeconds) || 300),
      };
    } else if (triggerType === "date") {
      if (!runDate) {
        toast.error(t("scheduledTask.runDateRequired"));
        return;
      }
      const date = new Date(runDate);
      if (Number.isNaN(date.getTime())) {
        toast.error(t("scheduledTask.runDateRequired"));
        return;
      }
      triggerConfig = { run_date: date.toISOString() };
    } else {
      triggerConfig = {
        hour: cronHour || "0",
        minute: cronMinute || "0",
        second: cronSecond || "0",
        ...(cronDay ? { day: cronDay } : {}),
        ...(cronMonth ? { month: cronMonth } : {}),
        ...(cronDayOfWeek ? { day_of_week: cronDayOfWeek } : {}),
      };
    }

    setIsSaving(true);
    try {
      const nextPayload = buildScheduledTaskInputPayload(payload, {
        agentId,
        modelId,
        modelValue,
        availableModels,
        personaPresetId,
        pluginOptionValues: scheduledTaskPluginOptionValues,
        pluginOptionDeclarations: scheduledTaskPluginOptions,
      });
      await onSave({
        name: name.trim(),
        agent_id: agentId,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        timezone,
        input_payload: nextPayload,
        description: description.trim() || null,
        enabled,
        run_on_start: triggerType === "date" ? false : runOnStart,
        max_retries: Math.max(0, parseInt(maxRetries) || 0),
        timeout_seconds: Math.max(10, parseInt(timeoutSeconds) || 600),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const inputClass = "scheduled-task-input";
  const agentOptions = [
    { value: "", label: t("scheduledTask.agentPlaceholder") },
    ...agents.map((agent) => ({
      value: agent.id,
      label: t(agent.name),
    })),
  ];
  if (agentId && !agentOptions.some((option) => option.value === agentId)) {
    agentOptions.push({ value: agentId, label: agentId });
  }
  const renderPersonaOption = (label: string) => (
    <span className="inline-flex min-w-0 items-center gap-2">
      <UserRound size={14} className="shrink-0 opacity-70" />
      <span className="truncate">{label}</span>
    </span>
  );
  const personaOptions = [
    {
      value: "",
      label: renderPersonaOption(t("scheduledTask.personaPlaceholder")),
    },
    ...personaPresets.map((preset) => ({
      value: preset.id,
      label: renderPersonaOption(preset.name),
    })),
  ];

  const renderScheduledTaskPluginOption = (option: ExtensionScopedOption) => {
    const currentValue = pluginOptionFromValues(
      scheduledTaskPluginOptionValues,
      option.plugin_id,
      option.key,
    );
    const inactive = option.effective === false;
    const disabled = inactive;
    const fieldId = `${option.plugin_id}.${option.key}`;
    const pluginValues = scheduledTaskPluginOptionValues[option.plugin_id];
    const scopedPluginValues =
      pluginValues && typeof pluginValues === "object" && !Array.isArray(pluginValues)
        ? (pluginValues as Record<string, unknown>)
        : {};
    const inactiveNotice = inactive || disabled ? (
      <p className="mt-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
        {t(
          "scheduledTask.pluginOptionInactive",
          "Plugin disabled; saved value is retained but will not apply.",
        )}
      </p>
    ) : null;
    const onChange = (value: unknown) =>
      setScheduledTaskPluginOptionValue(option.plugin_id, option.key, value);
    const rendered = renderScheduledTaskOptionField({
      option,
      value: currentValue,
      pluginValues: scopedPluginValues,
      disabled,
      inactive,
      triggerClassName: inputClass,
      onPluginValueChange: (key, nextValue) =>
        setScheduledTaskPluginOptionValue(option.plugin_id, key, nextValue),
      onChange,
    });

    if (rendered) {
      return (
        <div key={fieldId} className="scheduled-task-form-field">
          <label className="scheduled-task-label">{option.label || option.key}</label>
          {rendered}
          {inactiveNotice}
        </div>
      );
    }

    if (option.type === "boolean") {
      return (
        <div key={fieldId} className="scheduled-task-form-field">
          <label className="scheduled-task-label">{option.label || option.key}</label>
          <ToggleSwitch
            enabled={Boolean(currentValue)}
            onToggle={() => onChange(!currentValue)}
            disabled={disabled}
          />
          {inactiveNotice}
        </div>
      );
    }

    if (option.type === "select" && option.options?.length) {
      return (
        <div key={fieldId} className="scheduled-task-form-field">
          <label className="scheduled-task-label">{option.label || option.key}</label>
          <Select
            value={asInputValue(currentValue)}
            onChange={(value) => onChange(value || null)}
            disabled={disabled}
            triggerClassName={inputClass}
            options={[
              { value: "", label: t("common.none", "None") },
              ...option.options.map((value) => ({ value, label: value })),
            ]}
          />
          {inactiveNotice}
        </div>
      );
    }

    if (option.type === "json" || option.type === "text") {
      return (
        <div key={fieldId} className="scheduled-task-form-field">
          <label className="scheduled-task-label">{option.label || option.key}</label>
          <Textarea
            value={
              typeof currentValue === "object" && currentValue !== null
                ? JSON.stringify(currentValue, null, 2)
                : asInputValue(currentValue)
            }
            onChange={(event) =>
              onChange(
                option.type === "json"
                  ? parseJsonValue(event.target.value)
                  : event.target.value,
              )
            }
            disabled={disabled}
            rows={3}
            className={`${inputClass} min-h-[5rem] resize-y`}
          />
          {inactiveNotice}
        </div>
      );
    }

    return (
      <div key={fieldId} className="scheduled-task-form-field">
        <label className="scheduled-task-label">{option.label || option.key}</label>
        <Input
          type={optionInputType(option)}
          value={asInputValue(currentValue)}
          onChange={(event) =>
            onChange(
              option.type === "number"
                ? Number(event.target.value || 0)
                : event.target.value || null,
            )
          }
          disabled={disabled}
          className={inputClass}
        />
        {inactiveNotice}
      </div>
    );
  };

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={isEdit ? t("scheduledTask.edit") : t("scheduledTask.create")}
      icon={isEdit ? <Pencil size={16} /> : <Plus size={16} />}
      footer={
        <PanelFooterActions>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            variant="primary"
            onClick={handleSave}
            loading={isSaving || scheduledTaskPluginOptionsLoading}
            leftIcon={<Save size={16} />}
          >
            {t("common.save")}
          </Button>
        </PanelFooterActions>
      }
    >
      <div className="es-form" style={{ gap: 0 }}>
        <div className="space-y-5">
          {/* Name */}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.name")} *
            </label>
            <Input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
              placeholder={t("scheduledTask.namePlaceholder")}
            />
          </div>

          {/* Description */}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.description")}
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className={`${inputClass} resize-y`}
              placeholder={t("scheduledTask.descriptionPlaceholder")}
            />
          </div>

          {/* Agent selector */}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.agent")} *
            </label>
            <Select
              value={agentId}
              onChange={(v) => {
                setAgentId(v);
              }}
              triggerClassName={inputClass}
              options={agentOptions}
            />
          </div>

          {/* Persona / team selector */}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label inline-flex items-center gap-1.5">
              <UserRound size={14} className="shrink-0 opacity-75" />
              <span>{t("scheduledTask.persona", "瑙掕壊")}</span>
            </label>
            <Select
              value={personaPresetId}
              onChange={setPersonaPresetId}
              disabled={suppressPersonaSelector}
              triggerClassName={inputClass}
              options={personaOptions}
            />
          </div>

          {scheduledTaskPluginOptions.map(renderScheduledTaskPluginOption)}

          {/* Model selector */}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.model")}
            </label>
            <Select
              value={modelId}
              onChange={(v) => {
                const nextModel = availableModels?.find(
                  (model) => model.id === v,
                );
                setModelId(v);
                setModelValue(nextModel?.value || "");
              }}
              disabled={!availableModels || availableModels.length === 0}
              triggerClassName={inputClass}
              options={[
                { value: "", label: t("scheduledTask.modelPlaceholder") },
                ...(availableModels || []).map((model) => ({
                  value: model.id,
                  label: model.label || model.value,
                })),
              ]}
            />
          </div>

          {/* Trigger type */}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.triggerType")}
            </label>
            <div className="scheduled-task-segmented">
              {(["date", "interval", "cron"] as const).map((tt) => (
                <button
                  key={tt}
                  type="button"
                  onClick={() => setTriggerType(tt)}
                  className={`scheduled-task-segment ${
                    triggerType === tt ? "scheduled-task-segment--active" : ""
                  }`}
                >
                  {tt === "interval" ? (
                    <Timer size={16} />
                  ) : (
                    <CalendarClock size={16} />
                  )}
                  {t(`scheduledTask.${tt}`)}
                </button>
              ))}
            </div>
          </div>

          {/* Trigger config */}
          {triggerType === "interval" ? (
            <div className="scheduled-task-form-field">
              <label className="scheduled-task-label">
                {t("scheduledTask.intervalSeconds")} *
              </label>
              <Input
                type="number"
                min={1}
                value={intervalSeconds}
                onChange={(e) => setIntervalSeconds(e.target.value)}
                className={inputClass}
              />
            </div>
          ) : triggerType === "date" ? (
            <div className="scheduled-task-form-field">
              <label className="scheduled-task-label">
                {t("scheduledTask.runDate")} *
              </label>
              <Input
                type="datetime-local"
                value={runDate}
                onChange={(e) => setRunDate(e.target.value)}
                className={inputClass}
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {(
                [
                  {
                    key: "cronHour",
                    label: t("scheduledTask.cronHour"),
                    value: cronHour,
                    set: setCronHour,
                  },
                  {
                    key: "cronMinute",
                    label: t("scheduledTask.cronMinute"),
                    value: cronMinute,
                    set: setCronMinute,
                  },
                  {
                    key: "cronSecond",
                    label: t("scheduledTask.cronSecond"),
                    value: cronSecond,
                    set: setCronSecond,
                  },
                  {
                    key: "cronDay",
                    label: t("scheduledTask.cronDay"),
                    value: cronDay,
                    set: setCronDay,
                  },
                  {
                    key: "cronMonth",
                    label: t("scheduledTask.cronMonth"),
                    value: cronMonth,
                    set: setCronMonth,
                  },
                  {
                    key: "cronDayOfWeek",
                    label: t("scheduledTask.cronDayOfWeek"),
                    value: cronDayOfWeek,
                    set: setCronDayOfWeek,
                  },
                ] as const
              ).map(({ key, label, value, set }) => (
                <div key={key} className="scheduled-task-form-field">
                  <label className="scheduled-task-label text-xs">
                    {label}
                  </label>
                  <Input
                    type="text"
                    value={value}
                    onChange={(e) => set(e.target.value)}
                    className={inputClass}
                    placeholder="*"
                  />
                </div>
              ))}
            </div>
          )}

          {/* Input payload */}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.inputPayload")}
            </label>
            <Textarea
              value={inputPayload}
              onChange={(e) => {
                setInputPayload(e.target.value);
                setJsonError(null);
              }}
              rows={4}
              className={`${inputClass} resize-y font-mono text-xs`}
              placeholder="{}"
            />
            {jsonError && (
              <p className="mt-1 text-xs text-red-500">{jsonError}</p>
            )}
          </div>

          {/* Toggles */}
          <div className="space-y-3">
            {/* Enabled toggle */}
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-theme-text-secondary">
                {t("scheduledTask.enabled")}
              </span>
              <ToggleSwitch
                enabled={enabled}
                onToggle={() => setEnabled(!enabled)}
                ariaLabel={
                  enabled
                    ? t("scheduledTask.disable")
                    : t("scheduledTask.enable")
                }
              />
            </div>

            {triggerType !== "date" && (
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-theme-text-secondary">
                  {t("scheduledTask.runOnStart")}
                </span>
                <ToggleSwitch
                  enabled={runOnStart}
                  onToggle={() => setRunOnStart(!runOnStart)}
                  ariaLabel={
                    runOnStart
                      ? t("scheduledTask.disableRunOnStart")
                      : t("scheduledTask.enableRunOnStart")
                  }
                />
              </div>
            )}
          </div>

          {/* Number inputs */}
          <div className="grid grid-cols-2 gap-4">
            <div className="scheduled-task-form-field">
              <label className="scheduled-task-label">
                {t("scheduledTask.maxRetries")}
              </label>
              <Input
                type="number"
                min={0}
                max={10}
                value={maxRetries}
                onChange={(e) => setMaxRetries(e.target.value)}
                className={inputClass}
              />
            </div>
            <div className="scheduled-task-form-field">
              <label className="scheduled-task-label">
                {t("scheduledTask.timeoutSeconds")}
              </label>
              <Input
                type="number"
                min={10}
                max={3600}
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        </div>
      </div>
    </EditorSidebar>
  );
}
