import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { useInView } from "react-intersection-observer";
import { useTranslation } from "react-i18next";
import type { BackendSession } from "../../services/api/session";
import { scheduledTaskApi } from "../../services/api/scheduledTask";
import type { Project } from "../../types";
import type { ScheduledTask, TaskSession } from "../../types/scheduledTask";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { SessionItem } from "./SessionItem";
import { isSessionFavorite } from "./sessionFavorites";
import {
  getUnreadCountForScheduledTask,
  type UnreadBySession,
} from "./unreadCounts";
import { MarkAllReadBadge } from "./MarkAllReadBadge";

const PAGE_SIZE = 20;

export interface ScheduledTaskItemHandle {
  refresh: () => Promise<void>;
  softRefresh: () => Promise<void>;
  prependSession: (session: BackendSession) => void;
  removeSession: (sessionId: string) => void;
  updateSession: (session: BackendSession) => void;
  sessions: BackendSession[];
}

interface ScheduledTaskSidebarItemProps {
  task: ScheduledTask;
  currentSessionId: string | null;
  allProjects: Project[];
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onMoveSession: (sessionId: string, projectId: string | null) => void;
  onToggleFavorite?: (sessionId: string) => void;
  onShareSession?: (sessionId: string) => void;
  onUnreadCountChange?: (taskId: string, unreadCount: number) => void;
  scrollRoot?: Element | null;
  draggingSessionId?: string | null;
  unreadBySession?: UnreadBySession;
  onMarkAllRead?: (opts?: { scheduledTaskId?: string }) => void;
  markingReadId?: string | null;
  selectionMode?: boolean;
  selectedSessionIds?: Set<string>;
  onToggleSessionSelected?: (sessionId: string) => void;
}

function dedupSessions(sessions: BackendSession[]): BackendSession[] {
  const seen = new Set<string>();
  return sessions.filter((session) => {
    if (seen.has(session.id)) return false;
    seen.add(session.id);
    return true;
  });
}

function toBackendSession(session: TaskSession): BackendSession {
  const createdAt = session.created_at ?? session.updated_at ?? "";
  const updatedAt = session.updated_at ?? session.created_at ?? "";
  return {
    id: session.id,
    agent_id: session.agent_id,
    created_at: createdAt,
    updated_at: updatedAt,
    is_active: session.is_active,
    name: session.name ?? undefined,
    metadata: session.metadata ?? {},
    unread_count: session.unread_count,
  };
}

export const ScheduledTaskSidebarItem = forwardRef<
  ScheduledTaskItemHandle,
  ScheduledTaskSidebarItemProps
