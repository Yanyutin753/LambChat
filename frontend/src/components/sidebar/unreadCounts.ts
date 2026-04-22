import type { BackendSession } from "../../services/api/session";

export interface UnreadEntry {
  count: number;
  projectId: string | null;
}

export type UnreadBySession = Map<string, UnreadEntry>;

export function mergeUnreadUpdate(
  unreadBySession: UnreadBySession,
  update: {
    sessionId: string;
    unreadCount: number;
    projectId?: string | null;
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
  });
  return next;
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
  const loadedCount = loadedSessions.reduce(
    (total, session) => total + Math.max(0, session.unread_count ?? 0),
    0,
  );
  const externalCount = Array.from(unreadBySession.entries()).reduce(
    (total, [sessionId, entry]) =>
      entry.projectId === null && !loadedIds.has(sessionId)
        ? total + entry.count
        : total,
    0,
  );
  return loadedCount + externalCount;
}

export function formatUnreadCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}
