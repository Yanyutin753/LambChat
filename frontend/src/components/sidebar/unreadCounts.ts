import type { BackendSession } from "../../services/api/session";
import { isSessionFavorite } from "./sessionFavorites";

export interface UnreadEntry {
  count: number;
  projectId: string | null;
  scheduledTaskId?: string | null;
  isFavorite?: boolean;
}

export type UnreadBySession = Map<string, UnreadEntry>;

export function mergeUnreadUpdate(
  unreadBySession: UnreadBySession,
  update: {
    sessionId: string;
    unreadCount: number;
    projectId?: string | null;
    scheduledTaskId?: string | null;
    isFavorite?: boolean;
  },
): UnreadBySession {
  const next = new Map(unreadBySession);
  if (update.unreadCount <= 0) {
    next.delete(update.sessionId);
    return next;
  }

  const previous = next.get(update.sessionId);
  next.set(update.sessionId, {
    count: update.unreadCount,
    projectId: update.projectId ?? previous?.projectId ?? null,
    scheduledTaskId:
      update.scheduledTaskId ?? previous?.scheduledTaskId ?? null,
    isFavorite: update.isFavorite ?? previous?.isFavorite ?? false,
  });
  return next;
}

function getScheduledTaskId(session: BackendSession): string | null {
  const value = session.metadata?.scheduled_task_id;
  return typeof value === "string" ? value : null;
}

export function getUnreadCountForProject({
  projectId,
  loadedSessions,
  unreadBySession,
}: {
  projectId: string;
  loadedSessions: BackendSession[];
  unreadBySession: UnreadBySession;
}): number {
  const loadedIds = new Set(loadedSessions.map((session) => session.id));
  const loadedCount = loadedSessions.reduce(
    (total, session) => total + Math.max(0, session.unread_count ?? 0),
    0,
  );
  const externalCount = Array.from(unreadBySession.entries()).reduce(
    (total, [sessionId, entry]) =>
      entry.projectId === projectId && !loadedIds.has(sessionId)
        ? total + entry.count
        : total,
    0,
  );
  return loadedCount + externalCount;
}

export function getUnreadCountForUncategorized({
  loadedSessions,
  unreadBySession,
}: {
  loadedSessions: BackendSession[];
  unreadBySession: UnreadBySession;
}): number {
  const loadedIds = new Set(loadedSessions.map((session) => session.id));
  const loadedCount = loadedSessions
    .filter((session) => getScheduledTaskId(session) === null)
    .reduce(
      (total, session) => total + Math.max(0, session.unread_count ?? 0),
      0,
    );
  const externalCount = Array.from(unreadBySession.entries()).reduce(
    (total, [sessionId, entry]) =>
      entry.projectId === null &&
      !entry.scheduledTaskId &&
      !loadedIds.has(sessionId)
        ? total + entry.count
        : total,
    0,
  );
  return loadedCount + externalCount;
}

export function getUnreadCountForScheduledTask({
  scheduledTaskId,
  loadedSessions,
  unreadBySession,
}: {
  scheduledTaskId: string;
  loadedSessions: BackendSession[];
  unreadBySession: UnreadBySession;
}): number {
  const loadedIds = new Set(loadedSessions.map((session) => session.id));
  const loadedCount = loadedSessions.reduce(
    (total, session) => total + Math.max(0, session.unread_count ?? 0),
    0,
  );
  const externalCount = Array.from(unreadBySession.entries()).reduce(
    (total, [sessionId, entry]) =>
      entry.scheduledTaskId === scheduledTaskId && !loadedIds.has(sessionId)
        ? total + entry.count
        : total,
    0,
  );
  return loadedCount + externalCount;
}

export function getExternalUnreadCountForScheduledTasks(
  unreadBySession: UnreadBySession,
  excludedTaskIds: ReadonlySet<string> = new Set(),
): number {
  return Array.from(unreadBySession.values()).reduce((total, entry) => {
    if (!entry.scheduledTaskId || excludedTaskIds.has(entry.scheduledTaskId)) {
      return total;
    }
    return total + entry.count;
  }, 0);
}

export function getUnreadCountForFavorites(
  loadedSessions: BackendSession[],
  unreadBySession: UnreadBySession,
): number {
  const loadedIds = new Set(loadedSessions.map((session) => session.id));
  const loadedCount = loadedSessions
    .filter(isSessionFavorite)
    .reduce(
      (total, session) => total + Math.max(0, session.unread_count ?? 0),
      0,
    );
  const externalCount = Array.from(unreadBySession.entries()).reduce(
    (total, [sessionId, entry]) =>
      entry.isFavorite && !loadedIds.has(sessionId)
        ? total + entry.count
        : total,
    0,
  );
  return loadedCount + externalCount;
}

export function formatUnreadCount(count: number): string {
  return String(Math.min(count, 99));
}
