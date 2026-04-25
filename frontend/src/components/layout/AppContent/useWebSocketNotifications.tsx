import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { X } from "lucide-react";
import { useWebSocket } from "../../../hooks/useWebSocket";
import { useBrowserNotification } from "../../../hooks/useBrowserNotification";
import { sessionApi } from "../../../services/api";
import { shouldSurfaceTaskNotification } from "./taskNotificationGuards";
import { buildTaskNotificationCopy } from "./taskNotificationContent";
import { isMobileDevice } from "../../../utils/mobile";

interface UseWebSocketNotificationsOptions {
  sessionId: string | null;
  enabled?: boolean;
  onSessionUnread?: (
    sessionId: string,
    unreadCount: number,
    projectId?: string | null,
  ) => void;
}

export function useWebSocketNotifications({
  sessionId,
  enabled = true,
  onSessionUnread,
}: UseWebSocketNotificationsOptions) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { requestPermission, notify, isSupported, permission } =
    useBrowserNotification();
  const onSessionUnreadRef = useRef(onSessionUnread);
  onSessionUnreadRef.current = onSessionUnread;

  // Request notification permission on first interaction
  useEffect(() => {
    if (isSupported && permission === "default") {
      requestPermission();
    }
  }, [isSupported, permission, requestPermission]);

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
      };
    }) => {
      const { session_id, run_id, status, message, unread_count, project_id } =
        notification.data;

      // 通知侧边栏更新 unread_count（仅非当前 session）
      if (session_id !== sessionId && unread_count !== undefined) {
        onSessionUnreadRef.current?.(session_id, unread_count, project_id);
      }

      const visibilityState =
        typeof document === "undefined" ? "visible" : document.visibilityState;
      const shouldSurface = shouldSurfaceTaskNotification({
        notificationSessionId: session_id,
        currentSessionId: sessionId,
        visibilityState,
      });

      if (!shouldSurface) {
        sessionApi.markRead(session_id).catch(() => {});
        onSessionUnreadRef.current?.(session_id, 0, project_id);
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

      // Show browser notification (if permitted)
      if (isSupported && permission === "granted") {
        notify(notificationCopy.title, {
          body: notificationCopy.body,
          onClick: navigateToSession,
          url: `/chat/${session_id}`,
        });
      }

      toast.custom(
        (visible) => (
          <div
            className={`group relative pointer-events-auto cursor-pointer select-none max-w-[min(92vw,24rem)] w-full rounded-3xl border border-stone-100 bg-white px-4 py-3.5 text-black shadow-2xl transition-all dark:border-stone-800 dark:bg-stone-900 dark:text-white ${
              visible
                ? "translate-y-0 opacity-100"
                : "translate-y-1.5 opacity-0"
            }`}
            onClick={(e) => {
              e.stopPropagation();
              navigateToSession();
              toast.remove();
            }}
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                toast.remove();
              }}
              className="absolute top-1.5 right-1.5 z-10 rounded-full p-0.5 text-stone-400 opacity-0 transition-opacity hover:text-stone-600 group-hover:opacity-100 dark:text-stone-500 dark:hover:text-stone-300"
              aria-label="Dismiss notification"
            >
              <X size={12} />
            </button>

            <div className="flex items-center gap-3 text-left">
              <div className="flex shrink-0 items-center justify-center">
                <img
                  src="/icons/icon.svg"
                  alt=""
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
          duration: isMobileDevice() ? 5_000 : 10_000,
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
