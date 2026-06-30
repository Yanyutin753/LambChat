import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import {
  Bot,
  Clock,
  Cpu,
  History,
  Pause,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Timer,
  Trash2,
} from "lucide-react";
import { PanelHeader } from "../../common/PanelHeader";
import { PanelHeaderActions } from "../../common";
import { Button } from "../../common/ui/Button";
import { ScheduledTaskPanelSkeleton } from "../../skeletons";
import { Pagination } from "../../common/Pagination";
import { scheduledTaskApi } from "../../../services/api/scheduledTask";
import { agentApi } from "../../../services/api/agent";
import { useAuth } from "../../../hooks/useAuth";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { Permission } from "../../../types";
import type {
  ScheduledTask,
  ScheduledTaskCreate,
  ScheduledTaskStatus as ScheduledTaskStatusType,
  ScheduledTaskUpdate,
} from "../../../types/scheduledTask";
import type { AgentInfo } from "../../../types/agent";
import type { AvailableModel } from "../../../contexts/SettingsContext";
import type { PersonaPreset } from "../../../types/personaPreset";
import { personaPresetApi } from "../../../services/api/personaPreset";
import { useScheduledTaskPluginOptions } from "../../../hooks/useScheduledTaskPluginOptions";
import { formatDateTimeShort } from "../../../utils/datetime";
import {
  getAgentOptionsFromScheduledTaskPayload,
  getScheduledTaskPersonaPresetId,
} from "../scheduledTaskPayload";
import { notifyScheduledTaskMutation } from "../../../stores/scheduledTaskMutationStore";
import {
  filterPluginOptionsByVisibleWhen,
  legacyPayloadKeysForPluginOption,
  pluginOptionFromMetadata,
} from "../../../extensions/pluginOptions";
import { RunStatusBadge, StatusBadgeForTask as StatusBadge } from "./Badges";
import { ConfirmDialog } from "../../common/ConfirmDialog";
import { StatusFilter } from "./StatusFilter";
import { TaskFormModal } from "./TaskFormModal";
import { TaskSessionList } from "./TaskSessionList";
import { readScheduledTaskDefaults } from "./utils";
import {
  findScheduledTaskOptionRenderer,
  useScheduledTaskOptionValueLabels,
} from "./scheduledTaskOptionRenderers";

function scheduledTaskPluginOptionStringValue(
  payload: Record<string, unknown> | undefined,
  option: { plugin_id: string; key: string; legacy_payload_keys?: readonly string[] | null },
): string {
  const value = pluginOptionFromMetadata(payload, option.plugin_id, option.key);
  if (typeof value === "string" && value.trim()) return value;

  for (const legacyKey of legacyPayloadKeysForPluginOption(option)) {
    const legacyValue = payload?.[legacyKey];
    if (typeof legacyValue === "string" && legacyValue.trim()) {
      return legacyValue;
    }
  }
  return "";
}

// ── Main Panel ──────────────────────────────────────

