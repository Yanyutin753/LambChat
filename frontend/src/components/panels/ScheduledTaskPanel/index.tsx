import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import i18n from "../../../i18n";
import { resolveAgentDisplayName } from "../../agent/agentCatalog";
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
import { SkillBaseCard } from "../../common/SkillBaseCard";
import { nameToGradient } from "../../common/cardUtils";
import { PanelHeader } from "../../common/PanelHeader";
import { EmptyState, PanelHeaderActions } from "../../common";
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
import type { Team } from "../../../types/team";
import { personaPresetApi } from "../../../services/api/personaPreset";
import { teamApi } from "../../../services/api/team";
import { formatDateTimeShort } from "../../../utils/datetime";
import {
  getAgentOptionsFromScheduledTaskPayload,
  getScheduledTaskPersonaPresetId,
  getScheduledTaskTeamId,
} from "../scheduledTaskPayload";
import { notifyScheduledTaskMutation } from "../../../stores/scheduledTaskMutationStore";
import { RunStatusBadge, StatusBadgeForTask as StatusBadge } from "./Badges";
import { ConfirmDialog } from "../../common/ConfirmDialog";
import { StatusFilter } from "./StatusFilter";
import { TaskFormModal } from "./TaskFormModal";
import { TaskSessionList } from "./TaskSessionList";
import { readScheduledTaskDefaults } from "./utils";

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
  const { taskId } = useParams<{ taskId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState("");
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const requestIdRef = useRef(0);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(20);
  const [statusFilter, setStatusFilter] = useState<
    ScheduledTaskStatusType | undefined
  >(undefined);
  const [deleteTarget, setDeleteTarget] = useState<ScheduledTask | null>(null);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  useEffect(() => {
    if (canWrite && searchParams.get("create") === "1") {
      setIsCreating(true);
      const next = new URLSearchParams(searchParams);
      next.delete("create");
      setSearchParams(next, { replace: true });
    }
  }, [canWrite, searchParams, setSearchParams]);

  const [agents, setAgents] = useState<AgentInfo[]>(providedAgents || []);
  const [personaPresets, setPersonaPresets] = useState<PersonaPreset[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [apiDefaultAgentId, setApiDefaultAgentId] = useState("");
  const defaults = readScheduledTaskDefaults();
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

  // Resolve task name from route param + loaded tasks
  const selectedTaskName = taskId
    ? tasks.find((t) => t.id === taskId)?.name || t("scheduledTask.title")
    : "";

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

  // Fetch tasks
  const fetchTasks = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setLoadError(false);
    try {
      const response = await scheduledTaskApi.list(skip, limit, statusFilter, {
        search: searchQuery,
      });
      if (requestId !== requestIdRef.current) return;
      setTasks(response.items);
      setTotal(response.total);
    } catch {
      if (requestId !== requestIdRef.current) return;
      setLoadError(true);
    } finally {
      if (requestId === requestIdRef.current) {
        setIsLoading(false);
        setHasLoaded(true);
      }
    }
  }, [skip, limit, statusFilter, searchQuery]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

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
    if (task.agent_id === "team") {
      const teamId = getScheduledTaskTeamId(task.input_payload);
      if (!teamId) return null;
      return teams.find((team) => team.id === teamId)?.name || teamId;
    }
    const personaPresetId = getScheduledTaskPersonaPresetId(task.input_payload);
    if (!personaPresetId) return null;
    return (
      personaPresets.find((preset) => preset.id === personaPresetId)?.name ||
      personaPresetId
    );
  };

  // Show skeleton during initial data loading — consistent with other panels
  if (isLoading && !hasLoaded && !taskId) {
    return <ScheduledTaskPanelSkeleton />;
  }

  return (
    <div className="glass-shell scheduled-task-panel flex h-full flex-col min-h-0">
      {taskId ? (
        <TaskSessionList taskId={taskId} taskName={selectedTaskName} />
      ) : (
        <>
          <PanelHeader
            title={t("scheduledTask.title")}
            subtitle={t("scheduledTask.subtitle")}
            illustration="panel-schedule"
            searchValue={searchQuery}
            onSearchChange={(value) => {
              setSearchQuery(value);
              setSkip(0);
            }}
            searchPlaceholder={t("scheduledTask.searchPlaceholder")}
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
          <div className="panel-body flex-1 overflow-y-auto">
            {loadError && (
              <div
                role="alert"
                className="p-4 text-center text-theme-text-secondary"
              >
                <p>{t("common.loadFailed")}</p>
                <Button className="mt-3" onClick={fetchTasks}>
                  {t("common.refresh")}
                </Button>
              </div>
            )}
            {!loadError && tasks.length === 0 ? (
              <EmptyState
                icon={<Clock size={20} />}
                title={t(
                  searchQuery.trim()
                    ? "scheduledTask.noResults"
                    : "scheduledTask.noTasks",
                )}
                description={t(
                  searchQuery.trim()
                    ? "scheduledTask.noResultsDesc"
                    : "scheduledTask.noTasksDesc",
                )}
              />
            ) : (
              <div className="grid auto-grid-cols gap-3">
                {tasks.map((task) => {
                  const agent = agents.find((a) => a.id === task.agent_id);
                  const modelName = formatTaskModel(task);
                  const contextName = formatTaskContext(task);

                  return (
                    <SkillBaseCard
                      key={task.id}
                      title={task.name}
                      gradient={nameToGradient(task.name)}
                      icon={
                        <Clock
                          size={20}
                          className="text-theme-text-secondary"
                        />
                      }
                      className="cursor-pointer"
                      description={task.description ?? undefined}
                      onClick={() => navigate(`/scheduled-tasks/${task.id}`)}
                      statusPills={
                        <div className="mt-1">
                          <StatusBadge status={task.status} />
                        </div>
                      }
                      tags={
                        <div className="flex flex-wrap gap-1.5">
                          <span className="skill-meta-pill">
                            <Timer size={12} />
                            {formatTriggerInfo(task)}
                          </span>
                          <span className="skill-meta-pill">
                            <Bot size={12} />
                            {agent
                              ? resolveAgentDisplayName(agent, i18n.language, t)
                              : task.agent_id}
                          </span>
                          {modelName && (
                            <span className="skill-meta-pill">
                              <Cpu size={12} />
                              {modelName}
                            </span>
                          )}
                          {contextName && (
                            <span className="skill-meta-pill">
                              <Bot size={12} />
                              {contextName}
                            </span>
                          )}
                          {task.total_runs > 0 && (
                            <span className="skill-meta-pill">
                              <History size={12} />
                              {t("scheduledTask.totalRuns")}: {task.total_runs}
                            </span>
                          )}
                        </div>
                      }
                      meta={
                        <>
                          {task.last_run_at && (
                            <div className="flex flex-wrap items-center gap-2 text-11 text-[var(--theme-text-secondary)]">
                              <span>{t("scheduledTask.lastRun")}:</span>
                              <span>
                                {formatDateTimeShort(task.last_run_at)}
                              </span>
                              {task.last_run_status && (
                                <RunStatusBadge status={task.last_run_status} />
                              )}
                            </div>
                          )}
                          {!task.last_run_at && (
                            <p className="text-11 text-[var(--theme-text-secondary)]">
                              {t("scheduledTask.neverRun")}
                            </p>
                          )}
                        </>
                      }
                      actions={[
                        ...(canWrite && task.status === "active"
                          ? [
                              {
                                label: t("scheduledTask.pause"),
                                icon: <Pause size={14} />,
                                onClick: () => handlePause(task),
                              },
                            ]
                          : []),
                        ...(canWrite && task.status === "paused"
                          ? [
                              {
                                label: t("scheduledTask.resume"),
                                icon: <Play size={14} />,
                                onClick: () => handleResume(task),
                              },
                            ]
                          : []),
                        ...(canWrite
                          ? [
                              {
                                label: t("scheduledTask.runNow"),
                                icon: <RotateCcw size={14} />,
                                onClick: () => handleRunNow(task),
                              },
                              {
                                label: t("scheduledTask.edit"),
                                icon: <Pencil size={14} />,
                                onClick: () => setEditingTask(task),
                              },
                            ]
                          : []),
                        ...(canDelete
                          ? [
                              {
                                label: t("scheduledTask.delete"),
                                icon: <Trash2 size={14} />,
                                danger: true,
                                onClick: () => setDeleteTarget(task),
                              },
                            ]
                          : []),
                      ]}
                    />
                  );
                })}
              </div>
            )}
          </div>

          {/* Pagination */}
          <div className="panel-pagination empty:hidden">
            <Pagination
              page={Math.floor(skip / limit) + 1}
              pageSize={limit}
              total={total}
              onChange={(page) => setSkip((page - 1) * limit)}
            />
          </div>

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
