import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { sessionApi } from "../../services/api/session";
import { getSessionTitle } from "../panels/sessionHelpers";
import { APP_NAME } from "../../constants";
import type { BackendSession } from "../../services/api/session";

interface RecentChatsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSession: (sessionId: string) => void;
  currentSessionId?: string | null;
  anchorEl: HTMLElement | null;
}

export function RecentChatsDialog({
  isOpen,
  onClose,
  onSelectSession,
  currentSessionId,
  anchorEl,
}: RecentChatsDialogProps) {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number }>({
    top: 0,
    left: 0,
  });

  const loadSessions = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await sessionApi.list({ limit: 20 });
      const list = Array.isArray(response) ? response : response.sessions;
      setSessions(list);
    } catch (error) {
      console.error("Failed to load recent sessions:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) loadSessions();
  }, [isOpen, loadSessions]);

  useEffect(() => {
    if (!isOpen || !anchorEl) return;
    const rect = anchorEl.getBoundingClientRect();
    const panelWidth = 280;
    const panelMaxHeight = 480;
    let top = rect.bottom + 2;
    let left = rect.right + 2;

    if (left + panelWidth > window.innerWidth) {
      left = rect.left - panelWidth - 2;
    }
    if (top + panelMaxHeight > window.innerHeight) {
      top = window.innerHeight - panelMaxHeight - 8;
    }

    setPosition({ top, left });
  }, [isOpen, anchorEl]);

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
      <div className="flex items-center gap-2 px-4 pt-3 pb-2 border-b border-stone-200/60 dark:border-stone-800/60 shrink-0">
        <img
          src="/icons/icon.svg"
          alt={APP_NAME}
          className="size-5 rounded-full object-cover"
        />
        <span className="text-sm font-bold text-stone-800 dark:text-stone-100 font-serif leading-none">
          {t("sidebar.recentChats")}
        </span>
      </div>

      {/* Session list */}
      <div className="overflow-y-auto max-h-[420px] py-1">
        {isLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 size={18} className="animate-spin text-stone-400" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-10 text-xs text-stone-400 dark:text-stone-500">
            {t("sidebar.noSessions") || "No recent chats"}
          </div>
        ) : (
          sessions.map((session) => (
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
                  {new Date(session.updated_at).toLocaleString()}
                </div>
              </div>
              {session.unread_count != null && session.unread_count > 0 && (
                <span className="shrink-0 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium leading-none text-white">
                  {session.unread_count}
                </span>
              )}
            </button>
          ))
        )}
      </div>
    </div>,
    document.body,
  );
}
