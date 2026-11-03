import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import {
  CalendarClock,
  Clock,
  History,
  Pause,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Timer,
} from "lucide-react";
import { scheduledTaskApi } from "../../../services/api/scheduledTask";
import { useAuth } from "../../../hooks/useAuth";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { Permission } from "../../../types";
import type {
  ScheduledTask,
  ScheduledTaskCreate,
} from "../../../types/scheduledTask";
import {
  notifyScheduledTaskMutation,
  getScheduledTaskMutationVersion,
  subscribeScheduledTaskMutation,
} from "../../../stores/scheduledTaskMutationStore";
import { AgentIcon } from "../../agent/AgentIcon";
import { useAgentCatalog } from "../../agent/useAgentCatalog";
import { resolveAgentReferenceName } from "../../agent/agentCatalog";
import { Button } from "../../common";
import { EditorSidebar } from "../../common/EditorSidebar";
import { EmptyState } from "../../common/EmptyState";
import { InteractiveIcon } from "../../common/InteractiveIcon";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { Pagination } from "../../common/Pagination";
import { formatDateTimeShort } from "../../../utils/datetime";
import { RunStatusBadge, StatusBadgeForTask as StatusBadge } from "./Badges";
import { TaskFormModal } from "./TaskFormModal";
import { buildScheduledTaskUpdate } from "../scheduledTaskPayload";
import { formatTaskTrigger } from "./utils";

