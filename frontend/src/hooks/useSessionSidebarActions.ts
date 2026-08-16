/**
 * Hook encapsulating session CRUD actions for SessionSidebar:
 * move, share, toggle favorite, mark-all-read, delete, and select-and-close.
 */

import {
  useState,
  useCallback,
  useRef,
  useMemo,
  type MutableRefObject,
} from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { sessionApi, type BackendSession } from "../services/api";
import type { Project } from "../types";
import type { ProjectItemHandle } from "../components/sidebar/ProjectItem";
import type { ScheduledTaskItemHandle } from "../components/sidebar/ScheduledTaskSidebarItem";
import {
  mergeUnreadUpdate,
  type UnreadBySession,
} from "../components/sidebar/unreadCounts";
import { isSessionFavorite } from "../components/sidebar/sessionFavorites";
import { getSessionTitle } from "../components/panels/sessionHelpers";

/** Subset of useProjectSessionList return used by action handlers. */
export interface SessionListHandle {
  sessions: BackendSession[];
  updateSession: (session: BackendSession) => void;
  removeSession: (sessionId: string) => void;
  prependSession: (session: BackendSession) => void;
  softRefresh: () => void;
  refresh: () => Promise<void>;
}

interface UseSessionSidebarActionsParams {
  uncategorizedList: SessionListHandle;
  projectRefs: MutableRefObject<Map<string, ProjectItemHandle>>;
  scheduledTaskRefs: MutableRefObject<Map<string, ScheduledTaskItemHandle>>;
  projects: Project[];
  currentSessionId: string | null;
  setUnreadBySession: React.Dispatch<React.SetStateAction<UnreadBySession>>;
  onNewSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onMobileClose?: () => void;
  getProjectRef: (projectId: string) => ProjectItemHandle | null;
}

