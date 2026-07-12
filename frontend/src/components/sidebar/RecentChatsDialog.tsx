import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useInView } from "react-intersection-observer";
import { sessionApi } from "../../services/api/session";
import { getSessionTitle } from "../panels/sessionHelpers";
import { APP_NAME } from "../../constants";
import { BrandLogo } from "../common/BrandLogo";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import type { BackendSession } from "../../services/api/session";
import { formatDateTime } from "../../utils/datetime";
import {
  getNextRecentChatsState,
  type RecentChatsPaginationState,
} from "./recentChatsPagination";
import { MarkAllReadBadge } from "./MarkAllReadBadge";

interface RecentChatsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSession: (sessionId: string) => void;
  currentSessionId?: string | null;
  anchorEl: HTMLElement | null;
  unreadCount?: number;
  onMarkAllRead?: (opts?: {
    projectId?: string;
    scheduledTaskId?: string;
  }) => void;
  markingReadId?: string | null;
}

const PAGE_SIZE = 20;

const initialPaginationState: RecentChatsPaginationState = {
  sessions: [],
  skip: 0,
  hasMore: false,
};

export function RecentChatsDialog({
  isOpen,
  onClose,
  onSelectSession,
  currentSessionId,
  anchorEl,
  unreadCount = 0,
  onMarkAllRead,
  markingReadId,
}: RecentChatsDialogProps) {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [scrollRoot, setScrollRoot] = useState<HTMLDivElement | null>(null);
  const anchorRef = useRef(anchorEl);
  anchorRef.current = anchorEl;

  const position = useStickyDropdownPosition(anchorRef, isOpen, (rect) => {
    const panelWidth = 280;
    const panelMaxHeight = 480;
    let top = rect.bottom + 2;
    let left = rect.right + 2;
    if (left + panelWidth > window.innerWidth)
      left = rect.left - panelWidth - 2;
    if (top + panelMaxHeight > window.innerHeight)
      top = window.innerHeight - panelMaxHeight - 8;
    return { top, left };
  });
  const paginationRef = useRef<RecentChatsPaginationState>(
    initialPaginationState,
  );
  const isFetchingRef = useRef(false);

  const { ref: loadMoreRef, inView } = useInView({
    root: scrollRoot ?? undefined,
    rootMargin: "80px 0px",
    threshold: 0.1,
  });

  const applyPaginationState = useCallback(
    (next: RecentChatsPaginationState) => {
      paginationRef.current = next;
      setSessions(next.sessions);
      setHasMore(next.hasMore);
    },
    [],
  );

  const loadSessions = useCallback(
    async (reset = false) => {
      if (isFetchingRef.current) return;

      const current = reset ? initialPaginationState : paginationRef.current;
      if (!reset && !current.hasMore) return;

      isFetchingRef.current = true;
      if (reset) {
        setIsLoading(true);
      } else {
        setIsLoadingMore(true);
      }

      try {
        const response = await sessionApi.list({
          limit: PAGE_SIZE,
          skip: reset ? 0 : current.skip,
        });
        const list = Array.isArray(response) ? response : response.sessions;
        const next = getNextRecentChatsState({
          previousSessions: current.sessions,
          pageSessions: list,
          previousSkip: current.skip,
          reset,
          hasMore: Array.isArray(response) ? false : response.has_more,
        });
        applyPaginationState(next);
      } catch (error) {
        console.error("Failed to load recent sessions:", error);
      } finally {
        isFetchingRef.current = false;
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [applyPaginationState],
  );

  const resetSessions = useCallback(() => {
    applyPaginationState(initialPaginationState);
    void loadSessions(true);
  }, [applyPaginationState, loadSessions]);

  useEffect(() => {
    if (isOpen) resetSessions();
  }, [isOpen, resetSessions]);

  useEffect(() => {
    if (isOpen && inView && hasMore && !isLoading && !isLoadingMore) {
      void loadSessions(false);
    }
  }, [hasMore, inView, isLoading, isLoadingMore, isOpen, loadSessions]);

  useEffect(() => {
    if (!isOpen) {
      isFetchingRef.current = false;
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [isOpen]);

  const renderLoadingRows = (count: number) => (
    <div className="px-4 py-2 space-y-1">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-0 py-2.5">
          <div className="flex-1 min-w-0 space-y-1.5">
            <div
              className="skeleton-line h-[13px] rounded-md"
              style={{ width: i % 2 === 0 ? "75%" : "60%" }}
            />
            <div
              className="skeleton-line h-[11px] rounded-md !opacity-50"
              style={{ width: "40%" }}
            />
          </div>
        </div>
      ))}
    </div>
  );

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        anchorEl?.contains(target) ||
        document.getElementById("recent-chats-popover")?.contains(target)
      ) {
        return;
      }
      onClose();
    };
    const timer = setTimeout(() => {
      document.addEventListener("click", handler);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("click", handler);
    };
  }, [isOpen, onClose, anchorEl]);

  useEffect(() => {
    if (isOpen) {
      const handler = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      document.addEventListener("keydown", handler);
      return () => document.removeEventListener("keydown", handler);
    }
  }, [isOpen, onClose]);

  if (!isOpen || !anchorEl) return null;

  return createPortal(
    <div
      id="recent-chats-popover"
      className="fixed z-[301] w-[280px] rounded-xl shadow-xl border border-stone-200/60 dark:border-stone-800/60 overflow-hidden animate-scale-in bg-[var(--theme-bg-sidebar)]"
      style={{
        top: position.top,
        left: position.left,
        maxHeight: "480px",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-stone-200/60 dark:border-stone-800/60 shrink-0">
        <div className="flex items-center gap-2">
          <BrandLogo alt={APP_NAME} className="h-5" />
          <span className="text-sm font-bold text-stone-800 dark:text-stone-100 font-serif leading-none">
            {t("sidebar.recentChats")}
          </span>
        </div>
        {unreadCount > 0 && (
          <MarkAllReadBadge
            count={unreadCount}
            badgeId="all"
            markingReadId={markingReadId ?? null}
            onMarkAllRead={() => onMarkAllRead?.()}
            title={t("sidebar.markAllRead")}
          />
        )}
      </div>

      {/* Session list */}
      <div ref={setScrollRoot} className="overflow-y-auto max-h-[420px] py-1">
        {isLoading ? (
          renderLoadingRows(6)
        ) : sessions.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-xs text-stone-400 dark:text-stone-500">
            {t("sidebar.noSessions") || "No recent chats"}
          </div>
        ) : (
          <>
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => {
                  onSelectSession(session.id);
                  onClose();
                }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 transition-colors text-left group ${
                  session.id === currentSessionId
                    ? "bg-stone-100 dark:bg-stone-800/60"
                    : "hover:bg-stone-100 dark:hover:bg-stone-800/40"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div
                    className={`truncate text-[13px] ${
                      session.id === currentSessionId
                        ? "text-stone-800 dark:text-stone-100 font-medium"
                        : "text-stone-600 dark:text-stone-300 group-hover:text-stone-700 dark:group-hover:text-stone-200"
                    }`}
                  >
                    {getSessionTitle(session, t)}
                  </div>
                  <div className="text-[11px] text-stone-400 dark:text-stone-500 mt-0.5">
                    {formatDateTime(session.updated_at)}
                  </div>
                </div>
                {session.unread_count != null && session.unread_count > 0 && (
                  <span className="shrink-0 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium leading-none text-white">
                    {session.unread_count}
                  </span>
                )}
              </button>
            ))}
            {hasMore && (
              <div ref={loadMoreRef} className="min-h-8">
                {isLoadingMore && renderLoadingRows(2)}
              </div>
            )}
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
