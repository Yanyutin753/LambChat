import { useState } from "react";
import { Bookmark } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useBookmarks } from "../../../hooks/useBookmarks";
import { toggleMessageBookmark } from "../../../stores/bookmarkStore";
import { isBookmarked } from "../../../utils/bookmarks";

interface BookmarkButtonProps {
  sessionId: string;
  messageId: string;
  runId?: string | null;
  /** 做书签时存下的消息摘要（列表展示用） */
  label?: string | null;
}

/** 消息操作栏的书签按钮：收藏/取消收藏当前消息 */
export function BookmarkButton({
  sessionId,
  messageId,
  runId,
  label,
}: BookmarkButtonProps) {
  const { t } = useTranslation();
  const { items } = useBookmarks();
  const [busy, setBusy] = useState(false);
  const active = isBookmarked(items, sessionId, messageId);

  const handleClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { bookmarked } = await toggleMessageBookmark({
        sessionId,
        messageId,
        runId,
        label,
      });
      toast.success(
        bookmarked
          ? t("chat.message.bookmarkAdded")
          : t("chat.message.bookmarkRemoved"),
      );
    } catch (error) {
      console.error("Failed to toggle bookmark:", error);
      toast.error(t("chat.message.bookmarkToggleFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={busy}
      className={clsx(
        "p-1.5 rounded-md transition-colors",
        "hover:bg-stone-200 dark:hover:bg-stone-700",
        active
          ? "text-amber-500 dark:text-amber-400"
          : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
        busy && "opacity-60 cursor-wait",
      )}
      title={
        active
          ? t("chat.message.removeBookmark")
          : t("chat.message.addBookmark")
      }
      aria-label={
        active
          ? t("chat.message.removeBookmark")
          : t("chat.message.addBookmark")
      }
      aria-pressed={active}
    >
      <Bookmark size={16} fill={active ? "currentColor" : "none"} />
    </button>
  );
}
