import { useCallback, type KeyboardEvent, type MouseEvent } from "react";
import { formatUnreadCount } from "./unreadCounts";
import { Tooltip } from "../common/Tooltip";

interface MarkAllReadBadgeProps {
  /** Current unread count to display. */
  count: number;
  /** Unique identifier for this badge, used to match against the global loading state. */
  badgeId: string;
  /** The currently-loading badge ID (or null). */
  markingReadId: string | null;
  /** Callback invoked when the user clicks or presses Enter/Space. */
  onMarkAllRead: () => void;
  /** Tooltip text shown on hover (desktop) or long press (touch). */
  tooltip: string;
}

/**
 * A small circular red badge that displays an unread count and acts as a
 * "mark all as read" button.  When the badge is in a loading state it renders
 * a tiny spinning indicator instead of the count.
 */
export function MarkAllReadBadge({
  count,
  badgeId,
  markingReadId,
  onMarkAllRead,
  tooltip,
}: MarkAllReadBadgeProps) {
  const isLoading = markingReadId === badgeId;
  const isSingleDigit = count >= 1 && count <= 9;

  const handleClick = useCallback(
    (e: MouseEvent) => {
      e.stopPropagation();
      onMarkAllRead();
    },
    [onMarkAllRead],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.stopPropagation();
        e.preventDefault();
        onMarkAllRead();
      }
    },
    [onMarkAllRead],
  );

  // Keep the badge visible while loading even if the count has already been
  // optimistically cleared to 0.
  if (count <= 0 && !isLoading) return null;

  return (
    <Tooltip content={tooltip}>
      <span
        role="button"
        tabIndex={0}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        aria-label={tooltip}
        className={[
          "inline-flex items-center justify-center rounded-full bg-red-500 text-10 font-medium leading-none text-white cursor-pointer select-none",
          isLoading
            ? "w-4 h-4 badge-scale"
            : isSingleDigit
              ? "w-4 h-4 hover:opacity-70 transition-opacity"
              : "h-4 min-w-[20px] px-1.5 hover:opacity-70 transition-opacity",
        ].join(" ")}
      >
        {isLoading ? (
          <span className="badge-spinner" />
        ) : (
          formatUnreadCount(count)
        )}
      </span>
    </Tooltip>
  );
}
