import {
  useState,
  useMemo,
  useEffect,
  useRef,
  useCallback,
  type RefObject,
  type PointerEvent,
  type MouseEvent,
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
// eslint-disable-next-line react-refresh/only-export-components
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

/** Whether any message of the turn falls inside the visible list range. */
function isTurnInRange(turn: Turn, range: ListRange): boolean {
  if (
    turn.user.messageIndex >= range.startIndex &&
    turn.user.messageIndex <= range.endIndex
  ) {
    return true;
  }
  return turn.responses.some(
    (r) =>
      r.messageIndex >= range.startIndex && r.messageIndex <= range.endIndex,
  );
}

/* ------------------------------------------------------------------ */
/*  TimelinePreviewCard — hover popup showing turn content            */
/* ------------------------------------------------------------------ */

const CARD_WIDTH = 260;

/** Pointer travel (px) below which a touch gesture counts as a tap. */
const TAP_SLOP_PX = 8;
/** Fling velocity clamp (px/frame) applied on release. */
const FLING_MAX_VELOCITY = 60;
const FLING_DECAY = 0.95;
const FLING_STOP_VELOCITY = 0.5;

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
      left: rect.right + 8,
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

      {/* Arrow pointing left toward the rail */}
      <div
        className="absolute top-1/2 -translate-y-1/2 h-[7px] w-[7px] rotate-45 border-[var(--theme-border)] bg-[var(--theme-bg-card)]"
        style={{
          left: "-4px",
          borderTop: "none",
          borderRight: "none",
        }}
      />
    </div>,
    document.body,
  );
}

