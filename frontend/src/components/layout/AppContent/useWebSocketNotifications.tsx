import {
  SCHEDULED_PROGRESS_EVENT,
  SCHEDULED_RESULT_EVENT,
  SCHEDULED_RESULTS_REFRESH_EVENT,
} from "../../../hooks/useAgent/scheduledResults";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import {
  useWebSocket,
  type RecommendQuestionsNotification,
} from "../../../hooks/useWebSocket";
import { useAuth } from "../../../hooks/useAuth";
import { useTaskCompletionJournal } from "./taskCompletionJournal";
import { useBrowserNotification } from "../../../hooks/useBrowserNotification";
import {
  SESSIONS_READ_EVENT,
  SESSIONS_READ_INVALIDATED_EVENT,
  type SessionReadScope,
} from "../../../services/api/session";
import { sessionApi } from "../../../services/api";
import { TODAY_USAGE_REFRESH_EVENT } from "../../../hooks/useTodayUsageCost";
import { appNotificationService } from "../../../services/notifications/appNotificationService";
import {
  applySandboxPresence,
  setSandboxWsHealthy,
} from "../../../stores/sandboxStatusStore";
import {
  shouldAttemptAppTaskNotification,
  shouldAttemptBrowserNotification,
  shouldSurfaceTaskNotification,
} from "./taskNotificationGuards";
import {
  buildTaskNotificationCopy,
  buildTaskNotificationRoute,
} from "./taskNotificationContent";
import { hasTaskNotified, markTaskNotified } from "./taskNotificationDedupe";
import { selectCatchUpCandidates, toCatchUpSnapshot } from "./taskCatchUp";
import { TaskNotificationToast } from "./TaskNotificationToast";
import { isMobileDevice } from "../../../utils/mobile";

const TASK_TOAST_OPTIONS = {
  position: "top-right" as const,
  style: {
    background: "transparent",
    padding: 0,
    boxShadow: "none",
    border: "none",
    borderRadius: 0,
    overflow: "visible",
  },
};

interface CatchUpToastEntry extends ReadableTask {
  createdAt: number;
  copy: ReturnType<typeof buildTaskNotificationCopy>;
  onOpen: () => void;
}

interface ReadableTask extends SessionReadScope {
  createdAt: number;
  status: string;
}

interface UseWebSocketNotificationsOptions {
  sessionId: string | null;
  enabled?: boolean;
  onSessionUnread?: (
    sessionId: string,
    unreadCount: number,
    projectId?: string | null,
    isFavorite?: boolean,
    scheduledTaskId?: string | null,
  ) => void;
  onRecommendQuestions?: (notification: RecommendQuestionsNotification) => void;
  onSessionTaskStatus?: (data: {
    session_id: string;
    task_status: string;
  }) => void;
  /** 当前打开会话的 run 完成/失败时触发：用于对流对账（落定气泡、
   *  发现其他端推进过的新 run 时重载历史） */
  onCurrentSessionTaskComplete?: (data: {
    session_id: string;
    run_id?: string;
    status: string;
  }) => void;
}

function matchesReadScope(task: SessionReadScope, read: SessionReadScope) {
  return (
    (!read.sessionId || read.sessionId === task.sessionId) &&
    (!read.projectId || read.projectId === task.projectId) &&
    (!read.scheduledTaskId || read.scheduledTaskId === task.scheduledTaskId)
  );
}

interface TaskCompleteDelivery {
  catchUp?: boolean;
  data: {
    session_id: string;
    run_id?: string;
    status: string;
    message?: string;
    unread_count?: number;
    project_id?: string | null;
    scheduled_task_id?: string | null;
    is_favorite?: boolean;
    dedupeKey?: string;
    dedupe_key?: string;
    id?: string;
    created_at?: string;
    notification_kind?: string;
    goal_status?: string;
  };
}

