export interface TaskNotificationSurfaceInput {
  notificationSessionId: string;
  currentSessionId: string | null;
  visibilityState: DocumentVisibilityState;
}

export function shouldSurfaceTaskNotification({
  notificationSessionId,
  currentSessionId,
  visibilityState,
}: TaskNotificationSurfaceInput): boolean {
  return !(
    currentSessionId === notificationSessionId && visibilityState === "visible"
  );
}