export function ScheduledTaskPanel({
  agents: providedAgents,
  currentAgent,
  availableModels: providedAvailableModels,
  currentModelId,
  currentModelValue,
}: {
  agents?: AgentInfo[];
  currentAgent?: string;
  availableModels?: AvailableModel[] | null;
  currentModelId?: string;
  currentModelValue?: string;
} = {}) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const { availableModels: settingsAvailableModels } = useSettingsContext();
  const canWrite = hasPermission(Permission.SCHEDULED_TASK_WRITE);
  const canDelete = hasPermission(Permission.SCHEDULED_TASK_DELETE);
  const [searchParams, setSearchParams] = useSearchParams();
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(20);
  const [statusFilter, setStatusFilter] = useState<
    ScheduledTaskStatusType | undefined
  >(undefined);
  const [deleteTarget, setDeleteTarget] = useState<ScheduledTask | null>(null);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [agents, setAgents] = useState<AgentInfo[]>(providedAgents || []);
  const [personaPresets, setPersonaPresets] = useState<PersonaPreset[]>([]);
  const [apiDefaultAgentId, setApiDefaultAgentId] = useState("");
  const defaults = readScheduledTaskDefaults();
  const { options: scheduledTaskPluginOptions } = useScheduledTaskPluginOptions(
    null,
    { includeInactive: true },
  );
  const scheduledTaskOptionWithRenderer = findScheduledTaskOptionRenderer(
    scheduledTaskPluginOptions,
  );
  const effectiveAvailableModels =
    providedAvailableModels ?? settingsAvailableModels ?? null;
  const fallbackDefaultModel = effectiveAvailableModels?.[0] || null;
  const effectiveDefaultAgentId =
    currentAgent || defaults.agentId || apiDefaultAgentId || "";
  const effectiveDefaultModelId =
    currentModelId || defaults.modelId || fallbackDefaultModel?.id || "";
  const effectiveDefaultModelValue =
    currentModelValue ||
    defaults.modelValue ||
    fallbackDefaultModel?.value ||
    "";
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedTaskName, setSelectedTaskName] = useState<string>("");
  const taskIdFromQuery = searchParams.get("taskId");
  const taskNameFromQuery = searchParams.get("taskName");
  const scheduledTaskOptionValues = useMemo(
    () =>
      tasks
        .flatMap((task) =>
          filterPluginOptionsByVisibleWhen(scheduledTaskPluginOptions, {
            agentId: task.agent_id,
            scope: "scheduled_task",
          }).flatMap((option) => {
            const stringValue = scheduledTaskPluginOptionStringValue(
              task.input_payload,
              option,
            );
            return stringValue && option.renderer ? [stringValue] : [];
          }),
        )
        .filter(Boolean),
    [scheduledTaskPluginOptions, tasks],
  );
  const scheduledTaskOptionLabels = useScheduledTaskOptionValueLabels(
    scheduledTaskOptionWithRenderer,
    scheduledTaskOptionValues,
  );

  // Fetch agents once for the form selector
  useEffect(() => {
    if (providedAgents) {
      setAgents(providedAgents);
      return;
    }
    agentApi
      .list()
      .then((res) => {
        setAgents(res.agents);
        setApiDefaultAgentId(res.default_agent || "");
      })
      .catch(() => {});
  }, [providedAgents]);

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

  // Fetch tasks
  const fetchTasks = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await scheduledTaskApi.list(skip, limit, statusFilter);
      setTasks(response.items);
      setTotal(response.total);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.loadFailed");
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [skip, limit, statusFilter, t]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    if (!taskIdFromQuery) return;

    const taskName =
      taskNameFromQuery ||
      tasks.find((task) => task.id === taskIdFromQuery)?.name ||
      t("scheduledTask.title");

    setSelectedTaskId(taskIdFromQuery);
    setSelectedTaskName(taskName);
  }, [taskIdFromQuery, taskNameFromQuery, tasks, t]);

  // Reset to page 1 when filter changes
  useEffect(() => {
    setSkip(0);
  }, [statusFilter]);

  const handleCreate = async (data: ScheduledTaskCreate) => {
    if (!canWrite) {
      toast.error(t("errors.noPermission"));
      return;
    }
    try {
      await scheduledTaskApi.create(data);
      toast.success(t("scheduledTask.createdSuccess"));
      setIsCreating(false);
      fetchTasks();
      notifyScheduledTaskMutation();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.saveFailed");
      toast.error(message);
    }
  };

  const handleUpdate = async (data: ScheduledTaskCreate) => {
    if (!editingTask) return;
    if (!canWrite) {
      toast.error(t("errors.noPermission"));
      return;
    }
    try {
      const updateData: ScheduledTaskUpdate = {};
      if (data.name !== editingTask.name) updateData.name = data.name;
      if (data.agent_id !== editingTask.agent_id)
        updateData.agent_id = data.agent_id;
      if (data.trigger_type !== editingTask.trigger_type)
        updateData.trigger_type = data.trigger_type;
      if (
        JSON.stringify(data.trigger_config) !==
        JSON.stringify(editingTask.trigger_config)
      )
        updateData.trigger_config = data.trigger_config;
      if (data.timezone && data.timezone !== editingTask.timezone)
        updateData.timezone = data.timezone;
      if (
        JSON.stringify(data.input_payload) !==
        JSON.stringify(editingTask.input_payload)
      )
        updateData.input_payload = data.input_payload;
      if (data.description !== editingTask.description)
        updateData.description = data.description;
      if (data.enabled !== editingTask.enabled)
        updateData.enabled = data.enabled;
      if (data.run_on_start !== editingTask.run_on_start)
        updateData.run_on_start = data.run_on_start;
      if (data.max_retries !== editingTask.max_retries)
        updateData.max_retries = data.max_retries;
      if (data.timeout_seconds !== editingTask.timeout_seconds)
        updateData.timeout_seconds = data.timeout_seconds;

      await scheduledTaskApi.update(editingTask.id, updateData);
      toast.success(t("scheduledTask.updatedSuccess"));
      setEditingTask(null);
      fetchTasks();
      notifyScheduledTaskMutation();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.saveFailed");
      toast.error(message);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    if (!canDelete) {
      toast.error(t("errors.noPermission"));
      return;
    }
    try {
      await scheduledTaskApi.delete(deleteTarget.id);
      toast.success(t("scheduledTask.deletedSuccess"));
      setDeleteTarget(null);
      fetchTasks();
      notifyScheduledTaskMutation();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.deleteFailed");
      toast.error(message);
    }
  };

  const handlePause = async (task: ScheduledTask) => {
    if (!canWrite) {
      toast.error(t("errors.noPermission"));
      return;
    }
    try {
      await scheduledTaskApi.pause(task.id);
      toast.success(t("scheduledTask.pausedSuccess"));
      fetchTasks();
      notifyScheduledTaskMutation();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.operationFailed");
      toast.error(message);
    }
  };

  const handleResume = async (task: ScheduledTask) => {
    if (!canWrite) {
      toast.error(t("errors.noPermission"));
      return;
    }
    try {
      await scheduledTaskApi.resume(task.id);
      toast.success(t("scheduledTask.resumedSuccess"));
      fetchTasks();
      notifyScheduledTaskMutation();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.operationFailed");
      toast.error(message);
    }
  };

  const handleRunNow = async (task: ScheduledTask) => {
    if (!canWrite) {
      toast.error(t("errors.noPermission"));
      return;
    }
    try {
      await scheduledTaskApi.runNow(task.id);
      toast.success(t("scheduledTask.triggeredSuccess"));
      fetchTasks();
      notifyScheduledTaskMutation();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.operationFailed");
      toast.error(message);
    }
  };

  /** Format trigger config for display */
  const formatTriggerInfo = (task: ScheduledTask): string => {
    if (task.trigger_type === "interval") {
      const cfg = task.trigger_config as { seconds?: number };
      return `${t("scheduledTask.interval")}: ${cfg.seconds}s`;
    }
    if (task.trigger_type === "date") {
      const cfg = task.trigger_config as { run_date?: string };
      return `${t("scheduledTask.date")}: ${
        cfg.run_date ? formatDateTimeShort(cfg.run_date) : "-"
      }`;
    }
    const cfg = task.trigger_config as {
      hour?: string;
      minute?: string;
      second?: string;
      day?: string;
      month?: string;
      day_of_week?: string;
    };
    const parts = [
      cfg.minute ?? "*",
      cfg.hour ?? "*",
      cfg.day ?? "*",
      cfg.month ?? "*",
      cfg.day_of_week ?? "*",
    ];
    return `${t("scheduledTask.cron")}: ${parts.join(" ")}`;
  };

  const formatTaskModel = (task: ScheduledTask): string | null => {
    const options = getAgentOptionsFromScheduledTaskPayload(task.input_payload);
    const modelId =
      typeof options.model_id === "string" ? options.model_id : "";
    const modelValue = typeof options.model === "string" ? options.model : "";
    if (!modelId && !modelValue) return null;
    const model = effectiveAvailableModels?.find(
      (item) => item.id === modelId || item.value === modelValue,
    );
    return model?.label || modelValue || modelId;
  };

  const formatTaskContext = (task: ScheduledTask): string | null => {
    const option = findScheduledTaskOptionRenderer(
      filterPluginOptionsByVisibleWhen(scheduledTaskPluginOptions, {
        agentId: task.agent_id,
        scope: "scheduled_task",
      }),
    );
    if (option) {
      const stringValue = scheduledTaskPluginOptionStringValue(
        task.input_payload,
        option,
      );
      if (!stringValue) return null;
      const label = scheduledTaskOptionLabels[stringValue] || stringValue;
      return option.effective !== false
        ? label
        : `${label} (${t("scheduledTask.pluginOptionInactive", "saved, not effective")})`;
    }
    const personaPresetId = getScheduledTaskPersonaPresetId(task.input_payload);
    if (!personaPresetId) return null;
    return (
      personaPresets.find((preset) => preset.id === personaPresetId)?.name ||
      personaPresetId
    );
  };

  // Show skeleton during initial data loading — consistent with other panels
  if (isLoading && tasks.length === 0 && !selectedTaskId) {
    return <ScheduledTaskPanelSkeleton />;
  }

  return (
    <div className="glass-shell scheduled-task-panel flex h-full flex-col min-h-0">
      {selectedTaskId ? (
        <TaskSessionList
          taskId={selectedTaskId}
          taskName={selectedTaskName}
          onBack={() => {
            setSelectedTaskId(null);
            setSelectedTaskName("");
            setSearchParams({});
          }}
        />
      ) : (
        <>
          <PanelHeader
            title={t("scheduledTask.title")}
            icon={
              <Clock size={20} className="text-stone-600 dark:text-stone-400" />
            }
            actions={
              <PanelHeaderActions>
                <StatusFilter value={statusFilter} onChange={setStatusFilter} />
                {canWrite && (
                  <Button
                    variant="primary"
                    size="md"
                    className="panel-header-primary-action"
                    onClick={() => setIsCreating(true)}
                    leftIcon={<Plus size={16} />}
                  >
                    {t("scheduledTask.create")}
                  </Button>
                )}
              </PanelHeaderActions>
            }
          />

          {/* Task List */}
          <div className="flex-1 overflow-y-auto px-4 py-3 sm:p-6">
            {tasks.length === 0 ? (
              <div className="scheduled-task-empty-state">
                <div className="scheduled-task-empty-state__icon">
                  <Clock size={32} />
                </div>
                <p className="scheduled-task-empty-state__title">
                  {t("scheduledTask.noTasks")}
                </p>
                <p className="scheduled-task-empty-state__body">
                  {t("scheduledTask.noTasksDesc")}
                </p>
              </div>
            ) : (
              <div className="grid auto-grid-cols gap-3">
                {tasks.map((task) => {
                  const agentName =
                    agents.find((a) => a.id === task.agent_id)?.name ??
                    task.agent_id;
                  const modelName = formatTaskModel(task);
                  const contextName = formatTaskContext(task);

                  return (
                    <div
                      key={task.id}
                      className="glass-card group relative flex flex-col rounded-xl p-4 sm:p-5 cursor-pointer transition-all duration-200 animate-glass-enter"
                      onClick={() => {
                        setSelectedTaskId(task.id);
                        setSelectedTaskName(task.name);
                      }}
                    >
                      {/* Title row */}
                      <div className="flex flex-wrap items-center gap-2 mb-1.5">
                        <h4 className="truncate text-base font-semibold text-[var(--theme-text)]">
                          {task.name}
                        </h4>
                        <StatusBadge status={task.status} />
                      </div>

                      {/* Description */}
                      {task.description && (
                        <p className="text-sm leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
                          {task.description}
                        </p>
                      )}

                      {/* Meta tags */}
                      <div className="my-3 flex flex-wrap gap-1.5">
                        <span className="glass-tag">
                          <Timer size={12} />
                          {formatTriggerInfo(task)}
                        </span>
                        <span className="glass-tag">
                          <Bot size={12} />
                          {t(agentName)}
                        </span>
                        {modelName && (
                          <span className="glass-tag">
                            <Cpu size={12} />
                            {modelName}
                          </span>
                        )}
                        {contextName && (
                          <span className="glass-tag">
                            <Bot size={12} />
                            {contextName}
                          </span>
                        )}
                        {task.total_runs > 0 && (
                          <span className="glass-tag">
                            <History size={12} />
                            {t("scheduledTask.totalRuns")}: {task.total_runs}
                          </span>
                        )}
                      </div>

                      {/* Last run / never run */}
                      {task.last_run_at && (
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--theme-text-secondary)] mb-2">
                          <span>{t("scheduledTask.lastRun")}:</span>
                          <span>{formatDateTimeShort(task.last_run_at)}</span>
                          {task.last_run_status && (
                            <RunStatusBadge status={task.last_run_status} />
                          )}
                        </div>
                      )}
                      {!task.last_run_at && (
                        <p className="text-[11px] text-[var(--theme-text-secondary)]">
                          {t("scheduledTask.neverRun")}
                        </p>
                      )}

                      {/* Footer actions */}
                      <div
                        className="mt-auto flex items-center gap-2 border-t border-[var(--glass-border)] pt-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="ml-auto" />
                        {canWrite && task.status === "active" && (
                          <button
                            onClick={() => handlePause(task)}
                            className="flex items-center justify-center h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-900/30 dark:hover:text-amber-400 transition-colors"
                            title={t("scheduledTask.pause")}
                          >
                            <Pause size={14} />
                          </button>
                        )}
                        {canWrite && task.status === "paused" && (
                          <button
                            onClick={() => handleResume(task)}
                            className="flex items-center justify-center h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-emerald-50 hover:text-emerald-600 dark:hover:bg-emerald-900/30 dark:hover:text-emerald-400 transition-colors"
                            title={t("scheduledTask.resume")}
                          >
                            <Play size={14} />
                          </button>
                        )}
                        {canWrite && (
                          <button
                            onClick={() => handleRunNow(task)}
                            className="flex items-center justify-center h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-900/30 dark:hover:text-blue-400 transition-colors"
                            title={t("scheduledTask.runNow")}
                          >
                            <RotateCcw size={14} />
                          </button>
                        )}
                        {canWrite && (
                          <button
                            onClick={() => setEditingTask(task)}
                            className="flex items-center justify-center h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-900/30 dark:hover:text-blue-400 transition-colors"
                            title={t("scheduledTask.edit")}
                          >
                            <Pencil size={14} />
                          </button>
                        )}
                        {canDelete && (
                          <button
                            onClick={() => setDeleteTarget(task)}
                            className="flex items-center justify-center h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400 transition-colors"
                            title={t("scheduledTask.delete")}
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Pagination */}
          {total > limit && (
            <div className="glass-divider bg-transparent px-4 py-4 sm:px-6">
              <Pagination
                page={Math.floor(skip / limit) + 1}
                pageSize={limit}
                total={total}
                onChange={(page) => setSkip((page - 1) * limit)}
              />
            </div>
          )}

          {/* Create Modal */}
          {isCreating && canWrite && (
            <TaskFormModal
              task={null}
              agents={agents}
              availableModels={effectiveAvailableModels}
              defaultAgentId={effectiveDefaultAgentId}
              defaultModelId={effectiveDefaultModelId}
              defaultModelValue={effectiveDefaultModelValue}
              onSave={handleCreate}
              onClose={() => setIsCreating(false)}
            />
          )}

          {/* Edit Modal */}
          {editingTask && canWrite && (
            <TaskFormModal
              task={editingTask}
              agents={agents}
              availableModels={effectiveAvailableModels}
              defaultAgentId={effectiveDefaultAgentId}
              defaultModelId={effectiveDefaultModelId}
              defaultModelValue={effectiveDefaultModelValue}
              onSave={handleUpdate}
              onClose={() => setEditingTask(null)}
            />
          )}

          {/* Delete Confirmation Modal */}
          <ConfirmDialog
            isOpen={!!deleteTarget && canDelete}
            title={t("scheduledTask.deleteConfirm")}
            message={t("scheduledTask.deleteWarning")}
            confirmText={t("scheduledTask.delete")}
            cancelText={t("scheduledTask.cancel")}
            onConfirm={handleDelete}
            onCancel={() => setDeleteTarget(null)}
            variant="danger"
          />
        </>
      )}
    </div>
  );
}