export function useWebSocketNotifications({
  sessionId,
  enabled = true,
  onSessionUnread,
  onRecommendQuestions,
  onSessionTaskStatus,
  onCurrentSessionTaskComplete,
}: UseWebSocketNotificationsOptions) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const notificationUserRef = useRef(user?.id);
  notificationUserRef.current = user?.id;
  const ownedToastIds = useRef(new Map<string, ReadableTask>());
  const notificationScope = useMemo(
    () => ({
      active: false,
      generation: 0,
      userId: user?.id,
      enabled,
      startedAt: Date.now(),
    }),
    [user?.id, enabled],
  );
  const catchUpToast = useRef({
    entries: new Map<string, CatchUpToastEntry>(),
    id: null as string | null,
    updatedAt: 0,
    expiresAt: 0,
  });
  const showCatchUpToast = useCallback(() => {
    const summary = catchUpToast.current;
    const generation = notificationScope.generation;
    const isCurrent = () =>
      notificationScope.active && notificationScope.generation === generation;
    const entries = [...summary.entries.values()].sort(
      (a, b) => a.createdAt - b.createdAt,
    );
    const latest = entries.at(-1);
    if (!latest) {
      if (summary.id) {
        toast.remove(summary.id);
        ownedToastIds.current.delete(summary.id);
      }
      summary.id = null;
      return;
    }
    const duration = entries.every((entry) => entry.copy.isSuccess)
      ? 5_000
      : 10_000;
    summary.expiresAt = Date.now() + duration;
    summary.id = toast.custom(
      (currentToast) => (
        <TaskNotificationToast
          visible={currentToast.visible}
          title={
            entries.length > 1
              ? t("notification.taskUpdates", { count: entries.length })
              : latest.copy.title
          }
          body={
            entries.length > 1
              ? `${latest.copy.title}: ${latest.copy.body}`
              : latest.copy.body
          }
          openLabel={t(
            entries.length > 1
              ? "notification.openLatestConversation"
              : "notification.openConversation",
          )}
          dismissLabel={t("common.dismiss", "关闭")}
          onOpen={() => {
            if (!isCurrent()) return;
            latest.onOpen();
            summary.entries.clear();
            toast.dismiss(currentToast.id);
          }}
          onDismiss={() => {
            if (!isCurrent()) return;
            summary.entries.clear();
            toast.dismiss(currentToast.id);
          }}
        />
      ),
      { ...TASK_TOAST_OPTIONS, id: `task-catch-up:${user?.id}`, duration },
    );
    ownedToastIds.current.set(summary.id, latest);
  }, [t, user?.id, notificationScope]);
  const pendingNotifications = useRef(
    new Set<ReadableTask & { read: boolean }>(),
  );
  useEffect(() => {
    notificationScope.generation += 1;
    notificationScope.active =
      notificationScope.enabled && !!notificationScope.userId;
    const toastIds = ownedToastIds.current;
    const summary = catchUpToast.current;
    return () => {
      notificationScope.active = false;
      notificationScope.generation += 1;
      for (const id of toastIds.keys()) toast.remove(id);
      toastIds.clear();
      summary.entries.clear();
      summary.id = null;
    };
  }, [notificationScope]);
  const isNotificationScopeActive = useCallback(
    () =>
      notificationScope.active &&
      notificationUserRef.current === notificationScope.userId,
    [notificationScope],
  );
  useEffect(() => {
    const onRead = async (event: Event) => {
      const scope = (event as CustomEvent<SessionReadScope>).detail;
      const generation = notificationScope.generation;
      if (
        catchUpToast.current.id &&
        Date.now() >= catchUpToast.current.expiresAt
      ) {
        catchUpToast.current.entries.clear();
        showCatchUpToast();
      }
      const tasks = [
        ...ownedToastIds.current.values(),
        ...catchUpToast.current.entries.values(),
        ...pendingNotifications.current,
      ].filter((task) => matchesReadScope(task, scope));
      const snapshots = new Map(
        await Promise.all(
          [...new Set(tasks.map((task) => task.sessionId))].map(
            async (id) =>
              [
                id,
                id ? await sessionApi.get(id).catch(() => null) : null,
              ] as const,
          ),
        ),
      );
      if (
        !isNotificationScopeActive() ||
        notificationScope.generation !== generation
      )
        return;
      const read = (task: ReadableTask) => {
        if (!tasks.includes(task)) return false;
        const session = snapshots.get(task.sessionId);
        if (!session) return false;
        const readAt = Date.parse(session.last_read_at ?? "");
        return (
          task.createdAt <= readAt ||
          (task.status !== "waiting_human" && session.unread_count === 0)
        );
      };
      for (const [id, task] of ownedToastIds.current) {
        if (id === catchUpToast.current.id || !read(task)) continue;
        toast.remove(id);
        ownedToastIds.current.delete(id);
      }
      let summaryChanged = false;
      for (const [key, task] of catchUpToast.current.entries) {
        if (!read(task)) continue;
        catchUpToast.current.entries.delete(key);
        summaryChanged = true;
      }
      if (summaryChanged) showCatchUpToast();
      for (const task of pendingNotifications.current) {
        if (read(task)) task.read = true;
      }
    };
    window.addEventListener(SESSIONS_READ_EVENT, onRead);
    window.addEventListener(SESSIONS_READ_INVALIDATED_EVENT, onRead);
    return () => {
      window.removeEventListener(SESSIONS_READ_EVENT, onRead);
      window.removeEventListener(SESSIONS_READ_INVALIDATED_EVENT, onRead);
    };
  }, [showCatchUpToast, notificationScope, isNotificationScopeActive]);
  const navigate = useNavigate();
  const { notify, isSupported, permission } = useBrowserNotification();
  const onSessionUnreadRef = useRef(onSessionUnread);
  onSessionUnreadRef.current = onSessionUnread;
  const onRecommendQuestionsRef = useRef(onRecommendQuestions);
  onRecommendQuestionsRef.current = onRecommendQuestions;
  const onSessionTaskStatusRef = useRef(onSessionTaskStatus);
  onSessionTaskStatusRef.current = onSessionTaskStatus;
  const onCurrentSessionTaskCompleteRef = useRef(onCurrentSessionTaskComplete);
  onCurrentSessionTaskCompleteRef.current = onCurrentSessionTaskComplete;

  const deliverTaskCompletion = useCallback(
    async (notification: TaskCompleteDelivery) => {
      const generation = notificationScope.generation;
      const isCurrent = () =>
        isNotificationScopeActive() &&
        notificationScope.generation === generation;
      if (!isCurrent()) return;
      const {
        session_id,
        run_id,
        status,
        message,
        unread_count,
        project_id,
        scheduled_task_id,
        is_favorite,
      } = notification.data;

      // 跨通道去重：websocket 即时通知与回前台补发共用同一 key 空间
      const dedupeKey =
        notification.data.dedupe_key ??
        notification.data.dedupeKey ??
        (run_id ? `task:${run_id}:${status}` : undefined);
      if (dedupeKey && hasTaskNotified(dedupeKey)) return;

      // 当前会话跑完（可能在本端断连窗口内、也可能在另一端推进）：
      // 触发对流对账——落定气泡、必要时重载历史/接上新 run
      if (notification.data.notification_kind === "scheduled_result") {
        window.dispatchEvent(new Event(SCHEDULED_RESULTS_REFRESH_EVENT));
      } else if (session_id === sessionId) {
        onCurrentSessionTaskCompleteRef.current?.({
          session_id,
          run_id,
          status,
        });
      }

      const visibilityState =
        typeof document === "undefined" ? "visible" : document.visibilityState;
      const shouldSurface = shouldSurfaceTaskNotification({
        notificationSessionId: session_id,
        currentSessionId: sessionId,
        visibilityState,
      });
      const appNotificationRuntime = appNotificationService.getRuntime();
      const shouldAttemptAppNotification = shouldAttemptAppTaskNotification({
        appRuntime: appNotificationRuntime,
        notificationSessionId: session_id,
        currentSessionId: sessionId,
        visibilityState,
      });

      if (!shouldSurface && !shouldAttemptAppNotification) {
        if (dedupeKey) markTaskNotified(dedupeKey);
        sessionApi.markRead(session_id).catch(() => {});
        onSessionUnreadRef.current?.(
          session_id,
          0,
          project_id,
          is_favorite,
          scheduled_task_id,
        );
        return;
      }

      const pending = {
        sessionId: session_id,
        projectId: project_id,
        scheduledTaskId: scheduled_task_id,
        read: false,
        createdAt: Date.parse(notification.data.created_at ?? ""),
        status,
      };
      pendingNotifications.current.add(pending);
      const [sessionResult, eventsResult] = await Promise.all([
        sessionApi.get(session_id).catch((err) => {
          console.warn(
            "[AppContent] Failed to fetch session name for notification:",
            err,
          );
          const statusCode =
            err && typeof err === "object" && "status" in err
              ? err.status
              : undefined;
          if (notification.catchUp && statusCode !== 404 && statusCode !== 403)
            throw err;
          return null;
        }),
        status === "completed"
          ? sessionApi.getEvents(session_id, { run_id }).catch((err) => {
              console.warn(
                "[AppContent] Failed to fetch session events for notification:",
                err,
              );
              return null;
            })
          : Promise.resolve(null),
      ]).finally(() => pendingNotifications.current.delete(pending));
      if (!isCurrent()) return;
      const readAt = Date.parse(sessionResult?.last_read_at ?? "");
      const completedAt = Date.parse(notification.data.created_at ?? "");
      if (
        pending.read ||
        completedAt <= readAt ||
        (status !== "waiting_human" && sessionResult?.unread_count === 0) ||
        (notification.catchUp && !sessionResult)
      ) {
        if (dedupeKey) markTaskNotified(dedupeKey);
        return;
      }
      // 通知侧边栏更新 unread_count（仅非当前 session）
      const currentUnreadCount = sessionResult?.unread_count ?? unread_count;
      if (session_id !== sessionId && currentUnreadCount !== undefined) {
        onSessionUnreadRef.current?.(
          session_id,
          currentUnreadCount,
          project_id,
          is_favorite,
          scheduled_task_id,
        );
      }

      if (dedupeKey) {
        if (hasTaskNotified(dedupeKey)) return;
        markTaskNotified(dedupeKey);
      }
      const notificationCopy = buildTaskNotificationCopy({
        sessionName: sessionResult?.name,
        status:
          status === "waiting_human"
            ? "waiting_human"
            : status === "completed"
              ? "completed"
              : "failed",
        fallbackMessage: message,
        events: eventsResult?.events,
        successLabel: t("notification.taskCompleted"),
        failureLabel: t("notification.taskFailed"),
        attentionLabel: t("notification.taskNeedsAttention"),
      });

      const notificationRoute = buildTaskNotificationRoute(session_id, run_id);
      const navigateToSession = () => {
        if (!isCurrent()) return;
        navigate(notificationRoute, {
          replace: true,
          state: { externalNavigate: true, scrollToBottom: true },
        });
      };
      const isAppNotificationRuntime = appNotificationRuntime !== "unsupported";

      if (shouldAttemptAppNotification && !notification.catchUp) {
        void appNotificationService.notify({
          type: "task",
          ownerUserId: notificationScope.userId,
          title: notificationCopy.title,
          body: notificationCopy.body,
          route: notificationRoute,
          dedupeKey,
          importance: status === "completed" ? "normal" : "high",
        });
      }

      if (!shouldSurface) {
        sessionApi.markRead(session_id).catch(() => {});
        onSessionUnreadRef.current?.(session_id, 0, project_id, is_favorite);
        return;
      }

      // Show browser notification (if permitted)
      if (
        !notification.catchUp &&
        !isAppNotificationRuntime &&
        shouldAttemptBrowserNotification({
          isSupported,
          cachedPermission: permission,
          notificationSessionId: session_id,
          currentSessionId: sessionId,
          visibilityState,
        })
      ) {
        notify(notificationCopy.title, {
          body: notificationCopy.body,
          onClick: navigateToSession,
          url: notificationRoute,
        });
      }

      if (visibilityState !== "visible") {
        return;
      }

      const toastDuration = notificationCopy.isSuccess
        ? 5_000
        : isMobileDevice()
          ? 7_000
          : 10_000;

      const readScope = {
        sessionId: session_id,
        projectId:
          project_id ??
          (sessionResult?.metadata?.project_id as string | undefined),
        scheduledTaskId:
          scheduled_task_id ??
          (sessionResult?.metadata?.scheduled_task_id as string | undefined),
      };
      if (notification.catchUp) {
        const summary = catchUpToast.current;
        if (Date.now() - summary.updatedAt > 10_000) summary.entries.clear();
        summary.updatedAt = Date.now();
        summary.entries.set(
          dedupeKey ?? session_id,
          Object.assign(pending, {
            ...readScope,
            createdAt: Number.isFinite(completedAt) ? completedAt : Date.now(),
            status,
            copy: notificationCopy,
            onOpen: navigateToSession,
          }),
        );
        showCatchUpToast();
        return;
      }

      const toastId = toast.custom(
        (currentToast) => (
          <TaskNotificationToast
            visible={currentToast.visible}
            title={notificationCopy.title}
            body={notificationCopy.body}
            openLabel={t("notification.openConversation")}
            dismissLabel={t("common.dismiss", "关闭")}
            onOpen={() => {
              if (!isCurrent()) return;
              navigateToSession();
              toast.dismiss(currentToast.id);
            }}
            onDismiss={() => {
              if (!isCurrent()) return;
              toast.dismiss(currentToast.id);
            }}
          />
        ),
        {
          duration: toastDuration,
          ...TASK_TOAST_OPTIONS,
        },
      );
      ownedToastIds.current.set(toastId, Object.assign(pending, readScope));
    },
    [
      sessionId,
      t,
      navigate,
      notify,
      isSupported,
      permission,
      notificationScope,
      isNotificationScopeActive,
      showCatchUpToast,
    ],
  );

  const deliverTaskCompletionRef = useRef(deliverTaskCompletion);
  deliverTaskCompletionRef.current = deliverTaskCompletion;
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  // 回前台补发：移动端退后台后 WebSocket 被系统挂断，`task:complete`
  // 送达不了；回到前台时对比「切走时刻 vs 会话列表最新状态」，把后台
  // 期间完成的 run 补一条通知（与即时通知共用 dedupe，不会重复）。
  useEffect(() => {
    if (!enabled) return;
    const generation = notificationScope.generation;
    const isCurrent = () =>
      isNotificationScopeActive() &&
      notificationScope.generation === generation;

    const hiddenAtRef: { current: number | null } = { current: null };
    let catchUpInFlight = false;

    const handleVisibilityChange = () => {
      if (!isCurrent()) return;
      if (document.visibilityState === "hidden") {
        hiddenAtRef.current = Date.now();
        return;
      }

      const hiddenAt = hiddenAtRef.current;
      hiddenAtRef.current = null;
      if (!hiddenAt || catchUpInFlight) return;

      catchUpInFlight = true;
      void (async () => {
        try {
          const response = await sessionApi.list({ limit: 100 });
          if (!isCurrent()) return;
          const sessions = Array.isArray(response)
            ? response
            : response?.sessions ?? [];
          const candidates = selectCatchUpCandidates({
            sessions: sessions.map(toCatchUpSnapshot),
            hiddenAt,
            notBefore: notificationScope.startedAt,
            currentSessionId: sessionIdRef.current,
            hasNotified: hasTaskNotified,
          });
          for (const candidate of candidates) {
            if (!isCurrent()) return;
            await deliverTaskCompletionRef.current({
              catchUp: true,
              data: {
                session_id: candidate.session_id,
                run_id: candidate.run_id,
                created_at: candidate.created_at,
                status: candidate.status,
                unread_count: candidate.unreadCount,
                dedupeKey: candidate.dedupeKey,
              },
            });
          }
        } catch (err) {
          console.warn("[AppContent] Task catch-up check failed:", err);
        } finally {
          catchUpInFlight = false;
        }
      })();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [enabled, notificationScope, isNotificationScopeActive]);

  const restoreCompletions = useTaskCompletionJournal(
    user?.id,
    enabled,
    async (event) => {
      await deliverTaskCompletionRef.current({ data: event, catchUp: true });
    },
  );

  // WebSocket for task completion notifications
  useWebSocket({
    enabled,
    userId: user?.id,
    // daemon/机器 presence 推送直达 store（WS 健康时轮询降频为对账兜底）
    onSessionsRead: (scope) => {
      if (!isNotificationScopeActive()) return;
      window.dispatchEvent(
        new CustomEvent(SESSIONS_READ_INVALIDATED_EVENT, { detail: scope }),
      );
    },
    onSandboxPresence: (notification) => {
      if (!isNotificationScopeActive()) return;
      applySandboxPresence(notification.data);
    },
    onWsOpen: () => {
      if (!isNotificationScopeActive()) return;
      void restoreCompletions();
      window.dispatchEvent(new Event(SCHEDULED_RESULTS_REFRESH_EVENT));
      window.dispatchEvent(new Event(TODAY_USAGE_REFRESH_EVENT));
      setSandboxWsHealthy(true);
    },
    onWsClose: () => {
      if (!isNotificationScopeActive()) return;
      setSandboxWsHealthy(false);
    },
    onUsageUpdated: () => {
      if (!isNotificationScopeActive()) return;
      // 用量落库或账号额度变化后，从认证 API 刷新当前账号的用量和额度。
      window.dispatchEvent(new Event(TODAY_USAGE_REFRESH_EVENT));
    },
    onSessionTaskStatus: (data) => {
      if (!isNotificationScopeActive()) return;
      onSessionTaskStatusRef.current?.(data);
    },
    onRecommendQuestions: (notification) => {
      if (!isNotificationScopeActive()) return;
      onRecommendQuestionsRef.current?.(notification);
    },
    onScheduledProgress: (data) => {
      if (!isNotificationScopeActive()) return;
      window.dispatchEvent(
        new CustomEvent(SCHEDULED_PROGRESS_EVENT, { detail: data }),
      );
    },
    onScheduledResult: (data) => {
      if (!isNotificationScopeActive()) return;
      window.dispatchEvent(
        new CustomEvent(SCHEDULED_RESULT_EVENT, { detail: data }),
      );
    },
    onTaskComplete: (notification) => {
      if (!isNotificationScopeActive()) return;
      void deliverTaskCompletionRef.current(notification);
    },
  });
}
