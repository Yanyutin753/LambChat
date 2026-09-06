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
import { PanelHeader } from "../common/PanelHeader";
import { PanelLoadingState } from "../common/PanelLoadingState";
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
    <div className="flex min-h-full flex-col">
      <PanelHeader
        title={t("bookmarks.title")}
        subtitle={t("bookmarks.subtitle")}
        icon={
          <Bookmark
            size={20}
            className="text-stone-600 dark:text-stone-400"
            fill="currentColor"
          />
        }
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

      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 sm:p-6">
        {status === "loading" && items.length === 0 && (
          <PanelLoadingState text={t("bookmarks.loading")} />
        )}

        {status === "error" && (
          <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
            <p className="text-sm text-[var(--theme-text-secondary)]">
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
          <div className="flex min-h-64 flex-col items-center justify-center gap-4 p-8 text-center">
            <div className="flex size-16 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] text-[var(--theme-primary)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border)),0_18px_34px_-28px_color-mix(in_srgb,var(--theme-primary)_46%,transparent)]">
              <Bookmark size={26} strokeWidth={1.5} />
            </div>
            <div>
              <p className="font-serif text-base font-semibold text-[var(--theme-text)]">
                {t("bookmarks.empty")}
              </p>
              <p className="mx-auto mt-1 max-w-88 text-sm leading-relaxed text-[var(--theme-text-secondary)]">
                {t("bookmarks.emptyHint")}
              </p>
            </div>
          </div>
        )}

        {items.length > 0 && (
          <div className="grid auto-grid-cols gap-3">
            {items.map((bookmark) => (
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
                  <p className="line-clamp-2 min-w-0 flex-1 text-left font-serif text-sm font-semibold leading-relaxed text-[var(--theme-text)] sm:text-base">
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
    </div>
  );
}