export function useSessionSidebarActions({
  uncategorizedList,
  projectRefs,
  scheduledTaskRefs,
  projects,
  currentSessionId,
  setUnreadBySession,
  onNewSession,
  onSelectSession,
  onMobileClose,
  getProjectRef,
}: UseSessionSidebarActionsParams) {
  const { t } = useTranslation();

  // ─── Share dialog state ───────────────────────────────────────────

  const [shareDialogSessionId, setShareDialogSessionId] = useState<
    string | null
  >(null);
  const [shareDialogSessionName, setShareDialogSessionName] = useState("");

  // ─── Delete confirmation state ────────────────────────────────────

  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    sessionId: string | null;
  }>({ isOpen: false, sessionId: null });
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState<{
    isOpen: boolean;
    sessionIds: string[];
  }>({ isOpen: false, sessionIds: [] });
  const [batchMoveConfirm, setBatchMoveConfirm] = useState<{
    isOpen: boolean;
    sessionIds: string[];
    projectId: string | null;
  }>({ isOpen: false, sessionIds: [], projectId: null });

  // ─── Mark-all-read loading tracker ────────────────────────────────

  const [markingReadId, setMarkingReadId] = useState<string | null>(null);

  // ─── Unread update (used by imperative handle & selectAndClose) ──

  const handleSessionUnread = useCallback(
    (
      sid: string,
      count: number,
      projectId?: string | null,
      isFavorite?: boolean,
      scheduledTaskId?: string | null,
    ) => {
      setUnreadBySession((prev) =>
        mergeUnreadUpdate(prev, {
          sessionId: sid,
          unreadCount: count,
          projectId,
          scheduledTaskId,
          isFavorite,
        }),
      );
      const session = uncategorizedList.sessions.find((s) => s.id === sid);
      if (session) {
        uncategorizedList.updateSession({ ...session, unread_count: count });
      }
      for (const [, handle] of projectRefs.current) {
        const s = handle.sessions.find((s) => s.id === sid);
        if (s) {
          handle.updateSession({ ...s, unread_count: count });
        }
      }
      for (const [, handle] of scheduledTaskRefs.current) {
        const s = handle.sessions.find((s) => s.id === sid);
        if (s) {
          handle.updateSession({ ...s, unread_count: count });
        }
      }
    },
    [uncategorizedList, projectRefs, scheduledTaskRefs, setUnreadBySession],
  );

  // ─── Move session ──────────────────────────────────────────────────

  const applyMovedSession = useCallback(
    (sessionId: string, movedSession: BackendSession) => {
      const favorite = isSessionFavorite(movedSession);
      const movedProjectId =
        (movedSession.metadata?.project_id as string | null | undefined) ??
        null;

      for (const [, handle] of projectRefs.current) {
        handle.removeSession(sessionId);
      }
      for (const [, handle] of scheduledTaskRefs.current) {
        handle.removeSession(sessionId);
      }
      uncategorizedList.removeSession(sessionId);

      if (movedProjectId) {
        getProjectRef(movedProjectId)?.prependSession(movedSession);
      } else {
        uncategorizedList.prependSession(movedSession);
      }
      if (favorite) {
        const fp = projects.find((p) => p.type === "favorites");
        if (fp) getProjectRef(fp.id)?.prependSession(movedSession);
      }

      setUnreadBySession((prev) =>
        mergeUnreadUpdate(prev, {
          sessionId,
          unreadCount: movedSession.unread_count ?? 0,
          projectId: movedProjectId,
          scheduledTaskId:
            (movedSession.metadata?.scheduled_task_id as
              | string
              | null
              | undefined) ?? null,
          isFavorite: favorite,
        }),
      );
    },
    [
      getProjectRef,
      projects,
      projectRefs,
      scheduledTaskRefs,
      setUnreadBySession,
      uncategorizedList,
    ],
  );

  const handleMoveSession = useCallback(
    async (sessionId: string, projectId: string | null) => {
      try {
        const response = await sessionApi.moveToProject(sessionId, projectId);
        if (response.session) {
          applyMovedSession(sessionId, response.session);
        }
      } catch (err) {
        console.error("Failed to move session:", err);
        toast.error(t("sidebar.sessionMoveFailed"));
      }
    },
    [applyMovedSession, t],
  );

  const handleMoveSessionRef = useRef(handleMoveSession);
  handleMoveSessionRef.current = handleMoveSession;

  const handleBatchMoveSessions = useCallback(
    async (sessionIds: string[], projectId: string | null) => {
      if (sessionIds.length === 0) return;

      const results = await Promise.allSettled(
        sessionIds.map(async (sessionId) => {
          const response = await sessionApi.moveToProject(sessionId, projectId);
          if (response.session) applyMovedSession(sessionId, response.session);
        }),
      );
      const failedCount = results.filter(
        (result) => result.status === "rejected",
      ).length;

      if (failedCount > 0) {
        toast.error(
          t("sidebar.batchMovePartialFailed", {
            count: failedCount,
            defaultValue: "{{count}} 个会话移动失败",
          }),
        );
        return;
      }

      toast.success(
        t("sidebar.batchMoved", {
          count: sessionIds.length,
          defaultValue: "已移动 {{count}} 个会话",
        }),
      );
    },
    [applyMovedSession, t],
  );

  const confirmBatchMoveSessions = useCallback(async () => {
    const { sessionIds, projectId } = batchMoveConfirm;
    if (sessionIds.length === 0) return;
    try {
      await handleBatchMoveSessions(sessionIds, projectId);
    } finally {
      setBatchMoveConfirm({ isOpen: false, sessionIds: [], projectId: null });
    }
  }, [batchMoveConfirm, handleBatchMoveSessions]);

  // ─── Share session ────────────────────────────────────────────────

  const handleShareSession = useCallback(
    (sessionId: string) => {
      let title = "";
      for (const [, handle] of projectRefs.current) {
        const s = handle.sessions.find((s) => s.id === sessionId);
        if (s) {
          title = getSessionTitle(s, t);
          break;
        }
      }
      if (!title) {
        for (const [, handle] of scheduledTaskRefs.current) {
          const s = handle.sessions.find((s) => s.id === sessionId);
          if (s) {
            title = getSessionTitle(s, t);
            break;
          }
        }
      }
      if (!title) {
        const s = uncategorizedList.sessions.find((s) => s.id === sessionId);
        if (s) title = getSessionTitle(s, t);
      }
      setShareDialogSessionId(sessionId);
      setShareDialogSessionName(title || t("sidebar.newChat"));
    },
    [projectRefs, scheduledTaskRefs, uncategorizedList, t],
  );

  // ─── Toggle favorite ──────────────────────────────────────────────

  const handleToggleFavorite = useCallback(
    async (sessionId: string) => {
      try {
        const response = await sessionApi.toggleFavorite(sessionId);
        const updatedSession = response.session;
        const favoritesProject = projects.find((p) => p.type === "favorites");
        const favoritesRef = favoritesProject
          ? getProjectRef(favoritesProject.id)
          : null;

        if (uncategorizedList.sessions.some((s) => s.id === sessionId)) {
          uncategorizedList.updateSession(updatedSession);
        }
        for (const [, handle] of projectRefs.current) {
          const exists = handle.sessions.some((s) => s.id === sessionId);
          if (!exists) continue;
          if (
            favoritesRef &&
            handle === favoritesRef &&
            !response.is_favorite
          ) {
            handle.removeSession(sessionId);
            continue;
          }
          handle.updateSession(updatedSession);
        }
        if (response.is_favorite && favoritesRef) {
          favoritesRef.prependSession(updatedSession);
          favoritesRef.updateSession(updatedSession);
        }
        setUnreadBySession((prev) =>
          mergeUnreadUpdate(prev, {
            sessionId,
            unreadCount: updatedSession.unread_count ?? 0,
            projectId:
              (updatedSession.metadata?.project_id as
                | string
                | null
                | undefined) ?? null,
            scheduledTaskId:
              (updatedSession.metadata?.scheduled_task_id as
                | string
                | null
                | undefined) ?? null,
            isFavorite: response.is_favorite,
          }),
        );
      } catch (err) {
        console.error("Failed to toggle favorite:", err);
        toast.error(t("sidebar.favoriteToggleFailed", "收藏状态更新失败"));
      }
    },
    [
      getProjectRef,
      projectRefs,
      projects,
      t,
      uncategorizedList,
      setUnreadBySession,
    ],
  );

  // ─── Toggle pin ───────────────────────────────────────────────────

  const handleTogglePin = useCallback(
    async (sessionId: string) => {
      try {
        const response = await sessionApi.togglePin(sessionId);
        const updatedSession = response.session;
        if (uncategorizedList.sessions.some((s) => s.id === sessionId)) {
          uncategorizedList.updateSession(updatedSession);
          // updateSession keeps list order; refetch so the pinned session
          // moves to its pinned-first position (mirrors mark-all-read).
          uncategorizedList.softRefresh();
        }
        for (const [, handle] of projectRefs.current) {
          if (handle.sessions.some((s) => s.id === sessionId)) {
            handle.updateSession(updatedSession);
            handle.softRefresh();
          }
        }
      } catch (err) {
        console.error("Failed to toggle pin:", err);
        toast.error(t("sidebar.pinToggleFailed", "置顶状态更新失败"));
      }
    },
    [projectRefs, t, uncategorizedList],
  );

  // ─── Mark all read ────────────────────────────────────────────────

  const handleMarkAllRead = useCallback(
    async (opts?: { projectId?: string; scheduledTaskId?: string }) => {
      const key =
        !opts?.projectId && !opts?.scheduledTaskId
          ? "all"
          : opts!.projectId
            ? `project-${opts!.projectId}`
            : `task-${opts!.scheduledTaskId}`;

      setMarkingReadId(key);

      try {
        await sessionApi.markAllRead(opts);

        // Optimistic update: clear matching unread entries after API success
        const clearSessionList = (
          sessionList: SessionListHandle,
          filterFn?: (s: BackendSession) => boolean,
        ) => {
          sessionList.sessions.forEach((s) => {
            if (filterFn && !filterFn(s)) return;
            if ((s.unread_count ?? 0) > 0) {
              sessionList.updateSession({ ...s, unread_count: 0 });
            }
          });
        };

        const isUncategorized = !opts?.projectId && !opts?.scheduledTaskId;

        if (isUncategorized) {
          setUnreadBySession(() => new Map());
          clearSessionList(uncategorizedList);
          uncategorizedList.softRefresh();
        } else if (opts!.projectId) {
          setUnreadBySession((prev) => {
            const next = new Map(prev);
            for (const [sid, entry] of next) {
              if (entry.projectId === opts!.projectId) {
                next.delete(sid);
              }
            }
            return next;
          });
          clearSessionList(
            uncategorizedList,
            (s) => s.metadata?.project_id === opts!.projectId,
          );
          const handle = getProjectRef(opts!.projectId);
          if (handle) {
            handle.sessions.forEach((s) => {
              if ((s.unread_count ?? 0) > 0) {
                handle.updateSession({ ...s, unread_count: 0 });
              }
            });
            handle.softRefresh();
          }
        } else if (opts!.scheduledTaskId) {
          setUnreadBySession((prev) => {
            const next = new Map(prev);
            for (const [sid, entry] of next) {
              if (entry.scheduledTaskId === opts!.scheduledTaskId) {
                next.delete(sid);
              }
            }
            return next;
          });
          for (const [, handle] of scheduledTaskRefs.current) {
            handle.sessions.forEach((s) => {
              if (
                (s.unread_count ?? 0) > 0 &&
                s.metadata?.scheduled_task_id === opts!.scheduledTaskId
              ) {
                handle.updateSession({ ...s, unread_count: 0 });
              }
            });
            handle.softRefresh();
          }
        }
      } catch (err) {
        console.error("Failed to mark all as read:", err);
        toast.error(t("sidebar.markAllReadFailed"));
      } finally {
        setMarkingReadId(null);
      }
    },
    [
      getProjectRef,
      scheduledTaskRefs,
      t,
      uncategorizedList,
      setUnreadBySession,
    ],
  );

  const confirmDeleteSession = useCallback(async () => {
    const sessionId = deleteConfirm.sessionId;
    if (!sessionId) return;
    try {
      await sessionApi.delete(sessionId);
      for (const [, handle] of projectRefs.current) {
        handle.removeSession(sessionId);
      }
      for (const [, handle] of scheduledTaskRefs.current) {
        handle.removeSession(sessionId);
      }
      uncategorizedList.removeSession(sessionId);
      if (currentSessionId === sessionId) onNewSession();
      toast.success(t("sidebar.sessionDeleted"));
    } catch (err) {
      console.error("Failed to delete session:", err);
      toast.error(t("sidebar.deleteFailed"));
    } finally {
      setDeleteConfirm({ isOpen: false, sessionId: null });
    }
  }, [
    deleteConfirm,
    currentSessionId,
    onNewSession,
    projectRefs,
    scheduledTaskRefs,
    uncategorizedList,
    t,
  ]);

  const confirmBatchDeleteSessions = useCallback(async () => {
    const sessionIds = batchDeleteConfirm.sessionIds;
    if (sessionIds.length === 0) return;

    let deletedCount = 0;
    try {
      const results = await Promise.allSettled(
        sessionIds.map((sessionId) => sessionApi.delete(sessionId)),
      );
      const deletedIds = sessionIds.filter(
        (_sessionId, index) => results[index]?.status === "fulfilled",
      );
      deletedCount = deletedIds.length;

      for (const sessionId of deletedIds) {
        for (const [, handle] of projectRefs.current) {
          handle.removeSession(sessionId);
        }
        for (const [, handle] of scheduledTaskRefs.current) {
          handle.removeSession(sessionId);
        }
        uncategorizedList.removeSession(sessionId);
      }

      setUnreadBySession((prev) => {
        const next = new Map(prev);
        deletedIds.forEach((sessionId) => next.delete(sessionId));
        return next;
      });

      if (currentSessionId && deletedIds.includes(currentSessionId)) {
        onNewSession();
      }

      const failedCount = sessionIds.length - deletedCount;
      if (failedCount > 0) {
        toast.error(
          t("sidebar.batchDeletePartialFailed", {
            count: failedCount,
            defaultValue: "{{count}} 个会话删除失败",
          }),
        );
      } else {
        toast.success(
          t("sidebar.batchDeleted", {
            count: deletedCount,
            defaultValue: "已删除 {{count}} 个会话",
          }),
        );
      }
    } catch (err) {
      console.error("Failed to batch delete sessions:", err);
      toast.error(t("sidebar.deleteFailed"));
    } finally {
      setBatchDeleteConfirm({ isOpen: false, sessionIds: [] });
    }
  }, [
    batchDeleteConfirm.sessionIds,
    currentSessionId,
    onNewSession,
    projectRefs,
    scheduledTaskRefs,
    setUnreadBySession,
    t,
    uncategorizedList,
  ]);

  // ─── Select session helper (mobile close) ───────────────────────

  const selectAndClose = useCallback(
    (sessionId: string) => {
      const uncategorizedSession = uncategorizedList.sessions.find(
        (session) => session.id === sessionId,
      );
      const existingSession =
        uncategorizedSession ??
        Array.from(scheduledTaskRefs.current.values())
          .flatMap((handle) => handle.sessions)
          .find((session) => session.id === sessionId) ??
        Array.from(projectRefs.current.values())
          .flatMap((handle) => handle.sessions)
          .find((session) => session.id === sessionId);
      handleSessionUnread(
        sessionId,
        0,
        (existingSession?.metadata?.project_id as string | null | undefined) ??
          null,
        existingSession ? isSessionFavorite(existingSession) : undefined,
        (existingSession?.metadata?.scheduled_task_id as
          | string
          | null
          | undefined) ?? null,
      );
      onSelectSession(sessionId);
      onMobileClose?.();
    },
    [
      projectRefs,
      scheduledTaskRefs,
      uncategorizedList,
      handleSessionUnread,
      onSelectSession,
      onMobileClose,
    ],
  );

  return useMemo(
    () => ({
      handleSessionUnread,
      handleMoveSession,
      handleMoveSessionRef,
      handleBatchMoveSessions,
      batchMoveConfirm,
      setBatchMoveConfirm,
      confirmBatchMoveSessions,
      handleShareSession,
      handleToggleFavorite,
      handleTogglePin,
      handleMarkAllRead,
      markingReadId,
      shareDialogSessionId,
      setShareDialogSessionId,
      shareDialogSessionName,
      deleteConfirm,
      setDeleteConfirm,
      confirmDeleteSession,
      batchDeleteConfirm,
      setBatchDeleteConfirm,
      confirmBatchDeleteSessions,
      selectAndClose,
    }),
    [
      handleSessionUnread,
      handleMoveSession,
      handleMoveSessionRef,
      handleBatchMoveSessions,
      batchMoveConfirm,
      confirmBatchMoveSessions,
      handleShareSession,
      handleToggleFavorite,
      handleTogglePin,
      handleMarkAllRead,
      markingReadId,
      shareDialogSessionId,
      shareDialogSessionName,
      deleteConfirm,
      confirmDeleteSession,
      batchDeleteConfirm,
      confirmBatchDeleteSessions,
      selectAndClose,
    ],
  );
}
