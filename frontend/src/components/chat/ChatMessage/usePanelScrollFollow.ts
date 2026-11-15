import {
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { RightPanelActiveContext } from "../../common/useRightPanelEntry";
import {
  createWheelIntentAccumulator,
  nextWheelIntentState,
} from "../../layout/AppContent/messageScrollUtils";
import {
  createMessageScrollFollowState,
  getNextMessageScrollFollowStateForUserScroll,
} from "../../layout/AppContent/useMessageScroll.followState";
import { getMessageScrollViewportState } from "../../layout/AppContent/useMessageScroll.viewport";

// Both sidebar reading surfaces share the main conversation's user-scroll policy.
export function usePanelScrollFollow(
  content: unknown,
  initiallyFollowing = true,
) {
  const active = useContext(RightPanelActiveContext);
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const following = useRef(initiallyFollowing);
  const lastTop = useRef(0);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const follow = useCallback(() => {
    if (!active || !scroller || !following.current) return;
    scroller.scrollTop = scroller.scrollHeight;
    lastTop.current = scroller.scrollTop;
  }, [active, scroller]);
  const jumpToBottom = useCallback(() => {
    following.current = true;
    setShowScrollToBottom(false);
    follow();
  }, [follow]);

  useLayoutEffect(() => {
    follow();
  }, [content, follow]);

  useEffect(() => {
    if (!scroller) return;
    // Panel history restores scroll offsets during its first 600ms.
    const timer = window.setTimeout(() => {
      if (
        scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight >
        1
      ) {
        following.current = false;
        setShowScrollToBottom(true);
      }
    }, 650);
    return () => window.clearTimeout(timer);
  }, [scroller]);
  useEffect(() => {
    if (!active || !scroller) return;
    lastTop.current = scroller.scrollTop;
    let wheel = createWheelIntentAccumulator();
    let touchY: number | null = null;
    const detach = () => {
      following.current = false;
      setShowScrollToBottom(true);
    };
    const onScroll = () => {
      const delta = lastTop.current - scroller.scrollTop;
      const { isMobileViewport, awayFromBottomThresholdPx } =
        getMessageScrollViewportState();
      const state = getNextMessageScrollFollowStateForUserScroll({
        state: createMessageScrollFollowState({
          userScrolledUp: !following.current,
          autoScrollActive: following.current,
        }),
        isMobileViewport,
        streamingAssistantActive: true,
        programmaticScroll: false,
        movedUp: delta > 8,
        isAwayFromBottom:
          scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight >
          awayFromBottomThresholdPx,
        deltaScrollPx: Math.max(0, delta),
        scrollTop: scroller.scrollTop,
        reachedBottom:
          delta < 0 &&
          scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight <=
            1,
      });
      following.current = !state.userScrolledUp;
      setShowScrollToBottom(state.userScrolledUp);
      lastTop.current = scroller.scrollTop;
    };
    const onWheel = (event: WheelEvent) => {
      const intent = nextWheelIntentState(wheel, event.deltaY, Date.now());
      wheel = intent.state;
      if (intent.detach) detach();
    };
    const onTouchStart = (event: TouchEvent) => {
      touchY = event.touches[0]?.clientY ?? null;
    };
    const onTouchMove = (event: TouchEvent) => {
      const y = event.touches[0]?.clientY;
      if (touchY !== null && y !== undefined && y - touchY > 6) {
        detach();
        touchY = y;
      }
    };
    const onTouchEnd = () => {
      touchY = null;
    };
    scroller.addEventListener("scroll", onScroll, { passive: true });
    scroller.addEventListener("wheel", onWheel, { passive: true });
    scroller.addEventListener("touchstart", onTouchStart, { passive: true });
    scroller.addEventListener("touchmove", onTouchMove, { passive: true });
    scroller.addEventListener("touchend", onTouchEnd, { passive: true });
    scroller.addEventListener("touchcancel", onTouchEnd, { passive: true });
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(follow);
    observer?.observe(scroller);
    if (contentRef.current) observer?.observe(contentRef.current);
    return () => {
      observer?.disconnect();
      scroller.removeEventListener("scroll", onScroll);
      scroller.removeEventListener("wheel", onWheel);
      scroller.removeEventListener("touchstart", onTouchStart);
      scroller.removeEventListener("touchmove", onTouchMove);
      scroller.removeEventListener("touchend", onTouchEnd);
      scroller.removeEventListener("touchcancel", onTouchEnd);
    };
  }, [active, scroller, follow]);

  return {
    scrollRef: setScroller,
    contentRef,
    showScrollToBottom,
    jumpToBottom,
  };
}
