import {
  useState,
  useMemo,
  useEffect,
  useRef,
  useCallback,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { cjkGfmRemarkPlugins } from "../../common/markdownRemarkPlugins";
import type { ListRange } from "react-virtuoso";
import type { CSSProperties } from "react";
import type { MessageOutlineItem } from "./messageOutline";
import { createSingletonStore } from "../../chat/ChatMessage/items/createSingletonStore";
import { useStickyDropdownPosition } from "../../../hooks/useStickyDropdownPosition";

/* ------------------------------------------------------------------ */
/*  Singleton store for visible range (avoids useState in ChatView)  */
/* ------------------------------------------------------------------ */

const timelineRangeStore = createSingletonStore<ListRange | null>(null);

/** Call from ChatView's rangeChanged handler — no React state needed. */
export function updateTimelineRange(range: ListRange | null): void {
  timelineRangeStore.set(range);
}

/** Hook for the rail component to subscribe to range changes. */
function useTimelineRange(): ListRange | null {
  const [range, setRange] = useState<ListRange | null>(() =>
    timelineRangeStore.get(),
  );
  useEffect(() => {
    return timelineRangeStore.subscribe(() =>
      setRange(timelineRangeStore.get()),
    );
  }, []);
  return range;
}

/* ------------------------------------------------------------------ */
/*  Turn grouping — pairs consecutive user + assistant messages       */
/* ------------------------------------------------------------------ */

interface Turn {
  user: MessageOutlineItem;
  responses: MessageOutlineItem[];
}

function groupIntoTurns(items: MessageOutlineItem[]): Turn[] {
  const turns: Turn[] = [];
  let current: Turn | null = null;

  for (const item of items) {
    if (item.kind === "user-message") {
      if (current) turns.push(current);
      current = { user: item, responses: [] };
    } else if (item.kind === "assistant-message" && current) {
      current.responses.push(item);
    }
  }
  if (current) turns.push(current);
  return turns;
}

/* ------------------------------------------------------------------ */
/*  TimelinePreviewCard — hover popup showing turn content            */
/* ------------------------------------------------------------------ */

const CARD_WIDTH = 260;

function TimelinePreviewCard({
  turn,
  anchorRef,
  visible,
}: {
  turn: Turn;
  anchorRef: RefObject<HTMLSpanElement | null>;
  visible: boolean;
}) {
  const cardStyle = useStickyDropdownPosition(anchorRef, visible, (rect) => {
    const estimatedHeight = 120;
    let top = rect.top + rect.height / 2 - estimatedHeight / 2;
    top = Math.max(8, Math.min(top, window.innerHeight - estimatedHeight - 8));

    return {
      position: "fixed",
      right: window.innerWidth - rect.left + 8,
      top,
      zIndex: 60,
      width: `${CARD_WIDTH}px`,
    } satisfies CSSProperties;
  });

  if (!visible) return null;

  const responseText =
    turn.responses.length > 0
      ? turn.responses.map((r) => r.label).join(" ")
      : "";

  return createPortal(
    <div
      className={clsx(
        "relative rounded-lg border p-3 shadow-lg pointer-events-none",
        "border-[var(--theme-border)]",
        "bg-[var(--theme-bg-card)]",
      )}
      style={cardStyle}
    >
      {/* User message */}
      <div className="truncate text-sm font-medium leading-snug text-[var(--theme-text)] [&_p]:inline">
        <ReactMarkdown remarkPlugins={[...cjkGfmRemarkPlugins]}>
          {turn.user.label}
        </ReactMarkdown>
      </div>

      {/* Divider */}
      {responseText && <div className="my-1.5 h-px bg-[var(--theme-border)]" />}

      {/* Assistant response */}
      {responseText && (
        <div className="line-clamp-3 text-xs leading-relaxed text-[var(--theme-text-secondary)] [&_p]:inline [&_code]:rounded [&_code]:bg-[var(--theme-bg-subtle)] [&_code]:px-0.5">
          <ReactMarkdown remarkPlugins={[...cjkGfmRemarkPlugins]}>
            {responseText}
          </ReactMarkdown>
        </div>
      )}

      {/* Arrow pointing right toward the bar */}
      <div
        className="absolute top-1/2 -translate-y-1/2 h-[7px] w-[7px] rotate-45 border-[var(--theme-border)] bg-[var(--theme-bg-card)]"
        style={{
          right: "-4px",
          borderTop: "none",
          borderLeft: "none",
        }}
      />
    </div>,
    document.body,
  );
}

/* ------------------------------------------------------------------ */
/*  MessageTimelineRail — vertical bar strip on right edge             */
/*                                                                      */
/*  One bar per turn (user + assistant pair). Hover shows a preview    */
/*  card with the turn's messages. Click navigates to the turn.        */
/* ------------------------------------------------------------------ */

export interface MessageTimelineRailProps {
  /** Outline items (already extracted from messages). */
  items: MessageOutlineItem[];
  /** Called with the anchor ID and message index when a bar is clicked. */
  onNavigate: (anchorId: string, messageIndex: number) => void;
}

export function MessageTimelineRail({
  items,
  onNavigate,
}: MessageTimelineRailProps) {
  const visibleRange = useTimelineRange();
  const { t } = useTranslation();

  const [hoveredTurnIndex, setHoveredTurnIndex] = useState<number | null>(null);
  const hoveredBarRef = useRef<HTMLSpanElement | null>(null);

  const handleRailMouseLeave = useCallback(() => {
    setHoveredTurnIndex(null);
    hoveredBarRef.current = null;
  }, []);

  // Only user-message and assistant-message items (exclude headings).
  const messageItems = useMemo(
    () =>
      items.filter(
        (i) => i.kind === "user-message" || i.kind === "assistant-message",
      ),
    [items],
  );

  // Group into turns (user + following assistant responses).
  const turns = useMemo(() => groupIntoTurns(messageItems), [messageItems]);

  if (turns.length === 0) return null;

  const count = turns.length;

  return (
    <div className="hidden lg:block absolute right-0 top-1/2 -translate-y-1/2 z-20">
      <button
        type="button"
        className="group/timeline pointer-events-auto flex flex-col items-end px-4 py-3 pr-1 transition-all duration-150"
        aria-label={t("chat.timeline", "Timeline")}
        title={`${t("chat.timeline", "Timeline")} · ${count}`}
        style={{ gap: 12 }}
        onMouseLeave={handleRailMouseLeave}
      >
        {turns.map((turn, index) => {
          const isActive =
            visibleRange !== null &&
            turn.responses.some(
              (r) =>
                r.messageIndex >= visibleRange.startIndex &&
                r.messageIndex <= visibleRange.endIndex,
            );

          // Also mark active if the user message itself is in range.
          const userActive =
            visibleRange !== null &&
            turn.user.messageIndex >= visibleRange.startIndex &&
            turn.user.messageIndex <= visibleRange.endIndex;

          const isHovered = hoveredTurnIndex === index;

          return (
            <span
              key={turn.user.id}
              className="flex w-11 cursor-pointer items-center justify-end"
              onClick={(e) => {
                e.stopPropagation();
                onNavigate(turn.user.anchorId, turn.user.messageIndex);
              }}
              onMouseEnter={(e) => {
                hoveredBarRef.current = e.currentTarget;
                setHoveredTurnIndex(index);
              }}
            >
              <span
                className={clsx(
                  "h-[3px] rounded-full transition-all duration-200 ease-out",
                  isActive || userActive
                    ? "bg-[var(--theme-primary)]"
                    : isHovered
                      ? "bg-[color-mix(in_srgb,var(--theme-primary)_40%,transparent)]"
                      : "bg-[color-mix(in_srgb,var(--theme-text-secondary)_22%,transparent)] group-hover/timeline:bg-[color-mix(in_srgb,var(--theme-primary)_32%,transparent)]",
                )}
                style={{
                  width: isHovered ? "24px" : "16px",
                }}
              />
            </span>
          );
        })}
      </button>

      {/* Hover preview card */}
      {hoveredTurnIndex !== null && turns[hoveredTurnIndex] && (
        <TimelinePreviewCard
          turn={turns[hoveredTurnIndex]}
          anchorRef={hoveredBarRef}
          visible={hoveredTurnIndex !== null}
        />
      )}
    </div>
  );
}
