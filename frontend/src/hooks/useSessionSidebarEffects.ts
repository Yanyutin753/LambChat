/**
 * Hook encapsulating side effects for SessionSidebar:
 * mobile media query, auto-expand, project loading, session refresh,
 * new session prepending, and keyboard shortcuts.
 */

import { useEffect, useRef } from "react";
import type { BackendSession } from "../services/api";
import type { Project } from "../types";
import type { ProjectItemHandle } from "../components/sidebar/ProjectItem";
import type { ScheduledTaskItemHandle } from "../components/sidebar/ScheduledTaskSidebarItem";
import { isSessionFavorite } from "../components/sidebar/sessionFavorites";
import { isEditableEventTarget } from "../utils/editableTarget";

/** Subset of useProjectSessionList return used by effects. */
export interface SessionListHandle {
  sessions: BackendSession[];
  softRefresh: () => void;
  prependSession: (session: BackendSession) => void;
  updateSession: (session: BackendSession) => void;
}

interface UseSessionSidebarEffectsParams {
  currentSessionId: string | null;
  refreshKey?: number;
  newSession?: BackendSession | null;
  autoExpandProjectId?: string | null;
  onNewSession: () => void;
  setIsSearchOpen: (open: boolean) => void;
  setIsProjectsCollapsed: (collapsed: boolean) => void;
  setIsMobile: (mobile: boolean) => void;
  loadProjects: () => Promise<void>;
  uncategorizedList: SessionListHandle;
  projectRefs: React.MutableRefObject<Map<string, ProjectItemHandle>>;
  scheduledTaskRefs: React.MutableRefObject<
    Map<string, ScheduledTaskItemHandle>
  >;
  getProjectRef: (id: string) => ProjectItemHandle | null;
  projects: Project[];
}

export function useSessionSidebarEffects({
  currentSessionId,
  refreshKey,
  newSession,
  autoExpandProjectId,
  onNewSession,
  setIsSearchOpen,
  setIsProjectsCollapsed,
  setIsMobile,
  loadProjects,
  uncategorizedList,
  projectRefs,
  scheduledTaskRefs,
  getProjectRef,
  projects,
}: UseSessionSidebarEffectsParams) {
  // ─── Mobile media query ───────────────────────────────────────────

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [setIsMobile]);

  // ─── Auto-expand project ───────────────────────────────────────────

  useEffect(() => {
    if (autoExpandProjectId) setIsProjectsCollapsed(false);
  }, [autoExpandProjectId, setIsProjectsCollapsed]);

  // ─── Load projects on refresh ──────────────────────────────────────

  useEffect(() => {
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  // ─── Soft refresh all lists on session change ──────────────────────

  useEffect(() => {
    if (!currentSessionId) return;
    uncategorizedList.softRefresh();
    projectRefs.current.forEach((ref) => ref?.softRefresh());
    scheduledTaskRefs.current.forEach((ref) => ref?.softRefresh());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSessionId]);

  // ─── Prepend new session ──────────────────────────────────────────

  const projectCount = projects.length;
  const lastAppliedNewSessionKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (newSession && newSession.id) {
      const sessionKey = [
        newSession.id,
        newSession.updated_at,
        newSession.name ?? "",
      ].join(":");
      if (lastAppliedNewSessionKeyRef.current === sessionKey) return;
      const scheduledTaskId = newSession.metadata?.scheduled_task_id as
        | string
        | undefined;
      const projectId = newSession.metadata?.project_id as string | undefined;
      const list = scheduledTaskId
        ? scheduledTaskRefs.current.get(scheduledTaskId)
        : projectId
          ? getProjectRef(projectId)
          : uncategorizedList;
      if (list) {
        list.prependSession(newSession);
        list.updateSession(newSession);
      }
      if (isSessionFavorite(newSession)) {
        const fp = projects.find((p) => p.type === "favorites");
        if (fp) {
          const favRef = getProjectRef(fp.id);
          favRef?.prependSession(newSession);
          favRef?.updateSession(newSession);
        }
      }
      lastAppliedNewSessionKeyRef.current = sessionKey;
    }
  }, [
    newSession,
    getProjectRef,
    projectCount,
    projects,
    uncategorizedList,
    scheduledTaskRefs,
  ]);

  // ─── Keyboard shortcuts ───────────────────────────────────────────

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 正在输入框/弹窗内打字时忽略新建会话快捷键，避免误触跳回首页（issue #158）
      if (isEditableEventTarget(e.target)) return;
      const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const modifier = isMac ? e.metaKey : e.ctrlKey;
      if (modifier && e.key === "k") {
        e.preventDefault();
        setIsSearchOpen(true);
      }
      if (modifier && e.key === "n") {
        e.preventDefault();
        onNewSession();
      }
      if (modifier && e.shiftKey && (e.key === "O" || e.key === "o")) {
        e.preventDefault();
        onNewSession();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onNewSession, setIsSearchOpen]);
}
