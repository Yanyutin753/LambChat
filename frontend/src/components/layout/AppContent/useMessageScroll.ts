import { useRef, useEffect, useState, useCallback } from "react";
import type { VirtuosoHandle } from "react-virtuoso";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  showScrollTop: boolean;
  handleVirtuosoAtBottomChange: (atBottom: boolean) => void;
  scrollToBottom: () => void;
  scrollToTop: () => void;
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
  const rafRef = useRef<number>(0);

  // Whether the user has manually scrolled up (away from bottom)
  const userScrolledUpRef = useRef(false);

  // Track previous message count to detect new messages
  const prevMessagesCountRef = useRef(0);

  // Track if we've done initial scroll (for page refresh case)
  const initialScrollDoneRef = useRef(false);

  // Track scroll polling interval for cleanup on unmount
  const scrollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Called by Virtuoso's atBottomStateChange
  const handleVirtuosoAtBottomChange = useCallback((atBottom: boolean) => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setIsNearBottom(atBottom);
      if (atBottom) {
        setShowScrollTop(false);
        userScrolledUpRef.current = false;
      }
    });
  }, []);

  const scrollToBottom = useCallback(() => {
    userScrolledUpRef.current = false;

    // Clear any existing scroll polling interval
    if (scrollIntervalRef.current) {
      clearInterval(scrollIntervalRef.current);
      scrollIntervalRef.current = null;
    }

    const scroller = virtuosoScrollerRef.current;
    if (!scroller || !virtuosoRef.current) return;

    // Virtuoso uses virtual rendering — not all items are measured at once,
    // so a single scrollTo may not reach the true bottom.
    // Poll until scrollTop + clientHeight >= scrollHeight (within 1px).
    let attempts = 0;
    const doScroll = () => {
      virtuosoRef.current?.scrollTo({
        top: Number.MAX_SAFE_INTEGER,
        behavior: "auto",
      });
    };
    doScroll();
    scrollIntervalRef.current = setInterval(() => {
      if (
        scroller.scrollTop + scroller.clientHeight >=
        scroller.scrollHeight - 1
      ) {
        clearInterval(scrollIntervalRef.current!);
        scrollIntervalRef.current = null;
        return;
      }
      doScroll();
      if (++attempts > 20) {
        clearInterval(scrollIntervalRef.current!);
        scrollIntervalRef.current = null;
      }
    }, 30);
  }, []);

  const scrollToTop = useCallback(() => {
    userScrolledUpRef.current = true;
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
      const dScroll = lastScrollTop.value - scrollTop; // positive = scrolling up

      if (dt < 300 && dScroll > 30 && scrollTop > 200) {
        setShowScrollTop(true);
        userScrolledUpRef.current = true;
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
      if (scrollIntervalRef.current) clearInterval(scrollIntervalRef.current);
    };
  }, [messages.length]);

  // Auto-scroll to bottom when new messages arrive AND user hasn't scrolled up
  useEffect(() => {
    const prevCount = prevMessagesCountRef.current;
    const newCount = messages.length;

    if (newCount > prevCount && !userScrolledUpRef.current) {
      // New message added - use scrollToBottom for reliable scrolling
      scrollToBottom();
    } else if (newCount > 0 && !initialScrollDoneRef.current) {
      // Initial load or page refresh - scroll to bottom
      scrollToBottom();
      initialScrollDoneRef.current = true;
    }

    prevMessagesCountRef.current = newCount;
  }, [messages, scrollToBottom]);

  return {
    messagesContainerRef,
    messagesEndRef,
    virtuosoRef,
    virtuosoScrollerRef,
    isNearBottom,
    showScrollTop,
    handleVirtuosoAtBottomChange,
    scrollToBottom,
    scrollToTop,
  };
}
