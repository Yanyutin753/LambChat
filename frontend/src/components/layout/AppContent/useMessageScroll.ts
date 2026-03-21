import { useRef, useEffect, useCallback, useState } from "react";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  showScrollTop: boolean;
  setShowScrollTop: (value: boolean) => void;
  handleScroll: () => void;
  checkIfNearBottom: () => boolean;
}

export function useMessageScroll(
  messages: { id: string }[],
): UseMessageScrollReturn {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const scrollTopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastScrollTopRef = useRef(0);
  const lastScrollTimeRef = useRef(0);

  // Track previous message count to detect new messages
  const prevMessagesCountRef = useRef(messages.length);

  // Check if user is near the bottom (within 100px)
  const checkIfNearBottom = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return true;
    const threshold = 100;
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      threshold;
    setIsNearBottom(isAtBottom);
    return isAtBottom;
  }, []);

  // Auto-scroll to bottom when new messages are added or when loading
  useEffect(() => {
    const prevCount = prevMessagesCountRef.current;
    const newCount = messages.length;

    // Scroll to bottom when:
    // 1. New message is added (count increased)
    // 2. User is already near bottom
    if (newCount > prevCount || isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
    }

    prevMessagesCountRef.current = newCount;
  }, [messages, isNearBottom]);

  // Smart scroll-to-top: detect fast upward scroll and auto-hide
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    checkIfNearBottom();

    const now = Date.now();
    const scrollTop = container.scrollTop;
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
  }, [checkIfNearBottom]);

  return {
    messagesContainerRef,
    messagesEndRef,
    isNearBottom,
    showScrollTop,
    setShowScrollTop,
    handleScroll,
    checkIfNearBottom,
  };
}