export function SessionScheduledTasksPanel({
  sessionId,
  onClose,
}: {
  sessionId: string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(Permission.SCHEDULED_TASK_READ);
  const canWrite = hasPermission(Permission.SCHEDULED_TASK_WRITE);
  const agents = useAgentCatalog();
  const { availableModels } = useSettingsContext();
  const mutationVersion = useSyncExternalStore(
    subscribeScheduledTaskMutation,
    getScheduledTaskMutationVersion,
  );
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [editingTask, setEditingTask] = useState<
    ScheduledTask | null | undefined
  >(undefined);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const actionPending = useRef(false);
  const pageSize = 20;

  useEffect(() => {
    if (!canRead) return;
    let cancelled = false;
    setIsLoading(true);
    setLoadError(false);
    scheduledTaskApi
      .listBySession(sessionId, (page - 1) * pageSize, pageSize)
      .then((response) => {
        if (cancelled) return;
        setTasks(response.items);
        setTotal(response.total);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, page, refreshKey, mutationVersion, canRead]);

  const runTaskAction = async (
    task: ScheduledTask,
    action: "pause" | "resume" | "runNow",
  ) => {
    if (!canWrite || actionPending.current) return;
    actionPending.current = true;
    setPendingTaskId(task.id);
    try {
      await scheduledTaskApi[action](task.id);
      toast.success(
        t(
          action === "pause"
            ? "scheduledTask.pausedSuccess"
            : action === "resume"
              ? "scheduledTask.resumedSuccess"
              : "scheduledTask.triggeredSuccess",
        ),
      );
      notifyScheduledTaskMutation();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("common.operationFailed"),
      );
    } finally {
      actionPending.current = false;
      setPendingTaskId(null);
    }
  };

  const saveTask = async (data: ScheduledTaskCreate) => {
    if (!canWrite) throw new Error(t("errors.noPermission"));
    if (editingTask)
      await scheduledTaskApi.update(
        editingTask.id,
        buildScheduledTaskUpdate(editingTask, data),
      );
    else await scheduledTaskApi.create(data);
    toast.success(
      t(
        editingTask
          ? "scheduledTask.updatedSuccess"
          : "scheduledTask.createdSuccess",
      ),
    );
    setEditingTask(undefined);
    notifyScheduledTaskMutation();
  };

  if (!canRead) return null;
  if (editingTask !== undefined && canWrite)
    return (
      <TaskFormModal
        registryKey="session-scheduled-tasks"
        key={editingTask?.id || "create"}
        task={editingTask}
        agents={agents}
        availableModels={availableModels}
        defaultSessionId={sessionId}
        onSave={saveTask}
        onClose={() => setEditingTask(undefined)}
      />
    );

  return (
    <EditorSidebar
      open
      registryKey="session-scheduled-tasks"
      onClose={onClose}
      title={t("scheduledTask.conversationTasks")}
      icon={<CalendarClock size={16} />}
      footer={
        <Pagination
          page={page}
          pageSize={pageSize}
          total={total}
          onChange={setPage}
        />
      }
    >
      <div className="flex flex-wrap items-center gap-2 pb-4">
        {canWrite && (
          <Button
            variant="primary"
            leftIcon={<Plus size={16} />}
            onClick={() => setEditingTask(null)}
          >
            {t("scheduledTask.create")}
          </Button>
        )}
        <Button
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={isLoading}
          loading={isLoading && tasks.length > 0}
        >
          {t("common.refresh")}
        </Button>
      </div>
      {loadError && tasks.length > 0 && (
        <div
          role="alert"
          className="mb-3 flex items-center justify-between gap-2 text-13 text-theme-error"
        >
          <span>{t("common.loadFailed")}</span>
          <Button
            disabled={isLoading}
            onClick={() => setRefreshKey((key) => key + 1)}
          >
            {t("common.retry")}
          </Button>
        </div>
      )}
      {isLoading && tasks.length === 0 ? (
        <div
          className="flex justify-center p-6"
          role="status"
          aria-label={t("common.loading")}
        >
          <LoadingSpinner />
        </div>
      ) : loadError && tasks.length === 0 ? (
        <EmptyState
          icon={<CalendarClock size={20} />}
          title={t("common.loadFailed")}
          action={
            <Button onClick={() => setRefreshKey((key) => key + 1)}>
              {t("common.retry")}
            </Button>
          }
        />
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={<CalendarClock size={20} />}
          title={t("scheduledTask.noConversationTasks")}
        />
      ) : (
        <div className="scheduled-task-panel space-y-3" aria-busy={isLoading}>
          {tasks.map((task) => (
            <div
              key={task.id}
              className={`scheduled-task-mini-card${
                task.status === "active"
                  ? " scheduled-task-mini-card--active"
                  : " scheduled-task-mini-card--paused"
              }`}
            >
              {/* Header: title + status badge */}
              <div className="scheduled-task-mini-card__header">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="break-words text-14 font-semibold text-[var(--theme-text)]">
                      {task.name}
                    </p>
                    <StatusBadge status={task.status} />
                    {pendingTaskId === task.id && (
                      <span role="status" aria-label={t("common.loading")}>
                        <LoadingSpinner size="sm" />
                      </span>
                    )}
                  </div>
                  {task.description && (
                    <p className="mt-1 text-12 leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
                      {task.description}
                    </p>
                  )}
                </div>
              </div>

              {/* Meta info pills */}
              <div className="scheduled-task-mini-card__meta">
                <span className="scheduled-task-mini-card__pill">
                  <Timer size={12} />
                  <span className="truncate">{formatTaskTrigger(task, t)}</span>
                </span>
                <span className="scheduled-task-mini-card__pill">
                  <AgentIcon
                    icon={
                      agents.find((agent) => agent.id === task.agent_id)?.icon
                    }
                    seed={task.agent_id}
                    size={14}
                  />
                  <span className="truncate">
                    {resolveAgentReferenceName(
                      task.agent_id,
                      "",
                      agents,
                      i18n.language,
                      t,
                    )}
                  </span>
                </span>
                {task.last_run_at ? (
                  <>
                    <span className="scheduled-task-mini-card__pill">
                      <Clock size={12} />
                      <span>{formatDateTimeShort(task.last_run_at)}</span>
                    </span>
                    {task.last_run_status && (
                      <RunStatusBadge status={task.last_run_status} />
                    )}
                  </>
                ) : (
                  <span className="scheduled-task-mini-card__pill scheduled-task-mini-card__pill--muted">
                    {t("scheduledTask.neverRun")}
                  </span>
                )}
              </div>

              {/* Action buttons */}
              <div className="scheduled-task-mini-card__actions">
                <button
                  onClick={() => {
                    onClose();
                    navigate(`/scheduled-tasks/${task.id}`);
                  }}
                  className="scheduled-task-button scheduled-task-button--secondary font-serif"
                  aria-label={t("scheduledTask.details")}
                  title={t("scheduledTask.details")}
                >
                  <InteractiveIcon>
                    <History size={14} />
                  </InteractiveIcon>
                  <span className="hidden sm:inline">
                    {t("scheduledTask.details", "详情")}
                  </span>
                </button>

                <div className="scheduled-task-actions">
                  {canWrite && (
                    <button
                      type="button"
                      disabled={pendingTaskId !== null || isLoading}
                      onClick={() => setEditingTask(task)}
                      className="scheduled-task-button"
                      aria-label={t("scheduledTask.edit")}
                      title={t("scheduledTask.edit")}
                    >
                      <InteractiveIcon>
                        <Pencil size={14} />
                      </InteractiveIcon>
                      <span className="hidden sm:inline">
                        {t("scheduledTask.edit")}
                      </span>
                    </button>
                  )}
                  {canWrite && task.status === "active" && (
                    <button
                      type="button"
                      disabled={pendingTaskId !== null || isLoading}
                      onClick={() => void runTaskAction(task, "pause")}
                      className="scheduled-task-button"
                      aria-label={t("scheduledTask.pause")}
                      title={t("scheduledTask.pause")}
                    >
                      <InteractiveIcon>
                        <Pause size={14} />
                      </InteractiveIcon>
                      <span className="hidden sm:inline">
                        {t("scheduledTask.pause")}
                      </span>
                    </button>
                  )}
                  {canWrite && task.status === "paused" && (
                    <button
                      type="button"
                      disabled={pendingTaskId !== null || isLoading}
                      onClick={() => void runTaskAction(task, "resume")}
                      className="scheduled-task-button scheduled-task-button--success"
                      aria-label={t("scheduledTask.resume")}
                      title={t("scheduledTask.resume")}
                    >
                      <InteractiveIcon>
                        <Play size={14} />
                      </InteractiveIcon>
                      <span className="hidden sm:inline">
                        {t("scheduledTask.resume")}
                      </span>
                    </button>
                  )}
                  {canWrite && (
                    <button
                      type="button"
                      disabled={pendingTaskId !== null || isLoading}
                      onClick={() => void runTaskAction(task, "runNow")}
                      className="scheduled-task-button scheduled-task-button--info"
                      aria-label={t("scheduledTask.runNow")}
                      title={t("scheduledTask.runNow")}
                    >
                      <InteractiveIcon>
                        <RotateCcw size={14} />
                      </InteractiveIcon>
                      <span className="hidden sm:inline">
                        {t("scheduledTask.runNow")}
                      </span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </EditorSidebar>
  );
}
