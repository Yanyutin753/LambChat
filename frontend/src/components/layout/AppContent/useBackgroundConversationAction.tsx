import { useCallback, useEffect, useMemo } from "react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { TaskNotificationToast } from "./TaskNotificationToast";
import { buildTaskNotificationRoute } from "./taskNotificationContent";

interface BackgroundConversationOptions {
  userId?: string;
  sessionId: string | null;
  runId: string | null;
  ready: boolean;
  onDetach: () => void;
}
export function useBackgroundConversationAction({ userId, sessionId, runId, ready, onDetach }: BackgroundConversationOptions) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const scope = useMemo(() => ({ userId, active: false, toastIds: new Set<string>() }), [userId]);
  useEffect(() => {
    scope.active = true;
    return () => {
      scope.active = false;
      for (const id of scope.toastIds) toast.remove(id);
      scope.toastIds.clear();
    };
  }, [scope]);
  return useCallback(() => {
    if (!scope.active || !ready || !sessionId || !runId) return;
    const route = buildTaskNotificationRoute(sessionId, runId);
    onDetach();
    const id = toast.custom((notification) => <TaskNotificationToast
      visible={notification.visible} title={t("chat.backgroundRunning")}
      body={t("chat.backgroundContinueHint")} openLabel={t("notification.openConversation")}
      dismissLabel={t("common.dismiss")}
      onOpen={() => { if (scope.active) navigate(route); toast.dismiss(notification.id); }}
      onDismiss={() => toast.dismiss(notification.id)} />, { duration: 7000 });
    scope.toastIds.add(id);
  }, [scope, sessionId, runId, ready, onDetach, navigate, t]);
}
