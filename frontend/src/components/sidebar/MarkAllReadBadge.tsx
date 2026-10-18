import { LoadingSpinner } from "../common/LoadingSpinner";
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

  const handleClick = useCallback(
    (e: MouseEvent) => {
      e.stopPropagation();
      if (!isLoading) onMarkAllRead();
    },
    [isLoading, onMarkAllRead],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.stopPropagation();
        e.preventDefault();
        if (!isLoading) onMarkAllRead();
      }
    },
    [isLoading, onMarkAllRead],
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
        aria-disabled={isLoading || undefined}
        aria-busy={isLoading || undefined}
        className="group/mark-read inline-flex size-8 shrink-0 items-center justify-center rounded-md cursor-pointer select-none aria-disabled:cursor-wait focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
      >
        <span
          aria-hidden="true"
          className={[
            "count-badge pointer-events-none",
            isLoading
              ? "count-badge--loading badge-scale"
              : "group-hover/mark-read:opacity-70 transition-opacity",
          ].join(" ")}
        >
          {isLoading ? (
            <LoadingSpinner size={10} color="text-current" />
          ) : (
            formatUnreadCount(count)
          )}
        </span>
      </span>
    </Tooltip>
  );
}
