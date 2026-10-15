/**
 * Hook encapsulating session CRUD actions for SessionSidebar:
 * move, share, toggle favorite, mark-all-read, delete, and select-and-close.
 */

import {
  useEffect,
  useState,
  useCallback,
  useRef,
  useMemo,
  type MutableRefObject,
} from "react";
import { isSessionPinned } from "../components/sidebar/sessionPin";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { sessionApi, type BackendSession } from "../services/api";
import {
  SESSIONS_READ_EVENT,
  SESSIONS_READ_INVALIDATED_EVENT,
  type SessionReadScope,
} from "../services/api/session";
import type { Project } from "../types";
import type { ProjectItemHandle } from "../components/sidebar/ProjectItem";
import type { ScheduledTaskItemHandle } from "../components/sidebar/ScheduledTaskSidebarItem";
import {
  mergeUnreadUpdate,
  type UnreadBySession,
} from "../components/sidebar/unreadCounts";
import { isSessionFavorite } from "../components/sidebar/sessionFavorites";
import { getSessionTitle } from "../components/panels/sessionHelpers";
import { useAuth } from "./useAuth";

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
  /** 侧边栏「置顶」分类的列表；置顶/取消置顶、删除等操作需要联动刷新。 */
  pinnedList?: SessionListHandle;
  projectRefs: MutableRefObject<Map<string, ProjectItemHandle>>;
  scheduledTaskRefs: MutableRefObject<Map<string, ScheduledTaskItemHandle>>;
  projects: Project[];
  currentSessionId: string | null;
  unreadBySession: UnreadBySession;
  setUnreadBySession: React.Dispatch<React.SetStateAction<UnreadBySession>>;
  onNewSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onMobileClose?: () => void;
  getProjectRef: (projectId: string) => ProjectItemHandle | null;
}

