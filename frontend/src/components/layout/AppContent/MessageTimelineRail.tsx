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

      {/* Arrow pointing right toward the rail */}
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
  const [touchTurnIndex, setTouchTurnIndex] = useState<number | null>(null);
  // 导航锚定的激活轮：跳转落点顶部留白会露出上一轮消息的尾巴，纯按
  // 可视区起点解析会把激活算到上一轮；锚定到被点击的轮，直到视口
  // 真正滚出该轮区间。
  const [pinnedActiveTurnIndex, setPinnedActiveTurnIndex] = useState<
    number | null
  >(null);
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
  // 最近一次真实指针类型：触摸后拦截合成 mouseenter，鼠标 pointermove
  // 到来后恢复悬停。
  const lastPointerTypeRef = useRef<"mouse" | "touch" | null>(null);

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
      // 触摸反馈是波动，不是悬停卡片：立刻清掉可能残留的鼠标悬停卡，
      // 并拦截触摸后浏览器补发的合成 mouseenter（会以过期锚点重开卡片，
      // 表现为卡片弹在上一条旁边）。真实鼠标 pointermove 才恢复悬停。
      lastPointerTypeRef.current = "touch";
      hoveredBarRef.current = null;
      setHoveredTurnIndex(null);
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

  // Clicks landing on the button itself (the 8px gap rows between 3px bars,
  // or a bar that shifted mid-click) still navigate to the nearest turn —
  // the whole rail is an effective click target. Hover resolution shares
  // the same nearest-center logic so the two can never disagree.
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

  const handleTouchMove = useCallback(
    (event: PointerEvent<HTMLButtonElement>) => {
      if (!draggingRef.current) {
        // 鼠标悬停按指针实际位置就近解析：行高只有 3px、间隔是死区，
        // 且轨道滚动/条宽变化后浏览器不会补发 mouseenter，仅靠进入
        // 事件会让亮条/预览卡停在过期的那一行（表现为亮的是上一条）。
        if (event.pointerType === "mouse") {
          lastPointerTypeRef.current = "mouse";
          const hoverIndex = findNearestTurnByViewportY(event.clientY);
          if (hoverIndex !== null && hoverIndex !== hoveredTurnIndex) {
            hoveredBarRef.current = barRefs.current[hoverIndex] ?? null;
            setHoveredTurnIndex(hoverIndex);
          }
        }
        return;
      }
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

      // The touch wave follows the finger while scrolling.
      const index = findTurnAtY(event.clientY, railScrolls ? dy : 0);
      if (index !== touchTurnRef.current) {
        touchTurnRef.current = index;
        setTouchTurnIndex(index);
      }
    },
    [findNearestTurnByViewportY, findTurnAtY, hoveredTurnIndex],
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

  // 所有导航路径（刻度点击 / 按钮兜底 / 触摸轻点）统一走这里：置位激活
  // 锚定，让被点击的轮立即点亮并保持到视口滚出它。
  const navigateToTurn = useCallback(
    (index: number) => {
      const turn = turns[index];
      if (!turn) return;
      setPinnedActiveTurnIndex(index);
      onNavigate(turn.user.anchorId, turn.user.messageIndex);
    },
    [onNavigate, turns],
  );

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
            navigateToTurn(tappedIndex);
          }
          return;
        }

        // Fling in the direction of the last drag delta.
        startFling(-lastDragDeltaRef.current);
      }
    },
    [navigateToTurn, startFling, turns],
  );

  const handleRailClick = useCallback(
    (event: MouseEvent<HTMLButtonElement>) => {
      if (suppressNextClickRef.current) {
        suppressNextClickRef.current = false;
        return;
      }
      const index = findNearestTurnByViewportY(event.clientY);
      if (index !== null && turns[index]) {
        navigateToTurn(index);
      }
    },
    [findNearestTurnByViewportY, navigateToTurn, turns],
  );

  // Keep the active turn's bar visible inside the scrollable rail.
  // 锚定优先：视口起点仍落在被导航轮（或其上一条消息的尾巴）时，
  // 激活保持在被导航的轮；起点滚出该轮消息区间后交还范围解析。
  const computedActiveTurnIndex =
    visibleRange === null
      ? null
      : turns.findIndex((turn) => isTurnInRange(turn, visibleRange));
  const pinnedTurn =
    pinnedActiveTurnIndex !== null && turns[pinnedActiveTurnIndex] !== undefined
      ? turns[pinnedActiveTurnIndex]
      : null;
  const pinnedStillRelevant =
    pinnedTurn !== null &&
    visibleRange !== null &&
    visibleRange.startIndex >= pinnedTurn.user.messageIndex - 1 &&
    visibleRange.startIndex <=
      (pinnedTurn.responses.length > 0
        ? pinnedTurn.responses[pinnedTurn.responses.length - 1]!.messageIndex
        : pinnedTurn.user.messageIndex);
  const activeTurnIndex =
    pinnedStillRelevant && pinnedActiveTurnIndex !== null
      ? pinnedActiveTurnIndex
      : computedActiveTurnIndex;

  useEffect(() => {
    if (activeTurnIndex === null || activeTurnIndex === -1) return;
    barRefs.current[activeTurnIndex]?.scrollIntoView?.({ block: "nearest" });
  }, [activeTurnIndex]);

  if (turns.length <= 2) return null;

  return (
    <div
      ref={railScrollRef}
      className="hidden lg:block absolute right-0 top-1/2 -translate-y-1/2 z-20 max-h-full overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <button
        type="button"
        className="group/timeline pointer-events-auto flex flex-col items-end px-4 py-3 pr-1 transition-all duration-150"
        aria-label={t("chat.timeline", "Timeline")}
        style={{ gap: 8, touchAction: "none" }}
        onMouseLeave={handleRailMouseLeave}
        onClick={handleRailClick}
        onPointerDown={handleTouchStart}
        onPointerMove={handleTouchMove}
        onPointerUp={handleTouchEnd}
        onPointerCancel={(e) => handleTouchEnd(e, true)}
      >
        {turns.map((turn, index) => {
          // Exactly one bar is active: the topmost turn in the visible
          // range — matching the single-highlight reference design.
          const isActive = index === activeTurnIndex;

          const isHovered =
            hoveredTurnIndex === index || touchTurnIndex === index;
          // Touch wave: the touched bar grows to 3× base width and
          // thickens via scaleY (3px → 5px without layout shift, so the
          // cached drag centers stay valid); neighbors get a gentle bump.
          const touchDistance =
            touchTurnIndex === null ? null : Math.abs(index - touchTurnIndex);
          const barWidth =
            touchDistance === null
              ? isHovered
                ? 24
                : 16
              : touchDistance === 0
                ? 48
                : touchDistance === 1
                  ? 34
                  : touchDistance === 2
                    ? 26
                    : touchDistance === 3
                      ? 20
                      : 16;
          const barTransform = touchDistance === 0 ? "scaleY(1.67)" : undefined;

          return (
            <span
              key={turn.user.id}
              ref={(element) => {
                barRefs.current[index] = element;
              }}
              data-turn-index={index}
              className="flex w-11 cursor-pointer items-center justify-end"
              onClick={(e) => {
                e.stopPropagation();
                navigateToTurn(index);
              }}
              onMouseEnter={(e) => {
                // 触摸后浏览器补发的合成 mouseenter：锚点是过期位置，
                // 直接忽略。
                if (lastPointerTypeRef.current === "touch") return;
                hoveredBarRef.current = e.currentTarget;
                setHoveredTurnIndex(index);
              }}
            >
              <span
                className={clsx(
                  "h-[3px] rounded-full transition-[width,background-color,transform] duration-200 ease-out",
                  isActive
                    ? "bg-[var(--theme-primary)]"
                    : isHovered
                      ? "bg-[color-mix(in_srgb,var(--theme-primary)_40%,transparent)]"
                      : "bg-[color-mix(in_srgb,var(--theme-text-secondary)_22%,transparent)] group-hover/timeline:bg-[color-mix(in_srgb,var(--theme-primary)_32%,transparent)]",
                )}
                style={{
                  width: `${barWidth}px`,
                  transform: barTransform,
                }}
              />
            </span>
          );
        })}
      </button>

      {/* Hover preview card — keyed by turn so it re-anchors to the bar
          the mouse is currently on (the position hook only recomputes on
          open, not when the anchor element changes). */}
      {hoveredTurnIndex !== null && turns[hoveredTurnIndex] && (
        <TimelinePreviewCard
          key={hoveredTurnIndex}
          turn={turns[hoveredTurnIndex]}
          anchorRef={hoveredBarRef}
          visible={hoveredTurnIndex !== null}
        />
      )}
    </div>
  );
}
