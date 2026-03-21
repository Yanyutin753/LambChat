import { useRef, useEffect, useCallback, useState } from "react";
import type { VirtuosoHandle } from "react-virtuoso";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  showScrollTop: boolean;
  setShowScrollTop: (value: boolean) => void;
  handleVirtuosoAtBottomChange: (atBottom: boolean) => void;
}

export function useMessageScroll(
  messages: { id: string }[],
): UseMessageScrollReturn {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const virtuosoScrollerRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const scrollTopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number>(0);
  const lastScrollTopRef = useRef(0);
  const lastScrollTimeRef = useRef(0);

  // Track previous message count to detect new messages
  const prevMessagesCountRef = useRef(messages.length);

  // Called by Virtuoso's atBottomStateChange
  // Uses rAF to batch state updates and avoid triggering re-renders during scroll
  const handleVirtuosoAtBottomChange = useCallback((atBottom: boolean) => {
    // Use rAF to debounce - atBottomStateChange fires rapidly during scroll
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setIsNearBottom(atBottom);
      if (atBottom) setShowScrollTop(false);
    });
  }, []);

  // Attach native scroll listener to Virtuoso's internal scroller element
  // (Virtuoso's onScroll prop binds to the wrapper div, not the scroll container)
  useEffect(() => {
    const scroller = virtuosoScrollerRef.current;
    if (!scroller) return;

    const handleScroll = () => {
      const now = Date.now();
      const scrollTop = scroller.scrollTop;
      const dt = now - lastScrollTimeRef.current;
      const dScroll = lastScrollTopRef.current - scrollTop; // positive = scrolling up

      // Fast scroll-up → show scroll-to-top
      if (dt < 200 && dScroll > 80 && scrollTop > 300) {
        setShowScrollTop(true);
        if (scrollTopTimerRef.current) clearTimeout(scrollTopTimerRef.current);
        scrollTopTimerRef.current = setTimeout(
          () => setShowScrollTop(false),
          3000,
        );
      } else if (scrollTop < 300) {
        setShowScrollTop(false);
      }

      lastScrollTopRef.current = scrollTop;
      lastScrollTimeRef.current = now;
    };

    scroller.addEventListener("scroll", handleScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", handleScroll);
  }, []);

  // Auto-scroll to bottom when new messages are added
  useEffect(() => {
    const prevCount = prevMessagesCountRef.current;
    const newCount = messages.length;

    // Only scroll when message count increases - don't re-scroll on isNearBottom changes
    if (newCount > prevCount) {
      virtuosoRef.current?.scrollToIndex({
        index: messages.length - 1,
        behavior: "auto",
        align: "end",
      });
    }

    prevMessagesCountRef.current = newCount;
  }, [messages]);

  return {
    messagesContainerRef,
    messagesEndRef,
    virtuosoRef,
    virtuosoScrollerRef,
    isNearBottom,
    showScrollTop,
    setShowScrollTop,
    handleVirtuosoAtBottomChange,
  };
}
