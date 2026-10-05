import { EmptyState } from "../common/EmptyState";
/**
 * 书签面板 - 列出当前用户收藏的消息（大纲/总结等），
 * 点击跳转到对应会话并定位高亮那条消息。
 */

import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  Archive,
  Bookmark,
  Clock,
  MessageSquare,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Pagination } from "../common/Pagination";
import { useClientPagination } from "../../hooks/useClientPagination";
import { PanelHeader } from "../common/PanelHeader";
import { BookmarksListSkeleton } from "../skeletons";
import { useBookmarks } from "../../hooks/useBookmarks";
import {
  ensureBookmarksLoaded,
  toggleMessageBookmark,
} from "../../stores/bookmarkStore";
import type { BookmarkItem } from "../../services/api/bookmark";
import { buildBookmarkNavigatePath } from "../../utils/bookmarks";
import { formatDateTimeShort } from "../../utils/datetime";

export function BookmarksPanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { status, items } = useBookmarks();
  const { page, pageSize, setPage, slice } = useClientPagination({
    total: items.length,
  });

  const handleJump = useCallback(
    (bookmark: BookmarkItem) => {
      navigate(buildBookmarkNavigatePath(bookmark));
    },
    [navigate],
  );

  const handleRemove = useCallback(
    async (bookmark: BookmarkItem) => {
      try {
        await toggleMessageBookmark({
          sessionId: bookmark.session_id,
          messageId: bookmark.message_id,
        });
        toast.success(t("chat.message.bookmarkRemoved"));
      } catch (error) {
        console.error("Failed to remove bookmark:", error);
        toast.error(t("chat.message.bookmarkToggleFailed"));
      }
    },
    [t],
  );

  const handleRefresh = useCallback(() => {
    void ensureBookmarksLoaded(true);
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PanelHeader
        title={t("bookmarks.title")}
        subtitle={t("bookmarks.subtitle")}
        illustration="panel-bookmarks"
        actions={
          <button
            type="button"
            onClick={handleRefresh}
            className="glass-card-subtle flex items-center justify-center rounded-lg p-2 text-stone-500 transition-colors dark:text-stone-400 hover:text-[var(--theme-text)]"
            title={t("bookmarks.refresh")}
            aria-label={t("bookmarks.refresh")}
          >
            <RefreshCw size={16} />
          </button>
        }
      />

      <div className="panel-body flex-1 overflow-y-auto min-h-0">
        {status === "loading" && items.length === 0 && (
          <BookmarksListSkeleton />
        )}

        {status === "error" && (
          <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
            <p className="text-14 text-[var(--theme-text-secondary)]">
              {t("bookmarks.loadFailed")}
            </p>
            <button
              type="button"
              onClick={handleRefresh}
              className="glass-tag cursor-pointer"
            >
              <RefreshCw size={12} />
              {t("bookmarks.refresh")}
            </button>
          </div>
        )}

        {status !== "error" && items.length === 0 && status !== "loading" && (
          <EmptyState
            icon={<Bookmark size={20} />}
            title={t("bookmarks.empty")}
            description={t("bookmarks.emptyHint")}
          />
        )}

        {items.length > 0 && (
          <div className="grid auto-grid-cols gap-3">
            {slice(items).map((bookmark) => (
              <div
                key={bookmark.id}
                role="button"
                tabIndex={0}
                onClick={() => handleJump(bookmark)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleJump(bookmark);
                  }
                }}
                className="glass-card group relative flex flex-col rounded-xl p-4 sm:p-5 cursor-pointer transition-all duration-200 animate-glass-enter"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="line-clamp-2 min-w-0 flex-1 text-left font-serif text-14 font-semibold leading-relaxed text-[var(--theme-text)] sm:text-16">
                    {bookmark.label?.trim() || t("bookmarks.untitled")}
                  </p>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleRemove(bookmark);
                    }}
                    className="shrink-0 rounded-md p-1.5 text-[var(--theme-text-secondary)] opacity-0 transition-all group-hover:opacity-100 focus-visible:opacity-100 hover:text-red-500 dark:hover:text-red-400 max-sm:opacity-100"
                    title={t("bookmarks.remove")}
                    aria-label={t("bookmarks.remove")}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <span className="glass-tag">
                    <MessageSquare size={12} />
                    <span className="max-w-44 truncate">
                      {bookmark.session_name ||
                        t("fileLibrary.untitledSession")}
                    </span>
                  </span>
                  {!bookmark.session_is_active && (
                    <span className="glass-tag">
                      <Archive size={12} />
                      {t("bookmarks.archivedSession")}
                    </span>
                  )}
                  <span className="glass-tag">
                    <Clock size={12} />
                    {formatDateTimeShort(bookmark.created_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="panel-pagination empty:hidden">
        <Pagination
          page={page}
          pageSize={pageSize}
          total={items.length}
          onChange={setPage}
        />
      </div>
    </div>
  );
}