>(function ScheduledTaskSidebarItem(
  {
    task,
    currentSessionId,
    allProjects,
    onSelectSession,
    onDeleteSession,
    onMoveSession,
    onToggleFavorite,
    onShareSession,
    onUnreadCountChange,
    scrollRoot,
    draggingSessionId,
    unreadBySession = new Map(),
    onMarkAllRead,
    markingReadId,
    selectionMode = false,
    selectedSessionIds = new Set(),
    onToggleSessionSelected,
  },
  ref,
) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  const sessionsRef = useRef(sessions);
  useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [skip, setSkip] = useState(0);
  const loadedCountRef = useRef(PAGE_SIZE);
  const hasLoadedRef = useRef(false);

  const { ref: loadMoreRef, inView } = useInView({
    threshold: 0.1,
    root: scrollRoot ?? undefined,
  });

  const fetchSessions = useCallback(
    async (reset = false) => {
      const targetSkip = reset ? 0 : skip;
      if (!reset && (isLoadingMore || !hasMore)) return;

      if (reset) {
        setIsLoading(true);
        setSkip(0);
      } else {
        setIsLoadingMore(true);
      }

      try {
        const response = await scheduledTaskApi.getSessions(
          task.id,
          targetSkip,
          PAGE_SIZE,
        );
        const fetchedSessions = response.items.map(toBackendSession);
        const nextHasMore = targetSkip + response.items.length < response.total;

        if (reset) {
          setSessions(dedupSessions(fetchedSessions));
          localDeductionsRef.current = 0;
          setSkip(response.items.length);
          loadedCountRef.current = Math.max(PAGE_SIZE, fetchedSessions.length);
        } else {
          setSessions((prev) => dedupSessions([...prev, ...fetchedSessions]));
          setSkip(targetSkip + response.items.length);
          loadedCountRef.current = Math.max(
            loadedCountRef.current,
            targetSkip + fetchedSessions.length,
          );
        }
        setHasMore(response.items.length > 0 ? nextHasMore : false);
      } catch (error) {
        console.error("Failed to load scheduled task sessions:", error);
        if (reset) {
          setSessions([]);
          setHasMore(false);
        }
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [hasMore, isLoadingMore, skip, task.id],
  );

  const refresh = useCallback(async () => {
    await fetchSessions(true);
  }, [fetchSessions]);

  const softRefresh = useCallback(async () => {
    try {
      const limit = Math.min(100, Math.max(PAGE_SIZE, loadedCountRef.current));
      const response = await scheduledTaskApi.getSessions(task.id, 0, limit);
      const latest = response.items.map(toBackendSession);
      setSessions(dedupSessions(latest));
      localDeductionsRef.current = 0;
      setSkip(response.items.length);
      loadedCountRef.current = Math.max(PAGE_SIZE, latest.length);
      setHasMore(response.items.length < response.total);
    } catch {
      // Best-effort refresh, same behavior as project list soft refresh.
    }
  }, [task.id]);

  const prependSession = useCallback((session: BackendSession) => {
    setSessions((prev) => {
      if (prev.some((s) => s.id === session.id)) return prev;
      return [session, ...prev];
    });
  }, []);

  const removeSession = useCallback((sessionId: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
  }, []);

  // Track locally-cleared unread counts so the fallback badge
  // (used when not all sessions are loaded) stays accurate after mark-read.
  const localDeductionsRef = useRef(0);

  const updateSession = useCallback((session: BackendSession) => {
    // Compute deduction from latest sessions state (avoids side effect
    // inside the state updater, which React may invoke twice in
    // StrictMode, and ref mutations are not rolled back).
    const current = sessionsRef.current;
    const idx = current.findIndex((s) => s.id === session.id);
    if (idx !== -1) {
      const prevUnread = current[idx].unread_count ?? 0;
      const nextUnread = session.unread_count ?? 0;
      if (prevUnread > nextUnread) {
        localDeductionsRef.current += prevUnread - nextUnread;
      }
    }
    setSessions((prev) => prev.map((s) => (s.id === session.id ? session : s)));
  }, []);

  const unreadCount = getUnreadCountForScheduledTask({
    scheduledTaskId: task.id,
    loadedSessions: sessions,
    unreadBySession,
  });
  const backendUnread = Math.max(
    0,
    (task.unread_count ?? 0) - localDeductionsRef.current,
  );
  const displayedUnreadCount =
    hasLoadedRef.current && !hasMore
      ? unreadCount
      : Math.max(backendUnread, unreadCount);

  useEffect(() => {
    onUnreadCountChange?.(task.id, displayedUnreadCount);
  }, [onUnreadCountChange, task.id, displayedUnreadCount]);

  useEffect(() => {
    if (isExpanded && !hasLoadedRef.current) {
      hasLoadedRef.current = true;
      void refresh();
    }
  }, [isExpanded, refresh]);

  useEffect(() => {
    if (inView && hasMore && !isLoadingMore && !isLoading) {
      void fetchSessions(false);
    }
  }, [fetchSessions, hasMore, inView, isLoading, isLoadingMore]);

  useImperativeHandle(
    ref,
    () => ({
      refresh,
      softRefresh,
      prependSession,
      removeSession,
      updateSession,
      sessions,
    }),
    [
      refresh,
      softRefresh,
      prependSession,
      removeSession,
      updateSession,
      sessions,
    ],
  );

  return (
    <div className="scheduled-task-panel">
      <div
        onClick={() => setIsExpanded((value) => !value)}
        className={`group relative flex h-10 cursor-pointer items-center gap-3 rounded-[10px] px-[9px] transition-colors ${
          isExpanded
            ? "bg-stone-100/60 dark:bg-stone-800/40"
            : "hover:bg-stone-100 dark:hover:bg-stone-800/30"
        }`}
        title={task.name}
      >
        <span
          className="shrink-0 inline-flex items-center justify-center overflow-hidden text-20"
          style={{ width: 20, height: 20, fontSize: 20, lineHeight: 1 }}
        >
          {task.status === "active" ? "⏰" : "🕐"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-13 text-stone-600 transition-colors group-hover:text-stone-700 dark:text-stone-400 dark:group-hover:text-stone-300">
            {task.name}
          </div>
        </div>
        {displayedUnreadCount > 0 && (
          <MarkAllReadBadge
            count={displayedUnreadCount}
            badgeId={`task-${task.id}`}
            markingReadId={markingReadId ?? null}
            onMarkAllRead={() => onMarkAllRead?.({ scheduledTaskId: task.id })}
            tooltip={t("sidebar.markAllRead")}
          />
        )}
      </div>

      {isExpanded && (
        <div className="ml-3 mt-0.5 flex flex-col gap-px">
          {isLoading ? (
            <div className="flex justify-center py-3">
              <LoadingSpinner size="sm" color="text-[var(--theme-primary)]" />
            </div>
          ) : sessions.length > 0 ? (
            <>
              {sessions.map((session) => (
                <SessionItem
                  key={session.id}
                  session={session}
                  isActive={session.id === currentSessionId}
                  projects={allProjects}
                  onSelect={() => onSelectSession(session.id)}
                  onDelete={() => onDeleteSession(session.id)}
                  onMoveToProject={(projectId) =>
                    onMoveSession(session.id, projectId)
                  }
                  currentProjectId={null}
                  onShare={
                    onShareSession
                      ? () => onShareSession(session.id)
                      : undefined
                  }
                  onToggleFavorite={
                    onToggleFavorite
                      ? () => onToggleFavorite(session.id)
                      : undefined
                  }
                  onSessionUpdate={updateSession}
                  isFavorite={isSessionFavorite(session)}
                  onDragStartTouch={undefined}
                  isDraggingTouch={draggingSessionId === session.id}
                  selectionMode={selectionMode}
                  isSelected={selectedSessionIds.has(session.id)}
                  onToggleSelected={() => onToggleSessionSelected?.(session.id)}
                />
              ))}
              {hasMore && (
                <div ref={loadMoreRef} className="flex justify-center py-2">
                  {isLoadingMore && (
                    <LoadingSpinner
                      size="xs"
                      color="text-[var(--theme-primary)]"
                    />
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="rounded-lg px-[9px] py-2 text-12 text-stone-400 dark:text-stone-500">
              {t("sidebar.noSessions", "暂无会话")}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