/* ------------------------------------------------------------------ */
/*  MessageTimelineRail — vertical bar strip on left edge              */
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
  const [touchTurnIndex, setTouchTurnIndex] = useState<number | null>(null);
  const hoveredBarRef = useRef<HTMLSpanElement | null>(null);
  const barRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const railScrollRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);
  const touchTurnRef = useRef<number | null>(null);
  // Bar viewport centers captured once per drag; moves resolve the nearest
  // bar arithmetically to avoid layout thrashing (rect reads after scrollTop
  // writes force synchronous layout on every pointermove).
  const dragCentersRef = useRef<number[]>([]);
  const touchScrollStartRef = useRef<{
    y: number;
    scrollTop: number;
    prevY: number;
    moved: boolean;
  } | null>(null);
  const lastDragDeltaRef = useRef(0);
  const flingFrameRef = useRef<number | null>(null);
  // 触摸手势结束时指针捕获会把合成 click 重定向到 button；由手势路径
  // 导航后置位，让 button 的 click 兜底跳过这一次，避免双跳。
  const suppressNextClickRef = useRef(false);

  const stopFling = useCallback(() => {
    if (flingFrameRef.current !== null) {
      cancelAnimationFrame(flingFrameRef.current);
      flingFrameRef.current = null;
    }
  }, []);

  // Inertia: keep gliding after the finger lifts, with exponential decay.
  const startFling = useCallback(
    (velocity: number) => {
      stopFling();
      let v = Math.max(
        -FLING_MAX_VELOCITY,
        Math.min(FLING_MAX_VELOCITY, velocity),
      );
      if (Math.abs(v) < FLING_STOP_VELOCITY) return;
      const step = () => {
        flingFrameRef.current = null;
        const rail = railScrollRef.current;
        if (!rail || Math.abs(v) < FLING_STOP_VELOCITY) return;
        const before = rail.scrollTop;
        rail.scrollTop = before + v;
        if (rail.scrollTop === before) return; // reached an edge
        v *= FLING_DECAY;
        flingFrameRef.current = requestAnimationFrame(step);
      };
      flingFrameRef.current = requestAnimationFrame(step);
    },
    [stopFling],
  );

  useEffect(() => stopFling, [stopFling]);

  const handleRailMouseLeave = useCallback(() => {
    setHoveredTurnIndex(null);
    hoveredBarRef.current = null;
  }, []);

  const captureDragCenters = useCallback(() => {
    dragCentersRef.current = barRefs.current.map((bar) => {
      const rect = bar?.getBoundingClientRect();
      return rect ? rect.top + rect.height / 2 : Number.NaN;
    });
  }, []);

  /** Nearest turn to a viewport Y, from cached centers. `scrollShift` is the
   * distance the rail has scrolled since the drag started (bars move up). */
  const findTurnAtY = useCallback((clientY: number, scrollShift = 0) => {
    let nearestIndex: number | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;
    dragCentersRef.current.forEach((center, index) => {
      if (Number.isNaN(center)) return;
      const distance = Math.abs(clientY - (center - scrollShift));
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    return nearestIndex;
  }, []);

  const handleTouchStart = useCallback(
    (event: PointerEvent<HTMLButtonElement>) => {
      suppressNextClickRef.current = false;
      // 任何指针按下都停住滑行（含鼠标：否则滑行中点击，目标会在
      // mousedown 与 mouseup 之间挪位，click 落空）。
      stopFling();
      if (event.pointerType !== "touch" && event.pointerType !== "pen") return;
      draggingRef.current = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      captureDragCenters();

      // Vertical drags scroll the rail when it overflows (touch-action: none
      // blocks native scrolling); below the tap slop the gesture is a tap and
      // navigates. Swipes never navigate.
      const rail = railScrollRef.current;
      touchScrollStartRef.current = {
        y: event.clientY,
        scrollTop: rail?.scrollTop ?? 0,
        prevY: event.clientY,
        moved: false,
      };

      const index = findTurnAtY(event.clientY);
      touchTurnRef.current = index;
      setTouchTurnIndex(index);
    },
    [captureDragCenters, findTurnAtY, stopFling],
  );

  const handleTouchMove = useCallback(
    (event: PointerEvent<HTMLButtonElement>) => {
      if (!draggingRef.current) return;
      event.preventDefault();

      const scrollStart = touchScrollStartRef.current;
      if (!scrollStart) return;

      const dy = scrollStart.y - event.clientY;
      const rail = railScrollRef.current;
      const railScrolls =
        rail !== null && rail.scrollHeight > rail.clientHeight + 1;
      if (rail !== null && railScrolls) {
        rail.scrollTop = scrollStart.scrollTop + dy;
      }
      if (Math.abs(dy) > TAP_SLOP_PX) {
        scrollStart.moved = true;
        lastDragDeltaRef.current = event.clientY - scrollStart.prevY;
      }
      scrollStart.prevY = event.clientY;

      // The doubled-width highlight follows the finger while scrolling.
      const index = findTurnAtY(event.clientY, railScrolls ? dy : 0);
      if (index !== touchTurnRef.current) {
        touchTurnRef.current = index;
        setTouchTurnIndex(index);
      }
    },
    [findTurnAtY],
  );

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

  const handleTouchEnd = useCallback(
    (event: PointerEvent<HTMLButtonElement>, isCancel = false) => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      // 指针捕获会把随后的合成 click 重定向到 button；手势路径已处理
      // 本次交互，置位让 button 的 click 兜底跳过它。
      suppressNextClickRef.current = true;

      const scrollStart = touchScrollStartRef.current;
      if (scrollStart) {
        touchScrollStartRef.current = null;
        const tappedIndex = touchTurnRef.current;
        touchTurnRef.current = null;
        setTouchTurnIndex(null);

        if (!scrollStart.moved) {
          // A tap (below slop travel) navigates — the pointer capture makes
          // the span's onClick unreachable on touch.
          if (
            !isCancel &&
            tappedIndex !== null &&
            turns[tappedIndex] !== undefined
          ) {
            onNavigate(
              turns[tappedIndex].user.anchorId,
              turns[tappedIndex].user.messageIndex,
            );
          }
          return;
        }

        // Fling in the direction of the last drag delta.
        startFling(-lastDragDeltaRef.current);
      }
    },
    [onNavigate, startFling, turns],
  );

  // Clicks landing on the button itself (the 8px gap rows between 3px bars,
  // or a bar that shifted mid-click) still navigate to the nearest turn —
  // the whole rail is an effective click target.
  const findNearestTurnByViewportY = useCallback((clientY: number) => {
    let nearestIndex: number | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;
    barRefs.current.forEach((bar, index) => {
      if (!bar) return;
      const rect = bar.getBoundingClientRect();
      const distance = Math.abs(clientY - (rect.top + rect.height / 2));
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    return nearestIndex;
  }, []);

  const handleRailClick = useCallback(
    (event: MouseEvent<HTMLButtonElement>) => {
      if (suppressNextClickRef.current) {
        suppressNextClickRef.current = false;
        return;
      }
      const index = findNearestTurnByViewportY(event.clientY);
      if (index !== null && turns[index]) {
        onNavigate(turns[index].user.anchorId, turns[index].user.messageIndex);
      }
    },
    [findNearestTurnByViewportY, onNavigate, turns],
  );

  // Keep the active turn's bar visible inside the scrollable rail.
  const activeTurnIndex =
    visibleRange === null
      ? null
      : turns.findIndex((turn) => isTurnInRange(turn, visibleRange));

  useEffect(() => {
    if (activeTurnIndex === null || activeTurnIndex === -1) return;
    barRefs.current[activeTurnIndex]?.scrollIntoView?.({ block: "nearest" });
  }, [activeTurnIndex]);

  if (turns.length <= 2) return null;

  const count = turns.length;

  return (
    <div
      ref={railScrollRef}
      className="hidden lg:block absolute left-2 top-1/2 -translate-y-1/2 z-20 max-h-full overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <button
        type="button"
        className="group/timeline pointer-events-auto flex flex-col items-start px-4 py-3 pl-1 transition-all duration-150"
        aria-label={t("chat.timeline", "Timeline")}
        title={`${t("chat.timeline", "Timeline")} · ${count}`}
        style={{ gap: 8, touchAction: "none" }}
        onMouseLeave={handleRailMouseLeave}
        onClick={handleRailClick}
        onPointerDown={handleTouchStart}
        onPointerMove={handleTouchMove}
        onPointerUp={handleTouchEnd}
        onPointerCancel={(e) => handleTouchEnd(e, true)}
      >
        {turns.map((turn, index) => {
          const isActive =
            visibleRange !== null && isTurnInRange(turn, visibleRange);

          const isHovered =
            hoveredTurnIndex === index || touchTurnIndex === index;
          // Touched bar doubles in width (following the finger); neighbors
          // stay at base width — no wave taper.
          const barWidth =
            touchTurnIndex === null
              ? isHovered
                ? 24
                : 16
              : index === touchTurnIndex
                ? 32
                : 16;

          return (
            <span
              key={turn.user.id}
              ref={(element) => {
                barRefs.current[index] = element;
              }}
              data-turn-index={index}
              className="flex w-11 cursor-pointer items-center justify-start"
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
                  "h-[3px] rounded-full transition-[width,background-color] duration-200 ease-out",
                  isActive
                    ? "bg-[var(--theme-primary)]"
                    : isHovered
                      ? "bg-[color-mix(in_srgb,var(--theme-primary)_40%,transparent)]"
                      : "bg-[color-mix(in_srgb,var(--theme-text-secondary)_22%,transparent)] group-hover/timeline:bg-[color-mix(in_srgb,var(--theme-primary)_32%,transparent)]",
                )}
                style={{
                  width: `${barWidth}px`,
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
