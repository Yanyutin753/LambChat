import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { Check, X } from "lucide-react";
import { useWebSocket } from "../../../hooks/useWebSocket";
import { useBrowserNotification } from "../../../hooks/useBrowserNotification";
import { sessionApi } from "../../../services/api";

interface UseWebSocketNotificationsOptions {
  sessionId: string | null;
  enabled?: boolean;
}

export function useWebSocketNotifications({
  sessionId,
  enabled = true,
}: UseWebSocketNotificationsOptions) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { requestPermission, notify, isSupported, permission } =
    useBrowserNotification();

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
      data: { session_id: string; status: string; message?: string };
    }) => {
      const { session_id, status, message } = notification.data;

      // Fetch session name for notification title
      let sessionName = "";
      try {
        const session = await sessionApi.get(session_id);
        if (session?.name) {
          sessionName = session.name;
        }
      } catch (err) {
        console.warn(
          "[AppContent] Failed to fetch session name for notification:",
          err,
        );
      }

      const navigateToSession = () => {
        if (session_id !== sessionId) {
          navigate(`/chat/${session_id}`, {
            replace: true,
            state: { externalNavigate: true },
          });
        }
      };

      // Show browser notification (if permitted)
      if (isSupported && permission === "granted") {
        const baseTitle =
          status === "completed"
            ? t("notification.taskCompleted")
            : t("notification.taskFailed");
        const notificationTitle = sessionName
          ? `${sessionName} - ${baseTitle}`
          : baseTitle;

        notify(notificationTitle, {
          body: message,
          onClick: navigateToSession,
          url: `/chat/${session_id}`,
        });
      }

      // Show toast notification (clickable)
      const toastMessage =
        status === "completed"
          ? message || t("notification.taskCompleted")
          : message || t("notification.taskFailed");
      const isSuccess = status === "completed";

      toast.custom(
        (visible) => (
          <div
            className={`cursor-pointer px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 transition-all ${
              visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
            } ${
              isSuccess
                ? "bg-green-50 dark:bg-green-900/80 text-green-800 dark:text-green-200 border border-green-200 dark:border-green-700"
                : "bg-red-50 dark:bg-red-900/80 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-700"
            }`}
            onClick={(e) => {
              e.stopPropagation();
              navigateToSession();
              toast.remove();
            }}
          >
            {isSuccess ? (
              <Check
                size={18}
                className="text-green-600 dark:text-green-400 flex-shrink-0"
              />
            ) : (
              <X
                size={18}
                className="text-red-600 dark:text-red-400 flex-shrink-0"
              />
            )}
            <span className="text-sm font-medium">{toastMessage}</span>
          </div>
        ),
        { duration: 4000 },
      );
    },
  });
}
