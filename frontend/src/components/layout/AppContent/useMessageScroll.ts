import { useRef, useEffect, useState, useCallback } from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import {
  hasNewOutgoingMessage,
  shouldAutoScrollForMessageUpdate,
  shouldAutoScrollAfterViewportChange,
  startVirtuosoScrollToBottom,
} from "./messageScrollUtils";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  showScrollTop: boolean;
  handleVirtuosoAtBottomChange: (atBottom: boolean) => void;
  scrollToBottom: () => void;
  scrollToTop: () => void;
}

export function useMessageScroll(
  messages: { id: string }[],
  sessionId?: string | null,
): UseMessageScrollReturn {
  const MOBILE_BOTTOM_BREATHING_ROOM_PX = 96;
  const DESKTOP_BOTTOM_BREATHING_ROOM_PX = 16;
  const isMobileViewport =
    typeof window !== "undefined" ? window.innerWidth < 640 : false;
  const bottomBreathingRoomPx = isMobileViewport
    ? MOBILE_BOTTOM_BREATHING_ROOM_PX
    : DESKTOP_BOTTOM_BREATHING_ROOM_PX;
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const virtuosoScrollerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const rafRef = useRef<number>(0);
  const viewportResizeRafRef = useRef<number>(0);
  const scrollCleanupRef = useRef<(() => void) | null>(null);
  const previousMessagesRef = useRef(messages);
  const isNearBottomRef = useRef(true);

  const userScrolledUpRef = useRef(false);
  const autoScrollActiveRef = useRef(false);
  const ignoreProgrammaticScrollUntilRef = useRef(0);

  const handleVirtuosoAtBottomChange = useCallback((atBottom: boolean) => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setIsNearBottom(atBottom);
      isNearBottomRef.current = atBottom;
      if (atBottom) {
        setShowScrollTop(false);
        userScrolledUpRef.current = false;
        autoScrollActiveRef.current = false;
      }
    });
  }, []);

  // Scroll the Footer sentinel into view — it's always in the DOM (not virtualized)
  const scrollToBottom = useCallback(() => {
    userScrolledUpRef.current = false;
    autoScrollActiveRef.current = true;
    scrollCleanupRef.current?.();
    scrollCleanupRef.current = startVirtuosoScrollToBottom({
      virtuoso: virtuosoRef.current,
      scroller: virtuosoScrollerRef.current,
      footer: messagesEndRef.current,
      observeLayoutChanges: true,
      resizeObserverTarget:
        virtuosoScrollerRef.current?.firstElementChild ??
        virtuosoScrollerRef.current,
      maxDurationMs: isMobileViewport ? 6500 : 3000,
      settleWindowMs: isMobileViewport ? 650 : 180,
      shouldAbort: () => userScrolledUpRef.current,
      onAutoScroll: () => {
        ignoreProgrammaticScrollUntilRef.current = Date.now() + 80;
      },
      onComplete: () => {
        autoScrollActiveRef.current = false;
      },
    });
  }, [isMobileViewport]);

  const scrollToTop = useCallback(() => {
    userScrolledUpRef.current = true;
    autoScrollActiveRef.current = false;
    virtuosoRef.current?.scrollTo({
      top: 0,
      behavior: "auto",
    });
    setShowScrollTop(false);
  }, []);

  // Attach scroll listener when Virtuoso Scroller mounts
  useEffect(() => {
    const scroller = virtuosoScrollerRef.current;
    if (!scroller) return;

    const lastScrollTop = { value: 0 };
    const lastScrollTime = { value: 0 };
    let timer: ReturnType<typeof setTimeout> | null = null;

    const handleScroll = () => {
      const now = Date.now();
      const scrollTop = scroller.scrollTop;
      const dt = now - lastScrollTime.value;
      const dScroll = lastScrollTop.value - scrollTop;
      const programmaticScroll =
        now <= ignoreProgrammaticScrollUntilRef.current;
      const movedUp = scrollTop < lastScrollTop.value - 2;
      const isAwayFromBottom =
        scrollTop + scroller.clientHeight <
        scroller.scrollHeight - Math.max(50, bottomBreathingRoomPx);

      if (
        autoScrollActiveRef.current &&
        !programmaticScroll &&
        movedUp &&
        isAwayFromBottom
      ) {
        userScrolledUpRef.current = true;
        autoScrollActiveRef.current = false;
      }

      if (dt < 300 && dScroll > 30 && scrollTop > 200) {
        setShowScrollTop(true);
        userScrolledUpRef.current = true;
        autoScrollActiveRef.current = false;
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => setShowScrollTop(false), 3000);
      } else if (scrollTop < 200) {
        setShowScrollTop(false);
      }

      lastScrollTop.value = scrollTop;
      lastScrollTime.value = now;
    };

    scroller.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scroller.removeEventListener("scroll", handleScroll);
      if (timer) clearTimeout(timer);
    };
  }, [bottomBreathingRoomPx, messages.length]);

  useEffect(() => {
    if (!isMobileViewport || typeof window === "undefined") {
      return;
    }

    const viewport = window.visualViewport;
    if (!viewport) {
      return;
    }

    let previousHeight = viewport.height;
    const handleViewportChange = () => {
      const heightChanged = Math.abs(viewport.height - previousHeight) > 4;

      previousHeight = viewport.height;

      if (!heightChanged) {
        return;
      }

      if (
        !shouldAutoScrollAfterViewportChange({
          scroller: virtuosoScrollerRef.current,
          bottomBreathingRoomPx,
          userScrolledUp: userScrolledUpRef.current,
          autoScrollActive: autoScrollActiveRef.current,
          isNearBottom: isNearBottomRef.current,
        })
      ) {
        return;
      }

      cancelAnimationFrame(viewportResizeRafRef.current);
      viewportResizeRafRef.current = requestAnimationFrame(() => {
        scrollToBottom();
      });
    };

    viewport.addEventListener("resize", handleViewportChange);

    return () => {
      viewport.removeEventListener("resize", handleViewportChange);
      cancelAnimationFrame(viewportResizeRafRef.current);
    };
  }, [bottomBreathingRoomPx, isMobileViewport, scrollToBottom]);

  // Scroll to bottom on session change or initial load (after messages load)
  // Only trigger for session switches and page refresh (not new session creation — sendMessage handles its own scrolling)
  const pendingScrollRef = useRef(false);
  const prevSessionIdRef = useRef<string | null | undefined>(undefined);
  const initializedRef = useRef(false);
  useEffect(() => {
    if (sessionId && (prevSessionIdRef.current || !initializedRef.current)) {
      pendingScrollRef.current = true;
      initializedRef.current = true;
    }
    prevSessionIdRef.current = sessionId;
  }, [sessionId]);

  // Scroll to bottom on session change or initial load (after messages load)
  // When Virtuoso mounts for the first time (switching from WelcomePage), refs
  // may not be available yet. We poll until the scroller appears.
  useEffect(() => {
    if (messages.length > 0 && pendingScrollRef.current) {
      let raf1 = 0;
      let raf2 = 0;
      let settled = false;

      const tryScroll = () => {
        if (settled) return;
        // Virtuoso may not have mounted yet (refs still null) — retry
        if (!virtuosoRef.current || !virtuosoScrollerRef.current) {
          raf1 = requestAnimationFrame(() => {
            raf2 = requestAnimationFrame(tryScroll);
          });
          return;
        }
        settled = true;
        pendingScrollRef.current = false;
        scrollToBottom();
      };

      // Wait two frames for React to commit the Virtuoso mount
      raf1 = requestAnimationFrame(() => {
        raf2 = requestAnimationFrame(tryScroll);
      });
      return () => {
        settled = true;
        cancelAnimationFrame(raf1);
        cancelAnimationFrame(raf2);
        // Do not abort scrollCleanupRef here. History can arrive in chunks,
        // and each messages update reruns this effect; aborting the active
        // bottom-lock loop is what leaves mobile users stranded mid-list.
      };
    }
  }, [messages, scrollToBottom]);

  useEffect(() => {
    const previousMessages = previousMessagesRef.current;
    if (hasNewOutgoingMessage(previousMessages, messages)) {
      scrollToBottom();
    } else if (
      shouldAutoScrollForMessageUpdate({
        previousMessages,
        nextMessages: messages,
        userScrolledUp: userScrolledUpRef.current,
        autoScrollActive: autoScrollActiveRef.current,
        isNearBottom: isNearBottomRef.current,
      })
    ) {
      scrollToBottom();
    }
    previousMessagesRef.current = messages;
  }, [messages, scrollToBottom]);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
      cancelAnimationFrame(viewportResizeRafRef.current);
      scrollCleanupRef.current?.();
    };
  }, []);

  return {
    messagesContainerRef,
    virtuosoRef,
    virtuosoScrollerRef,
    messagesEndRef,
    isNearBottom,
    showScrollTop,
    handleVirtuosoAtBottomChange,
    scrollToBottom,
    scrollToTop,
  };
}
