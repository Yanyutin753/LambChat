import { useRef, useEffect, useState, useCallback } from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import {
  hasNewOutgoingMessage,
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
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const virtuosoScrollerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const rafRef = useRef<number>(0);
  const scrollCleanupRef = useRef<(() => void) | null>(null);
  const previousMessagesRef = useRef(messages);

  const userScrolledUpRef = useRef(false);

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

  // Scroll the Footer sentinel into view — it's always in the DOM (not virtualized)
  const scrollToBottom = useCallback(() => {
    userScrolledUpRef.current = false;
    scrollCleanupRef.current?.();
    scrollCleanupRef.current = startVirtuosoScrollToBottom({
      virtuoso: virtuosoRef.current,
      scroller: virtuosoScrollerRef.current,
      footer: messagesEndRef.current,
    });
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
      const dScroll = lastScrollTop.value - scrollTop;

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
    };
  }, [messages.length]);

  // Scroll to bottom on session change (after messages load)
  // Only trigger for session switches (not new session creation — sendMessage handles its own scrolling)
  const pendingScrollRef = useRef(false);
  const prevSessionIdRef = useRef<string | null | undefined>(sessionId);
  useEffect(() => {
    if (sessionId && prevSessionIdRef.current) {
      pendingScrollRef.current = true;
    }
    prevSessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    if (messages.length > 0 && pendingScrollRef.current) {
      const timer = setTimeout(() => {
        pendingScrollRef.current = false;
        scrollToBottom();
      }, 50);
      return () => {
        clearTimeout(timer);
        scrollCleanupRef.current?.();
        scrollCleanupRef.current = null;
      };
    }
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (hasNewOutgoingMessage(previousMessagesRef.current, messages)) {
      scrollToBottom();
    }
    previousMessagesRef.current = messages;
  }, [messages, scrollToBottom]);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
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
