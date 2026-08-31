import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { Bookmark, CornerRightUp, Trash2 } from "lucide-react";
import type { BookmarkItem } from "../../services/api/bookmark";
import { useBookmarks } from "../../hooks/useBookmarks";
import { toggleMessageBookmark } from "../../stores/bookmarkStore";
import { formatDateTimeShort } from "../../utils/datetime";
import {
  closePersistentToolPanel,
  isPersistentToolPanelOpen,
  openPersistentToolPanel,
  updatePersistentToolPanel,
} from "./ChatMessage/items/persistentToolPanelState";

const SESSION_BOOKMARK_PANEL_KEY = "session-bookmarks";

export function SessionBookmarksPanelBody({
  bookmarks,
  onJump,
}: {
  bookmarks: BookmarkItem[];
  onJump: (messageId: string) => void;
}) {
  const { t } = useTranslation();

  const handleRemove = (bookmark: BookmarkItem) => {
    toggleMessageBookmark({
      sessionId: bookmark.session_id,
      messageId: bookmark.message_id,
    })
      .then(() => toast.success(t("chat.message.bookmarkRemoved")))
      .catch((error) => {
        console.error("Failed to remove bookmark:", error);
        toast.error(t("chat.message.bookmarkToggleFailed"));
      });
  };

  if (bookmarks.length === 0) {
    return (
      <div className="scheduled-task-empty-state min-h-0 flex-1 px-6">
        <div className="scheduled-task-empty-state__icon h-12 w-12">
          <Bookmark size={24} />
        </div>
        <p className="scheduled-task-empty-state__body">
          {t("bookmarks.empty")}
        </p>
      </div>
    );
  }

  return (
    <div className="scheduled-task-panel flex-1 space-y-2 overflow-y-auto p-3">
      {bookmarks.map((bookmark) => (
        <div key={bookmark.id} className="scheduled-task-mini-card">
          <div className="scheduled-task-mini-card__header">
            <div className="min-w-0 flex-1">
              <p
                className="truncate text-sm font-semibold font-serif text-[var(--theme-text)]"
                title={bookmark.label ?? undefined}
              >
                {bookmark.label?.trim() || t("bookmarks.untitled")}
              </p>
            </div>
          </div>

          <div className="scheduled-task-mini-card__meta">
            <span className="scheduled-task-mini-card__pill">
              <Bookmark size={12} />
              <span>{formatDateTimeShort(bookmark.created_at)}</span>
            </span>
          </div>

          <div className="scheduled-task-mini-card__actions">
            <button
              onClick={() => onJump(bookmark.message_id)}
              className="scheduled-task-button font-serif"
              title={t("bookmarks.jump")}
            >
              <CornerRightUp size={14} />
              <span className="hidden sm:inline">{t("bookmarks.jump")}</span>
            </button>
            <div className="scheduled-task-actions">
              <button
                onClick={() => handleRemove(bookmark)}
                className="scheduled-task-button"
                title={t("bookmarks.remove")}
              >
                <Trash2 size={14} />
                <span className="hidden sm:inline">
                  {t("bookmarks.remove")}
                </span>
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * 聊天输入框上方悬浮按钮组里的「本会话书签」入口：
 * 一键查看当前会话收藏的消息（大纲/总结），点击直达并高亮。
 * 与 SessionScheduledTasksButton 的交互模式保持一致。
 */
export function SessionBookmarksButton({
  sessionId,
  className,
  onNavigateToMessage,
}: {
  sessionId: string | null;
  className?: string;
  onNavigateToMessage?: (messageId: string) => void;
}) {
  const { t } = useTranslation();
  const { items } = useBookmarks();

  const sessionBookmarks = useMemo(
    () =>
      sessionId
        ? items.filter((bookmark) => bookmark.session_id === sessionId)
        : [],
    [items, sessionId],
  );
  const count = sessionBookmarks.length;

  const panelContent = useMemo(
    () => (
      <SessionBookmarksPanelBody
        bookmarks={sessionBookmarks}
        onJump={(messageId) => {
          closePersistentToolPanel();
          onNavigateToMessage?.(messageId);
        }}
      />
    ),
    [onNavigateToMessage, sessionBookmarks],
  );

  useEffect(() => {
    if (
      !panelContent ||
      !isPersistentToolPanelOpen(SESSION_BOOKMARK_PANEL_KEY)
    ) {
      return;
    }
    updatePersistentToolPanel(
      (panel) => ({
        ...panel,
        children: panelContent,
        subtitle: count > 0 ? `${count}` : undefined,
      }),
      SESSION_BOOKMARK_PANEL_KEY,
    );
  }, [count, panelContent]);

  if (!sessionId || count === 0) return null;

  const togglePanel = () => {
    if (isPersistentToolPanelOpen(SESSION_BOOKMARK_PANEL_KEY)) {
      closePersistentToolPanel();
      return;
    }
    openPersistentToolPanel({
      title: t("bookmarks.sessionTitle"),
      icon: <Bookmark size={16} />,
      status: "idle",
      subtitle: `${count}`,
      panelKey: SESSION_BOOKMARK_PANEL_KEY,
      children: panelContent,
    });
  };

  return (
    <button
      onClick={togglePanel}
      className={
        className ??
        "absolute right-3 top-3 z-40 flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 text-theme-text-secondary shadow-sm transition-colors hover:bg-[var(--glass-bg-subtle)] hover:text-theme-text"
      }
      title={t("bookmarks.sessionTitle")}
      aria-label={t("bookmarks.sessionTitle")}
    >
      <Bookmark size={17} />
      <span className="absolute -right-1 -top-1 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-amber-500 px-1 text-10 font-semibold leading-none text-white">
        {count > 99 ? "99+" : count}
      </span>
    </button>
  );
}
