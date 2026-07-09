import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { X } from "lucide-react";
import { useWebSocket } from "../../../hooks/useWebSocket";
import { useBrowserNotification } from "../../../hooks/useBrowserNotification";
import { sessionApi } from "../../../services/api";
import { appNotificationService } from "../../../services/notifications/appNotificationService";
import {
  shouldAttemptAppTaskNotification,
  shouldAttemptBrowserNotification,
  shouldSurfaceTaskNotification,
} from "./taskNotificationGuards";
import { buildTaskNotificationCopy } from "./taskNotificationContent";
import { ImageWithSkeleton } from "../../chat/ChatMessage/ImageWithSkeleton";
import { isMobileDevice } from "../../../utils/mobile";

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
}

export function useWebSocketNotifications({
  sessionId,
  enabled = true,
  onSessionUnread,
}: UseWebSocketNotificationsOptions) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { notify, isSupported, permission } = useBrowserNotification();
  const onSessionUnreadRef = useRef(onSessionUnread);
  onSessionUnreadRef.current = onSessionUnread;

  // WebSocket for task completion notifications
  useWebSocket({
    enabled,
    onTaskComplete: async (notification: {
      data: {
        session_id: string;
        run_id: string;
        status: string;
        message?: string;
        unread_count?: number;
        project_id?: string | null;
        scheduled_task_id?: string | null;
        is_favorite?: boolean;
      };
    }) => {
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

      // 通知侧边栏更新 unread_count（仅非当前 session）
      if (session_id !== sessionId && unread_count !== undefined) {
        onSessionUnreadRef.current?.(
          session_id,
          unread_count,
          project_id,
          is_favorite,
          scheduled_task_id,
        );
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

      const [sessionResult, eventsResult] = await Promise.all([
        sessionApi.get(session_id).catch((err) => {
          console.warn(
            "[AppContent] Failed to fetch session name for notification:",
            err,
          );
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
      ]);

      const notificationCopy = buildTaskNotificationCopy({
        sessionName: sessionResult?.name,
        status: status === "completed" ? "completed" : "failed",
        fallbackMessage: message,
        events: eventsResult?.events,
        successLabel: t("notification.taskCompleted"),
        failureLabel: t("notification.taskFailed"),
      });

      const navigateToSession = () => {
        navigate(`/chat/${session_id}`, {
          replace: true,
          state: { externalNavigate: true, scrollToBottom: true },
        });
      };
      const notificationRoute = `/chat/${session_id}`;
      const isAppNotificationRuntime = appNotificationRuntime !== "unsupported";

      if (shouldAttemptAppNotification) {
        void appNotificationService.notify({
          type: "task",
          title: notificationCopy.title,
          body: notificationCopy.body,
          route: notificationRoute,
          dedupeKey: `task:${run_id}:${status}`,
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

      toast.custom(
        (currentToast) => (
          <div
            className={`group relative pointer-events-auto cursor-pointer select-none max-w-[min(92vw,24rem)] w-full rounded-3xl border border-stone-100 bg-white px-4 py-3.5 text-black shadow-2xl transition-all dark:border-stone-800 dark:bg-stone-900 dark:text-white ${
              currentToast.visible
                ? "translate-y-0 opacity-100"
                : "translate-y-1.5 opacity-0"
            }`}
            onClick={(e) => {
              e.stopPropagation();
              navigateToSession();
              toast.dismiss(currentToast.id);
            }}
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                toast.dismiss(currentToast.id);
              }}
              className="absolute top-2 right-2 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-black/10 text-stone-400 opacity-0 transition-all hover:bg-black/20 hover:text-stone-600 group-hover:opacity-100 dark:bg-white/10 dark:text-stone-500 dark:hover:bg-white/20 dark:hover:text-stone-300"
              aria-label={t("common.dismiss", "关闭")}
            >
              <X size={14} />
            </button>

            <div className="flex items-center gap-3 text-left">
              <div className="flex shrink-0 items-center justify-center">
                <ImageWithSkeleton
                  src="/icons/icon.svg"
                  alt=""
                  skipUrlResolve
                  inline
                  className="size-8 rounded-lg"
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="line-clamp-1 text-[13px] font-semibold leading-tight">
                  {notificationCopy.title}
                </div>
                <div className="mt-0.5 line-clamp-1 text-xs leading-snug text-stone-500 dark:text-stone-400">
                  {notificationCopy.body}
                </div>
              </div>
            </div>
          </div>
        ),
        {
          duration: toastDuration,
          position: "top-right",
          style: {
            background: "transparent",
            padding: 0,
            boxShadow: "none",
            border: "none",
            borderRadius: 0,
            overflow: "visible",
          },
        },
      );
    },
  });
}
