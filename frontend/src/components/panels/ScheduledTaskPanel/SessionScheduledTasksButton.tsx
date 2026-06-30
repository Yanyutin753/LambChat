import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import {
  Bot,
  CalendarClock,
  Clock,
  History,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Timer,
} from "lucide-react";
import { scheduledTaskApi } from "../../../services/api/scheduledTask";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types";
import type { ScheduledTask } from "../../../types/scheduledTask";
import { formatDateTimeShort } from "../../../utils/datetime";
import {
  closePersistentToolPanel,
  isPersistentToolPanelOpen,
  openPersistentToolPanel,
  updatePersistentToolPanel,
} from "../../chat/ChatMessage/items/persistentToolPanelState";
import { RunStatusBadge, StatusBadgeForTask as StatusBadge } from "./Badges";
import { formatTaskTrigger } from "./utils";

const SESSION_TASK_PANEL_KEY = "session-scheduled-tasks";

function SessionScheduledTaskPanelBody({
  sessionId,
  refreshKey,
  onMutate,
}: {
  sessionId: string;
  refreshKey?: string | number;
  onMutate?: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canWrite = hasPermission(Permission.SCHEDULED_TASK_WRITE);
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchTasks = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await scheduledTaskApi.listBySession(sessionId, 0, 50);
      setTasks(response.items);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.loadFailed");
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, t]);

  useEffect(() => {
    void fetchTasks();
  }, [fetchTasks, refreshKey]);

  const runTaskAction = async (
    task: ScheduledTask,
    action: "pause" | "resume" | "runNow",
  ) => {
    if (!canWrite) {
      toast.error(t("errors.noPermission"));
      return;
    }

    try {
      if (action === "pause") {
        await scheduledTaskApi.pause(task.id);
        toast.success(t("scheduledTask.pausedSuccess"));
      } else if (action === "resume") {
        await scheduledTaskApi.resume(task.id);
        toast.success(t("scheduledTask.resumedSuccess"));
      } else {
        await scheduledTaskApi.runNow(task.id);
        toast.success(t("scheduledTask.triggeredSuccess"));
      }
      await fetchTasks();
      onMutate?.();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.operationFailed");
      toast.error(message);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {isLoading && tasks.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-stone-400" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="scheduled-task-empty-state min-h-0 flex-1 px-6">
          <div className="scheduled-task-empty-state__icon h-12 w-12">
            <CalendarClock size={24} />
          </div>
          <p className="scheduled-task-empty-state__body">
            {t(
              "scheduledTask.noConversationTasks",
              "当前会话暂无 agent 创建的定时任务",
            )}
          </p>
        </div>
      ) : (
        <div className="scheduled-task-panel flex-1 space-y-2 overflow-y-auto p-3">
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
                    <p className="truncate text-sm font-semibold text-[var(--theme-text)]">
                      {task.name}
                    </p>
                    <StatusBadge status={task.status} />
                  </div>
                  {task.description && (
                    <p className="mt-1 text-xs leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
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
                  <Bot size={12} />
                  <span className="truncate">{task.agent_id}</span>
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
                    closePersistentToolPanel();
                    const params = new URLSearchParams({
                      taskId: task.id,
                      taskName: task.name,
                    });
                    navigate(`/scheduled-tasks?${params.toString()}`);
                  }}
                  className="scheduled-task-button scheduled-task-button--secondary"
                  title={t("scheduledTask.details", "详情")}
                >
                  <History size={14} />
                  <span className="hidden sm:inline">
                    {t("scheduledTask.details", "详情")}
                  </span>
                </button>

                <div className="scheduled-task-actions">
                  {canWrite && task.status === "active" && (
                    <button
                      onClick={() => void runTaskAction(task, "pause")}
                      className="scheduled-task-button"
                      title={t("scheduledTask.pause")}
                    >
                      <Pause size={14} />
                      <span className="hidden sm:inline">
                        {t("scheduledTask.pause")}
                      </span>
                    </button>
                  )}
                  {canWrite && task.status === "paused" && (
                    <button
                      onClick={() => void runTaskAction(task, "resume")}
                      className="scheduled-task-button scheduled-task-button--success"
                      title={t("scheduledTask.resume")}
                    >
                      <Play size={14} />
                      <span className="hidden sm:inline">
                        {t("scheduledTask.resume")}
                      </span>
                    </button>
                  )}
                  {canWrite && (
                    <button
                      onClick={() => void runTaskAction(task, "runNow")}
                      className="scheduled-task-button scheduled-task-button--info"
                      title={t("scheduledTask.runNow")}
                    >
                      <RotateCcw size={14} />
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
    </div>
  );
}

export function SessionScheduledTasksButton({
  sessionId,
  refreshKey,
  className,
}: {
  sessionId: string | null;
  refreshKey?: string | number;
  className?: string;
}) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(Permission.SCHEDULED_TASK_READ);
  const [count, setCount] = useState(0);

  const fetchCount = useCallback(async () => {
    if (!sessionId || !canRead) {
      setCount(0);
      return;
    }
    try {
      const response = await scheduledTaskApi.listBySession(sessionId, 0, 1);
      setCount(response.total);
    } catch {
      setCount(0);
    }
  }, [canRead, sessionId]);

  useEffect(() => {
    void fetchCount();
  }, [fetchCount, refreshKey]);

  const panelContent = useMemo(() => {
    if (!sessionId) return null;
    return (
      <SessionScheduledTaskPanelBody
        sessionId={sessionId}
        refreshKey={refreshKey}
        onMutate={fetchCount}
      />
    );
  }, [fetchCount, refreshKey, sessionId]);

  useEffect(() => {
    if (!panelContent || !isPersistentToolPanelOpen(SESSION_TASK_PANEL_KEY)) {
      return;
    }
    updatePersistentToolPanel(
      (panel) => ({
        ...panel,
        children: panelContent,
        subtitle: count > 0 ? `${count}` : undefined,
      }),
      SESSION_TASK_PANEL_KEY,
    );
  }, [count, panelContent]);

  if (!sessionId || !canRead || count === 0) return null;

  const togglePanel = () => {
    if (isPersistentToolPanelOpen(SESSION_TASK_PANEL_KEY)) {
      closePersistentToolPanel();
      return;
    }
    openPersistentToolPanel({
      title: t("scheduledTask.conversationTasks", "会话定时任务"),
      icon: <CalendarClock size={16} />,
      status: "idle",
      subtitle: `${count}`,
      panelKey: SESSION_TASK_PANEL_KEY,
      children: panelContent,
    });
  };

  return (
    <button
      onClick={togglePanel}
      className={
        className ??
        "absolute right-3 top-3 z-40 flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 text-theme-text-secondary shadow-sm transition-colors hover:bg-[var(--glass-bg-subtle)] hover:text-theme-text"
      }
      title={t("scheduledTask.conversationTasks", "会话定时任务")}
    >
      <CalendarClock size={17} />
      <span className="absolute -right-1 -top-1 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-orange-500 px-1 text-[10px] font-semibold leading-none text-white">
        {count > 99 ? "99+" : count}
      </span>
    </button>
  );
}
