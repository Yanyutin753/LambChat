import { ModelIconImg } from "../../agent/modelIcon.tsx";
import { InteractiveIcon } from "../../common/InteractiveIcon";
import { AgentIcon } from "../../agent/AgentIcon";
import { AgentAvatar } from "../../common/AgentAvatar";
import { getTeamFallbackAvatar } from "../../team/teamAvatarUtils";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import i18n from "../../../i18n";
import { resolveAgentDisplayName } from "../../agent/agentCatalog";
import {
  CalendarClock,
  Pencil,
  Plus,
  Save,
  Timer,
  UserRound,
  UsersRound,
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
import type { Team } from "../../../types/team";
import { sessionApi, type BackendSession } from "../../../services/api/session";
import { personaPresetApi } from "../../../services/api/personaPreset";
import { teamApi } from "../../../services/api/team";
import { getFullUrl } from "../../../services/api";
import { useFileUpload } from "../../../hooks/useFileUpload";
import { AttachmentCard } from "../../common/AttachmentCard";
import { FileUploadButton } from "../../chat/FileUploadButton";
import { openAttachmentPreview } from "../../chat/attachmentPreviewStore";
import type { MessageAttachment } from "../../../types";
import {
  buildScheduledTaskInputPayload,
  getAgentOptionsFromScheduledTaskPayload,
  getScheduledTaskAttachments,
  getScheduledTaskPersonaPresetId,
  getScheduledTaskTeamId,
  withScheduledTaskAttachments,
} from "../scheduledTaskPayload";
import { getBrowserTimezone, toDateTimeLocalValue } from "./utils";

/** Create/Edit form sidebar */
export function TaskFormModal({
  task,
  agents,
  availableModels,
  defaultAgentId,
  defaultSessionId,
  defaultModelId,
  defaultModelValue,
  onSave,
  onClose,
}: {
  task: ScheduledTask | null;
  agents: AgentInfo[];
  availableModels: AvailableModel[] | null;
  defaultAgentId?: string;
  defaultSessionId?: string;
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

  const [executionMode, setExecutionMode] = useState<
    "conversation" | "standalone"
  >(task?.execution_mode || (defaultSessionId ? "conversation" : "standalone"));
  const [targetSessionId, setTargetSessionId] = useState(
    task?.target_session_id || defaultSessionId || "",
  );
  const [notificationPolicy, setNotificationPolicy] = useState<
    "always" | "meaningful_changes"
  >(
    task?.notification_policy ||
      (defaultSessionId ? "meaningful_changes" : "always"),
  );
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  useEffect(() => {
    let cancelled = false;
    sessionApi
      .list({ limit: 100 })
      .then((response) => {
        if (!cancelled)
          setSessions(Array.isArray(response) ? response : response.sessions);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  const [name, setName] = useState(task?.name ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [agentId, setAgentId] = useState(
    task?.agent_id ?? defaultAgentId ?? "",
  );
  const [personaPresetId, setPersonaPresetId] = useState(
    getScheduledTaskPersonaPresetId(task?.input_payload),
  );
  const [teamId, setTeamId] = useState(
    getScheduledTaskTeamId(task?.input_payload),
  );
  const [personaPresets, setPersonaPresets] = useState<PersonaPreset[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
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
  const [attachments, setAttachments] = useState<MessageAttachment[]>(
    getScheduledTaskAttachments(task?.input_payload),
  );
  const [enabled, setEnabled] = useState(task?.enabled ?? true);
  const [runOnStart, setRunOnStart] = useState(task?.run_on_start ?? false);
  const [maxRetries, setMaxRetries] = useState(String(task?.max_retries ?? 0));
  const [isSaving, setIsSaving] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const isTeamAgent = agentId === "team";
  const uploadController = useFileUpload({
    attachments,
    onAttachmentsChange: setAttachments,
  });
  const { cancelUpload } = uploadController;
  const hasUploadingAttachment = attachments.some((item) => item.isUploading);

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
    teamApi
      .list({ limit: 100 })
      .then((response) => {
        if (!cancelled) setTeams(response.teams);
      })
      .catch(() => {
        if (!cancelled) setTeams([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error(t("scheduledTask.nameRequired"));
      return;
    }
    if (executionMode === "conversation" && !targetSessionId) {
      toast.error(t("scheduledTask.targetRequired"));
      return;
    }
    if (executionMode === "standalone" && !agentId) {
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
    payload = withScheduledTaskAttachments(payload, attachments);

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
        teamId,
      });
      await onSave({
        execution_mode: executionMode,
        target_session_id:
          executionMode === "conversation" ? targetSessionId : null,
        notification_policy: notificationPolicy,
        source_session_id: task?.source_session_id || defaultSessionId || null,
        name: name.trim(),
        agent_id:
          executionMode === "conversation"
            ? sessions.find((session) => session.id === targetSessionId)
                ?.agent_id ||
              agentId ||
              "search"
            : agentId,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        timezone,
        input_payload: nextPayload,
        description: description.trim() || null,
        enabled,
        run_on_start: triggerType === "date" ? false : runOnStart,
        max_retries: Math.max(0, parseInt(maxRetries) || 0),
        timeout_seconds: 0,
      });
    } finally {
      setIsSaving(false);
    }
  };

  const inputClass = "scheduled-task-input";
  const PersonaOrTeamIcon = isTeamAgent ? UsersRound : UserRound;
  const personaOrTeamIconLabel = isTeamAgent
    ? t("scheduledTask.team", "团队")
    : t("scheduledTask.persona", "角色");
  const renderPersonaOrTeamOption = (
    label: string,
    avatar?: string | null,
    seed?: string,
  ) => (
    <span className="inline-flex min-w-0 items-center gap-2">
      {seed ? (
        <AgentAvatar avatar={avatar} seed={seed} size={18} />
      ) : (
        <PersonaOrTeamIcon size={14} className="shrink-0 opacity-70" />
      )}
      <span className="truncate">{label}</span>
    </span>
  );
  const handleRemoveAttachment = (attachment: MessageAttachment) => {
    setAttachments((prev) => prev.filter((item) => item.id !== attachment.id));
  };

  return (
    <EditorSidebar
      registryKey={isEdit ? "schedules:edit" : "schedules:create"}
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
            loading={isSaving}
            disabled={hasUploadingAttachment}
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
              aria-label={t("scheduledTask.name")}
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
              aria-label={t("scheduledTask.description")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className={`${inputClass} resize-y`}
              placeholder={t("scheduledTask.descriptionPlaceholder")}
            />
          </div>

          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.executionMode")}
            </label>
            <Select
              ariaLabel={t("scheduledTask.executionMode")}
              value={executionMode}
              onChange={(value) =>
                setExecutionMode(value as typeof executionMode)
              }
              triggerClassName={inputClass}
              options={[
                {
                  value: "conversation",
                  label: t("scheduledTask.conversationMode"),
                },
                {
                  value: "standalone",
                  label: t("scheduledTask.standaloneMode"),
                },
              ]}
            />
          </div>
          {executionMode === "conversation" && (
            <div className="scheduled-task-form-field">
              <label className="scheduled-task-label">
                {t("scheduledTask.targetConversation")}
              </label>
              <Select
                ariaLabel={t("scheduledTask.targetConversation")}
                value={targetSessionId}
                onChange={setTargetSessionId}
                triggerClassName={inputClass}
                options={[
                  { value: "", label: t("scheduledTask.targetRequired") },
                  ...(!sessions.some(
                    (session) => session.id === targetSessionId,
                  ) && targetSessionId
                    ? [
                        {
                          value: targetSessionId,
                          label: t("scheduledTask.currentConversation"),
                        },
                      ]
                    : []),
                  ...sessions.map((session) => ({
                    value: session.id,
                    label: session.name || t("scheduledTask.untitledSession"),
                  })),
                ]}
              />
              <p className="text-12 text-theme-text-secondary">
                {t("scheduledTask.inheritContext")}
              </p>
            </div>
          )}
          <div className="scheduled-task-form-field">
            <label className="scheduled-task-label">
              {t("scheduledTask.notificationPolicy")}
            </label>
            <Select
              ariaLabel={t("scheduledTask.notificationPolicy")}
              value={notificationPolicy}
              onChange={(value) =>
                setNotificationPolicy(value as typeof notificationPolicy)
              }
              triggerClassName={inputClass}
              options={[
                {
                  value: "meaningful_changes",
                  label: t("scheduledTask.meaningfulChanges"),
                },
                { value: "always", label: t("scheduledTask.alwaysNotify") },
              ]}
            />
          </div>
          {executionMode === "standalone" && (
            <>
              {/* Agent selector */}
              <div className="scheduled-task-form-field">
                <label className="scheduled-task-label">
                  {t("scheduledTask.agent")} *
                </label>
                <Select
                  ariaLabel={t("scheduledTask.agent")}
                  value={agentId}
                  onChange={(v) => {
                    setAgentId(v);
                    if (v === "team") {
                      setPersonaPresetId("");
                    } else {
                      setTeamId("");
                    }
                  }}
                  triggerClassName={inputClass}
                  options={[
                    { value: "", label: t("scheduledTask.agentPlaceholder") },
                    ...agents.map((agent) => ({
                      value: agent.id,
                      label: (
                        <span className="inline-flex min-w-0 items-center gap-2">
                          <AgentIcon
                            icon={agent.icon}
                            seed={agent.id}
                            size={18}
                          />
                          <span className="truncate">
                            {resolveAgentDisplayName(agent, i18n.language, t) ||
                              agent.id}
                          </span>
                        </span>
                      ),
                    })),
                  ]}
                />
              </div>

              {/* Persona / team selector */}
              <div className="scheduled-task-form-field">
                <label className="scheduled-task-label inline-flex items-center gap-1.5">
                  <PersonaOrTeamIcon
                    size={14}
                    className="shrink-0 opacity-75"
                  />
                  <span>{personaOrTeamIconLabel}</span>
                </label>
                <Select
                  ariaLabel={personaOrTeamIconLabel}
                  value={isTeamAgent ? teamId : personaPresetId}
                  onChange={isTeamAgent ? setTeamId : setPersonaPresetId}
                  triggerClassName={inputClass}
                  options={
                    isTeamAgent
                      ? [
                          {
                            value: "",
                            label: renderPersonaOrTeamOption(
                              t("scheduledTask.teamPlaceholder", "不指定团队"),
                            ),
                          },
                          ...teams.map((team) => ({
                            value: team.id,
                            label: renderPersonaOrTeamOption(
                              team.name,
                              team.avatar ?? getTeamFallbackAvatar(team),
                              team.name,
                            ),
                          })),
                        ]
                      : [
                          {
                            value: "",
                            label: renderPersonaOrTeamOption(
                              t(
                                "scheduledTask.personaPlaceholder",
                                "不指定角色",
                              ),
                            ),
                          },
                          ...personaPresets.map((preset) => ({
                            value: preset.id,
                            label: renderPersonaOrTeamOption(
                              preset.name,
                              preset.avatar,
                              preset.id,
                            ),
                          })),
                        ]
                  }
                />
              </div>

              {/* Model selector */}
              <div className="scheduled-task-form-field">
                <label className="scheduled-task-label">
                  {t("scheduledTask.model")}
                </label>
                <Select
                  ariaLabel={t("scheduledTask.model")}
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
                      label: (
                        <span className="inline-flex min-w-0 items-center gap-1.5">
                          <ModelIconImg
                            model={model.value}
                            provider={model.provider}
                            icon={model.icon}
                            size={16}
                          />
                          {model.label || model.value}
                        </span>
                      ),
                    })),
                  ]}
                />
              </div>
            </>
          )}
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
                  aria-pressed={triggerType === tt}
                  onClick={() => setTriggerType(tt)}
                  className={`scheduled-task-segment ${
                    triggerType === tt ? "scheduled-task-segment--active" : ""
                  }`}
                >
                  {tt === "interval" ? (
                    <InteractiveIcon>
                      <Timer size={16} />
                    </InteractiveIcon>
                  ) : (
                    <InteractiveIcon>
                      <CalendarClock size={16} />
                    </InteractiveIcon>
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
                aria-label={t("scheduledTask.intervalSeconds")}
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
                aria-label={t("scheduledTask.runDate")}
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
                  <label className="scheduled-task-label text-12">
                    {label}
                  </label>
                  <Input
                    aria-label={label}
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
              aria-label={t("scheduledTask.inputPayload")}
              value={inputPayload}
              onChange={(e) => {
                setInputPayload(e.target.value);
                setJsonError(null);
              }}
              rows={4}
              className={`${inputClass} resize-y font-mono text-12`}
              placeholder="{}"
            />
            {jsonError && (
              <p className="mt-1 text-12 text-red-500">{jsonError}</p>
            )}
          </div>

          <div className="scheduled-task-form-field">
            <div className="mb-2 flex items-center justify-between gap-3 font-serif">
              <label className="scheduled-task-label">
                {t("chat.attachments")}
              </label>
              <FileUploadButton uploadController={uploadController} />
            </div>
            {attachments.length > 0 && (
              <div className="flex gap-3 overflow-x-auto attachment-scroll pb-1">
                {attachments.map((attachment) => {
                  const isImage =
                    attachment.mimeType?.startsWith("image/") &&
                    Boolean(attachment.url);
                  return (
                    <AttachmentCard
                      key={attachment.id}
                      attachment={attachment}
                      variant="editable"
                      size="compact"
                      isUploading={attachment.isUploading}
                      onClick={() => {
                        if (isImage && attachment.url) {
                          window.open(
                            getFullUrl(attachment.url) ?? attachment.url,
                          );
                        } else {
                          openAttachmentPreview(attachment, "chat-input");
                        }
                      }}
                      onRemove={() => handleRemoveAttachment(attachment)}
                      onCancel={
                        attachment.isUploading
                          ? () => cancelUpload(attachment.id)
                          : undefined
                      }
                    />
                  );
                })}
              </div>
            )}
          </div>

          {/* Toggles */}
          <div className="space-y-3">
            {/* Enabled toggle */}
            <div className="flex items-center justify-between">
              <span className="text-14 font-medium text-theme-text-secondary">
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
                <span className="text-14 font-medium text-theme-text-secondary">
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
                aria-label={t("scheduledTask.maxRetries")}
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
                {t("approvals.scheduledTask.timeout")}
              </label>
              <span className="text-13 text-theme-text-secondary">
                {t("scheduledTask.noTimeLimit")}
              </span>
            </div>
          </div>
        </div>
      </div>
    </EditorSidebar>
  );
}