export function useSessionSidebarActions({
  uncategorizedList,
  pinnedList,
  projectRefs,
  scheduledTaskRefs,
  projects,
  currentSessionId,
  unreadBySession,
  setUnreadBySession,
  onNewSession,
  onSelectSession,
  onMobileClose,
  getProjectRef,
}: UseSessionSidebarActionsParams) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const readAccount = useMemo(
    () => ({ active: true, userId: user?.id }),
    [user?.id],
  );
  const currentReadAccount = useRef(readAccount);
  currentReadAccount.current = readAccount;
  useEffect(() => {
    readAccount.active = true;
    return () => {
      readAccount.active = false;
    };
  }, [readAccount]);
  const unreadRevisions = useRef(new Map<string, number>());
  const readLists = useRef<Array<SessionListHandle | undefined>>([]);
  readLists.current = [uncategorizedList, pinnedList];
  const unreadEntries = useRef(unreadBySession);
  unreadEntries.current = unreadBySession;

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
      unreadRevisions.current.set(
        sid,
        (unreadRevisions.current.get(sid) ?? 0) + 1,
      );
      setUnreadBySession((prev) => {
        unreadEntries.current = mergeUnreadUpdate(prev, {
          sessionId: sid,
          unreadCount: count,
          projectId,
          scheduledTaskId,
          isFavorite,
        });
        return unreadEntries.current;
      });
      const session = uncategorizedList.sessions.find((s) => s.id === sid);
      if (session) {
        uncategorizedList.updateSession({ ...session, unread_count: count });
      }
      const pinnedSession = pinnedList?.sessions.find((s) => s.id === sid);
      if (pinnedSession) {
        pinnedList?.updateSession({ ...pinnedSession, unread_count: count });
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
    [
      pinnedList,
      uncategorizedList,
      projectRefs,
      scheduledTaskRefs,
      setUnreadBySession,
    ],
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
      // 置顶分类跨项目聚合，移动项目后原条目仍是同一会话，原地更新即可
      pinnedList?.updateSession(movedSession);

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
      pinnedList,
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

  const pinRequests = useRef(new Set<string>());
  const handleTogglePin = useCallback(
    async (sessionId: string, pinOnly = false) => {
      if (pinRequests.current.has(sessionId)) return;
      if (pinOnly) {
        const session = [
          ...uncategorizedList.sessions,
          ...(pinnedList?.sessions ?? []),
          ...Array.from(projectRefs.current.values()).flatMap(
            (handle) => handle.sessions,
          ),
        ].find((item) => item.id === sessionId);
        if (!session || isSessionPinned(session)) return;
      }
      pinRequests.current.add(sessionId);
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
        // 置顶分类成员随置顶/取消置顶变化，必须重新拉取
        pinnedList?.softRefresh();
      } catch (err) {
        console.error("Failed to toggle pin:", err);
        toast.error(t("sidebar.pinToggleFailed", "置顶状态更新失败"));
      } finally {
        pinRequests.current.delete(sessionId);
      }
    },
    [pinnedList, projectRefs, t, uncategorizedList],
  );

  useEffect(() => {
    const getReadLists = () => [
      ...readLists.current,
      ...projectRefs.current.values(),
      ...scheduledTaskRefs.current.values(),
    ];
    const onRead = (event: Event) => {
      const scope = (event as CustomEvent<SessionReadScope>).detail;
      const matches = (
        id: string,
        projectId: unknown,
        scheduledTaskId: unknown,
      ) =>
        (!scope.sessionId || scope.sessionId === id) &&
        (!scope.projectId || scope.projectId === projectId) &&
        (!scope.scheduledTaskId || scope.scheduledTaskId === scheduledTaskId);
      const ids = new Set(
        getReadLists()
          .flatMap((list) => list?.sessions ?? [])
          .filter((session) =>
            matches(
              session.id,
              session.metadata?.project_id,
              session.metadata?.scheduled_task_id,
            ),
          )
          .map((session) => session.id),
      );
      for (const [id, entry] of unreadEntries.current) {
        if (matches(id, entry.projectId, entry.scheduledTaskId)) ids.add(id);
      }
      for (const id of ids) {
        const revision = unreadRevisions.current.get(id);
        void sessionApi
          .get(id)
          .then((session) => {
            // A newer completion or an account switch must win over an older HTTP snapshot.
            if (
              !session ||
              !readAccount.active ||
              currentReadAccount.current !== readAccount ||
              unreadRevisions.current.get(id) !== revision
            )
              return;
            for (const list of getReadLists()) {
              const current = list?.sessions.find((item) => item.id === id);
              if (
                current &&
                Date.parse(current.updated_at) <= Date.parse(session.updated_at)
              ) {
                list?.updateSession(session);
              }
            }
            setUnreadBySession((previous) => {
              unreadEntries.current = mergeUnreadUpdate(previous, {
                sessionId: id,
                unreadCount: session.unread_count ?? 0,
                projectId: session.metadata?.project_id as
                  | string
                  | null
                  | undefined,
                scheduledTaskId: session.metadata?.scheduled_task_id as
                  | string
                  | null
                  | undefined,
                isFavorite: isSessionFavorite(session),
              });
              return unreadEntries.current;
            });
          })
          .catch(() => {});
      }
    };
    window.addEventListener(SESSIONS_READ_EVENT, onRead);
    window.addEventListener(SESSIONS_READ_INVALIDATED_EVENT, onRead);
    return () => {
      window.removeEventListener(SESSIONS_READ_EVENT, onRead);
      window.removeEventListener(SESSIONS_READ_INVALIDATED_EVENT, onRead);
    };
  }, [
    uncategorizedList,
    pinnedList,
    projectRefs,
    scheduledTaskRefs,
    setUnreadBySession,
    readAccount,
  ]);

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
      } catch (err) {
        console.error("Failed to mark all as read:", err);
        toast.error(t("sidebar.markAllReadFailed"));
      } finally {
        setMarkingReadId(null);
      }
    },
    [t],
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
      pinnedList?.removeSession(sessionId);
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
    pinnedList,
    projectRefs,
    scheduledTaskRefs,
    uncategorizedList,
    t,
  ]);

  const confirmBatchDeleteSessions = useCallback(async () => {
    const sessionIds = batchDeleteConfirm.sessionIds;
    if (sessionIds.length === 0) return;

    try {
      const results = await Promise.allSettled(
        sessionIds.map((sessionId) => sessionApi.delete(sessionId)),
      );
      const deletedIds = sessionIds.filter(
        (_sessionId, index) => results[index]?.status === "fulfilled",
      );
      const deletedCount = deletedIds.length;

      for (const sessionId of deletedIds) {
        for (const [, handle] of projectRefs.current) {
          handle.removeSession(sessionId);
        }
        for (const [, handle] of scheduledTaskRefs.current) {
          handle.removeSession(sessionId);
        }
        uncategorizedList.removeSession(sessionId);
        pinnedList?.removeSession(sessionId);
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
    pinnedList,
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
